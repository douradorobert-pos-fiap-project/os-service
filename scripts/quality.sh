#!/usr/bin/env bash
set -euo pipefail

mkdir -p reports
poetry run ruff check src tests
poetry run black --check src tests
poetry run mypy src
poetry run bandit -q -r src -c pyproject.toml -f json -o reports/bandit.json
poetry run xenon --max-absolute B --max-modules B --max-average A src
poetry run pytest --cov=src --cov-fail-under=80 --cov-report=term-missing --cov-report=xml:reports/coverage.xml --junitxml=reports/junit.xml
