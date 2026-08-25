.PHONY: setup check lint test ingest backfill capture dbt-build eval clean

# --- setup -------------------------------------------------------------

setup:
	uv sync

# --- day 1: green on nothing -------------------------------------------

check: lint test

lint:
	uv run ruff check .

test:
	uv run pytest

# --- ingest (Day 2+, stubs until src/radar/ingest exists) --------------

ingest:
	@test -n "$(DATE)" || (echo "usage: make ingest DATE=YYYY-MM-DD" && exit 1)
	uv run radar ingest --date $(DATE)

backfill:
	@test -n "$(FROM)" && test -n "$(TO)" || (echo "usage: make backfill FROM=YYYY-MM-DD TO=YYYY-MM-DD" && exit 1)
	uv run radar backfill --from $(FROM) --to $(TO)

# Replay a captured cURL request against SICAP, save the response as a
# fixture under tests/fixtures/, and print a field inventory. See
# docs/sicap-endpoints.md. (W1-07)
capture:
	@test -n "$(NAME)" || (echo "usage: make capture NAME=direct-list CURL_FILE=path/to/curl.txt" && exit 1)
	uv run radar capture --name $(NAME) --curl-file $(CURL_FILE)

# --- transform (Day 4+) -------------------------------------------------

dbt-build:
	cd transform && uv run dbt build

# --- eval (Day 6+ for entity resolution, Day 10+ for narrative grounding)

eval:
	uv run python -m radar.eval

clean:
	rm -rf .pytest_cache .ruff_cache transform/target transform/logs
