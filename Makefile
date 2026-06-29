PYTHON := .venv/bin/python

.PHONY: check install-dev test

install-dev:
	$(PYTHON) -m pip install -e '.[dev]'

test:
	$(PYTHON) -m pytest tests/unit

check:
	$(PYTHON) -m ruff format --check src tests/unit tools
	$(PYTHON) -m ruff check src tests/unit tools
	$(PYTHON) -m mypy --strict src/trace_memory/domain src/trace_memory/application
	$(PYTHON) tools/check_functions.py src/trace_memory
	$(PYTHON) -m vulture src/trace_memory --min-confidence 90
	$(PYTHON) tools/check_frozen_gold.py evaluation/oag/v2/datasets.json
	$(MAKE) test
