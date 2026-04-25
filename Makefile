.PHONY: help install init-db scrape analyze send dry-send pipeline run ui clean lint test-models

PY ?= $(shell command -v python3 2>/dev/null || command -v python)

help:  ## Show this help.
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-12s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install:  ## pip install -r requirements.txt
	$(PY) -m pip install -r requirements.txt

init-db:  ## Create the SQLite schema (idempotent)
	$(PY) -m mailrocket init-db

scrape:  ## Scrape LinkedIn (no analysis, no send)
	$(PY) -m mailrocket scrape

analyze:  ## Run LLM on posts pending analysis
	$(PY) -m mailrocket analyze

pipeline:  ## scrape + analyze (no send). Use during the day.
	$(PY) -m mailrocket pipeline

send:  ## Send pending emails. Run when you want visibility (e.g. start of day).
	$(PY) -m mailrocket send

dry-send:  ## Show what `send` would do without contacting Gmail
	$(PY) -m mailrocket send --dry-run

run:  ## scrape + analyze + send in one shot
	$(PY) -m mailrocket run-all

ui:  ## Launch the web review UI on http://127.0.0.1:8765
	$(PY) -m mailrocket ui

test-models:  ## Ping every configured LLM with a tiny prompt and print a summary
	$(PY) scripts/test_models.py

clean:  ## Remove caches, .pyc, *.log
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type f -name '*.py[co]' -delete
	rm -f mailrocket.log resume_analysis.log

.DEFAULT_GOAL := help
