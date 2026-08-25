"""Tests for the W1-07 capture tool: cURL parsing, field inventory, and the
end-to-end `radar capture` command against a mocked SICAP response."""

import json
from pathlib import Path

import httpx
import pytest
import respx
from typer.testing import CliRunner

from radar.cli import app
from radar.sicap.capture import field_inventory, format_inventory, parse_curl, run_capture

DIRECT_LIST_URL = (
    "https://www.e-licitatie.ro/api-pub/DirectAcquisitionCommonUI/api/GetDirectAcquisitionList"
)

CHROME_CURL = f"""curl '{DIRECT_LIST_URL}' \\
  -H 'accept: application/json' \\
  -H 'accept-encoding: gzip, deflate, br' \\
  -H 'content-type: application/json' \\
  -H 'referer: https://www.e-licitatie.ro/pub/notices/contract-notices/list/0/0' \\
  -H 'user-agent: Mozilla/5.0' \\
  --data-raw '{{"pageIndex":0,"pageSize":50}}' \\
  --compressed"""


class TestParseCurl:
    def test_extracts_method_url_headers_body(self):
        parsed = parse_curl(CHROME_CURL)
        assert parsed.method == "POST"
        assert parsed.url == DIRECT_LIST_URL
        assert parsed.headers["content-type"] == "application/json"
        assert parsed.headers["referer"].endswith("/list/0/0")
        assert parsed.body == '{"pageIndex":0,"pageSize":50}'

    def test_drops_headers_httpx_manages_itself(self):
        parsed = parse_curl(CHROME_CURL)
        assert "accept-encoding" not in parsed.headers
        assert "content-length" not in parsed.headers

    def test_defaults_to_get_without_body(self):
        parsed = parse_curl("curl 'https://example.org/x' -H 'accept: */*'")
        assert parsed.method == "GET"
        assert parsed.body is None

    def test_explicit_method_wins(self):
        parsed = parse_curl("curl -X PUT 'https://example.org/x' --data-raw '{}'")
        assert parsed.method == "PUT"

    def test_handles_double_quoted_headers(self):
        text = 'curl "https://example.org/x" -H "accept: */*"'
        parsed = parse_curl(text)
        assert parsed.url == "https://example.org/x"
        assert parsed.headers["accept"] == "*/*"

    def test_missing_url_raises(self):
        with pytest.raises(ValueError, match="no URL"):
            parse_curl("curl -H 'accept: */*'")

    def test_unhandled_flags_are_collected_not_silently_dropped(self):
        parsed = parse_curl("curl 'https://example.org/x' --some-future-flag")
        assert "--some-future-flag" in parsed.unhandled_tokens


class TestFieldInventory:
    def test_flattens_nested_object(self):
        rows = field_inventory({"a": {"b": 1}})
        paths = {r.path for r in rows}
        assert "a.b" in paths

    def test_collapses_list_items_to_single_path(self):
        payload = {"results": [{"id": 1}, {"id": 2}, {"id": 3}]}
        rows = {r.path: r for r in field_inventory(payload)}
        assert "results[].id" in rows
        assert rows["results[].id"].count == 3

    def test_null_rate_is_computed(self):
        payload = {"results": [{"v": 1}, {"v": None}]}
        rows = {r.path: r for r in field_inventory(payload)}
        assert rows["results[].v"].null_count == 1
        assert rows["results[].v"].count == 2

    def test_mixed_types_are_all_recorded(self):
        payload = {"results": [{"v": 1}, {"v": "1"}]}
        rows = {r.path: r for r in field_inventory(payload)}
        assert set(rows["results[].v"].types) == {"int", "str"}

    def test_example_is_first_non_null_value(self):
        payload = {"results": [{"v": None}, {"v": "hello"}]}
        rows = {r.path: r for r in field_inventory(payload)}
        assert rows["results[].v"].example == "hello"

    def test_empty_list_and_dict_are_leaves_not_dropped(self):
        rows = {r.path: r for r in field_inventory({"tags": [], "meta": {}})}
        assert "tags" in rows
        assert "meta" in rows

    def test_format_inventory_renders_without_error(self):
        rows = field_inventory({"results": [{"id": 1, "name": "x"}]})
        text = format_inventory(rows)
        assert "results[].id" in text
        assert "results[].name" in text


class TestRunCapture:
    def test_saves_fixture_and_meta_and_builds_inventory(self, tmp_path: Path):
        payload = {"results": [{"id": 1, "valoareEstimata": 1000.0}], "totalCount": 1}

        with respx.mock:
            respx.post("https://example.org/api/list").mock(
                return_value=httpx.Response(200, json=payload)
            )
            result = run_capture(
                name="direct-list",
                curl_text="curl 'https://example.org/api/list' --data-raw '{\"pageIndex\":0}'",
                fixtures_dir=tmp_path,
            )

        assert result.status_code == 200
        saved = json.loads(result.fixture_path.read_text())
        assert saved == payload

        meta = json.loads(result.meta_path.read_text())
        assert meta["method"] == "POST"
        assert meta["url"] == "https://example.org/api/list"

        paths = {row.path for row in result.inventory}
        assert "results[].valoareEstimata" in paths


class TestCaptureCliCommand:
    def test_end_to_end_via_cli(self, tmp_path: Path):
        curl_file = tmp_path / "req.curl.txt"
        curl_file.write_text("curl 'https://example.org/api/list'")
        fixtures_dir = tmp_path / "fixtures"

        with respx.mock:
            respx.get("https://example.org/api/list").mock(
                return_value=httpx.Response(200, json={"results": []})
            )
            runner = CliRunner()
            result = runner.invoke(
                app,
                [
                    "capture",
                    "--name",
                    "direct-list",
                    "--curl-file",
                    str(curl_file),
                    "--fixtures-dir",
                    str(fixtures_dir),
                ],
            )

        assert result.exit_code == 0, result.output
        assert (fixtures_dir / "direct-list.json").exists()
        assert (fixtures_dir / "direct-list.meta.json").exists()
        assert "HTTP 200" in result.output
