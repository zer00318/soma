PYTHON := .venv/bin/python

.PHONY: check install-dev test

install-dev:
	$(PYTHON) -m pip install -e '.[dev]'

test:
	$(PYTHON) -m pytest tests/unit tests/test_evaluator_validity.py \
		--cov=soma.domain --cov=soma.application --cov-report=term-missing

check:
	$(PYTHON) -m ruff format --check src tests/unit tools
	$(PYTHON) -m ruff check src tests/unit tools
	$(PYTHON) -m mypy --strict src/soma/domain src/soma/application
	$(PYTHON) tools/check_functions.py src/soma
	$(PYTHON) -m vulture src/soma --min-confidence 90
	$(PYTHON) tools/check_frozen_gold.py evaluation/oag/v2/datasets.json
	$(MAKE) test
