"""Turn a browser-copied cURL command into a committed fixture.

This is the tool behind `radar capture` (W1-07). It exists so the Day 2
DevTools pass (W1-08) produces a paper trail — a real request and a real
response, saved to disk — instead of a shape someone typed from memory.
Per CLAUDE.md: endpoint shapes are captured, never guessed.

Deliberately dumb: it parses Chrome's "Copy as cURL (bash)" format, not
arbitrary shell. If DevTools ever hands you something this can't parse,
that's a signal to look at the raw text yourself, not a bug to work around
with a fancier parser.
"""

from __future__ import annotations

import json
import re
import shlex
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import httpx

# Headers httpx manages itself; replaying them verbatim causes more problems
# than it solves — e.g. a captured `accept-encoding: br` will make httpx
# choke if the `brotli` package isn't installed, and a captured
# `content-length` will simply be wrong once cURL's exact byte layout is
# gone. Drop them and let httpx recompute both honestly.
_DROPPED_HEADERS = {"accept-encoding", "content-length"}


@dataclass
class ParsedCurlRequest:
    method: str
    url: str
    headers: dict[str, str] = field(default_factory=dict)
    body: str | None = None
    unhandled_tokens: list[str] = field(default_factory=list)


def parse_curl(text: str) -> ParsedCurlRequest:
    """Parse a Chrome "Copy as cURL (bash)" command.

    Handles line-continuation backslashes, single- and double-quoted
    arguments, -H/--header, -X/--request, and --data/--data-raw/
    --data-binary/--data-ascii. Anything else is collected into
    `unhandled_tokens` rather than silently dropped, so a flag this parser
    doesn't know about is visible instead of invisible.
    """
    normalized = re.sub(r"\\\r?\n", " ", text)
    tokens = shlex.split(normalized)

    url: str | None = None
    method: str | None = None
    headers: dict[str, str] = {}
    body: str | None = None
    unhandled: list[str] = []

    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token == "curl":
            pass
        elif token in ("-H", "--header"):
            i += 1
            if i < len(tokens):
                name, _, value = tokens[i].partition(":")
                headers[name.strip().lower()] = value.strip()
        elif token in ("--data", "--data-raw", "--data-binary", "--data-ascii"):
            i += 1
            if i < len(tokens):
                body = tokens[i]
        elif token in ("-X", "--request"):
            i += 1
            if i < len(tokens):
                method = tokens[i].upper()
        elif token in ("--compressed", "-s", "--silent", "-k", "--insecure"):
            pass
        elif token.startswith("http://") or token.startswith("https://") or (
            not token.startswith("-") and url is None
        ):
            url = token
        else:
            unhandled.append(token)
        i += 1

    if url is None:
        raise ValueError("no URL found in the cURL command")

    resolved_method = method or ("POST" if body is not None else "GET")
    for name in _DROPPED_HEADERS:
        headers.pop(name, None)

    return ParsedCurlRequest(
        method=resolved_method,
        url=url,
        headers=headers,
        body=body,
        unhandled_tokens=unhandled,
    )


@dataclass
class InventoryRow:
    path: str
    types: Counter
    count: int
    null_count: int
    example: object


def field_inventory(payload: object) -> list[InventoryRow]:
    """Flatten a JSON payload into one row per field path.

    Arrays are collapsed to a single `path[]` entry aggregated across all
    elements — the question this answers is "what shape does this field
    have across the whole response," not "what's in slot 7."
    """
    stats: dict[str, dict] = {}

    def record(path: str, value: object) -> None:
        entry = stats.setdefault(
            path, {"types": Counter(), "count": 0, "null_count": 0, "example": None}
        )
        entry["count"] += 1
        if value is None:
            entry["null_count"] += 1
            entry["types"]["null"] += 1
            return
        entry["types"][type(value).__name__] += 1
        if entry["example"] is None:
            entry["example"] = value

    def walk(obj: object, path: str) -> None:
        if isinstance(obj, dict):
            if not obj:
                record(path, {})
            else:
                for key, value in obj.items():
                    walk(value, f"{path}.{key}" if path else key)
        elif isinstance(obj, list):
            if not obj:
                record(path, [])
            else:
                for item in obj:
                    walk(item, f"{path}[]" if path else "[]")
        else:
            record(path, obj)

    walk(payload, "")

    return [
        InventoryRow(
            path=path,
            types=entry["types"],
            count=entry["count"],
            null_count=entry["null_count"],
            example=entry["example"],
        )
        for path, entry in sorted(stats.items())
    ]


def format_inventory(rows: list[InventoryRow]) -> str:
    if not rows:
        return "(empty payload)"

    def fmt_types(types: Counter) -> str:
        return "|".join(f"{t}" for t in types)

    def fmt_example(value: object) -> str:
        text = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
        text = text.replace("\n", " ")
        return text if len(text) <= 40 else text[:37] + "..."

    path_w = max(len(r.path) or 1 for r in rows) + 2
    type_w = max(len(fmt_types(r.types)) for r in rows) + 2

    lines = [
        f"{'path'.ljust(path_w)}{'types'.ljust(type_w)}{'null%'.ljust(8)}example",
        "-" * (path_w + type_w + 8 + 40),
    ]
    for row in rows:
        null_pct = f"{100 * row.null_count / row.count:.0f}%" if row.count else "-"
        lines.append(
            f"{row.path.ljust(path_w)}"
            f"{fmt_types(row.types).ljust(type_w)}"
            f"{null_pct.ljust(8)}"
            f"{fmt_example(row.example)}"
        )
    return "\n".join(lines)


@dataclass
class CaptureResult:
    fixture_path: Path
    meta_path: Path
    inventory: list[InventoryRow]
    status_code: int


def run_capture(
    name: str,
    curl_text: str,
    fixtures_dir: Path,
    client: httpx.Client | None = None,
) -> CaptureResult:
    """Replay a parsed cURL request and save the response as a fixture.

    Writes two files: `<name>.json` (the response body verbatim — this is
    what W1-09/W1-10's pydantic parse tests read) and `<name>.meta.json`
    (the request that produced it: URL, method, headers, body, timestamp —
    so the fixture is reproducible without re-reading the DevTools capture).
    """
    parsed = parse_curl(curl_text)

    owns_client = client is None
    client = client or httpx.Client(timeout=30.0, follow_redirects=True)
    try:
        response = client.request(
            parsed.method,
            parsed.url,
            headers=parsed.headers,
            content=parsed.body,
        )
    finally:
        if owns_client:
            client.close()

    response.raise_for_status()
    payload = response.json()

    fixtures_dir.mkdir(parents=True, exist_ok=True)
    fixture_path = fixtures_dir / f"{name}.json"
    fixture_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")

    meta = {
        "captured_at": datetime.now(UTC).isoformat(),
        "method": parsed.method,
        "url": parsed.url,
        "headers": parsed.headers,
        "body": parsed.body,
        "status_code": response.status_code,
        "unhandled_curl_tokens": parsed.unhandled_tokens,
    }
    meta_path = fixtures_dir / f"{name}.meta.json"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n")

    return CaptureResult(
        fixture_path=fixture_path,
        meta_path=meta_path,
        inventory=field_inventory(payload),
        status_code=response.status_code,
    )
