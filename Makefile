# SPDX-License-Identifier: GPL-3.0-or-later
# Harness de qualidade. Todos os gates do DoD (docs/IMPLEMENTATION-PROMPT §4.2).
VENV ?= .venv
PY := $(VENV)/bin/python
RUFF := $(VENV)/bin/ruff
MYPY := $(VENV)/bin/mypy
PYTEST := $(VENV)/bin/pytest

.PHONY: help venv lint format format-check typecheck boundaries test cov check clean

help:
	@echo "Alvos: venv lint format-check typecheck boundaries test cov check"

venv:
	python3 -m venv $(VENV)
	$(VENV)/bin/pip install --upgrade pip pip-tools
	$(VENV)/bin/pip install --require-hashes -r requirements-dev.lock
	$(VENV)/bin/pip install --no-deps -e .

lint:
	$(RUFF) check src tests tools

format:
	$(RUFF) format src tests tools

format-check:
	$(RUFF) format --check src tests tools

typecheck:
	$(MYPY)

boundaries:
	$(PY) tools/lint_boundaries.py --root src

test:
	$(PYTEST)

cov:
	$(PYTEST) --cov=steamzero --cov-report=term-missing

# Gate completo: ordem barata->cara. Nenhum commit sem `make check` verde.
check: format-check lint boundaries typecheck test

clean:
	rm -rf .mypy_cache .ruff_cache .pytest_cache .hypothesis htmlcov .coverage
