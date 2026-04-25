.PHONY: help sync install lock init-db scrape analyze send dry-send pipeline run ui clean lint test-models

UV ?= uv
RUN ?= $(UV) run

help:  ## Show this help.
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-12s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

sync:  ## Install/refresh deps from pyproject.toml + uv.lock
	$(UV) sync

install: sync  ## Alias for sync (kept for muscle memory)

lock:  ## Re-resolve and refresh uv.lock
	$(UV) lock

init-db:  ## Create the SQLite schema (idempotent)
	$(RUN) mailrocket init-db

scrape:  ## Scrape LinkedIn (no analysis, no send)
	$(RUN) mailrocket scrape

analyze:  ## Run LLM on posts pending analysis
	$(RUN) mailrocket analyze

pipeline:  ## scrape + analyze (no send). Use during the day.
	$(RUN) mailrocket pipeline

send:  ## Send pending emails. Run when you want visibility (e.g. start of day).
	$(RUN) mailrocket send

dry-send:  ## Show what `send` would do without contacting Gmail
	$(RUN) mailrocket send --dry-run

run:  ## scrape + analyze + send in one shot
	$(RUN) mailrocket run-all

ui:  ## Launch the web review UI on http://127.0.0.1:8765
	$(RUN) mailrocket ui

test-models:  ## Ping every configured LLM with a tiny prompt and print a summary
	$(RUN) python scripts/test_models.py

lint:  ## Lint the codebase with ruff
	$(RUN) ruff check .

clean:  ## Remove caches, .pyc, *.log
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type f -name '*.py[co]' -delete
	rm -f mailrocket.log resume_analysis.log

.DEFAULT_GOAL := help
