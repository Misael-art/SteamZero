# SPDX-License-Identifier: GPL-3.0-or-later
# Harness de qualidade. Todos os gates do DoD (docs/IMPLEMENTATION-PROMPT §4.2).
VENV ?= .venv
PY := $(VENV)/bin/python
RUFF := $(VENV)/bin/ruff
MYPY := $(VENV)/bin/mypy
PYTEST := $(VENV)/bin/pytest
COVERAGE := $(VENV)/bin/coverage

.PHONY: help venv lint format format-check typecheck boundaries independence test cov check clean

help:
	@echo "Alvos: venv lint format-check typecheck boundaries test cov check"
	@echo "Visual: qml-visual check-qml-goldens update-qml-goldens"

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

independence:
	$(PY) tools/check_independence.py

test:
	$(PYTEST)

cov:
	$(COVERAGE) erase
	$(PYTEST) --cov=steamzero --cov-report=term-missing

# Gate completo: ordem barata->cara. Nenhum commit sem `make check` verde.
check: format-check lint boundaries independence typecheck cov

clean:
	rm -rf .mypy_cache .ruff_cache .pytest_cache .hypothesis htmlcov .coverage

qml-visual: ## Gate visual: renderiza os cenários e compara com as baselines
	$(VENV)/bin/pytest tests/integration/test_qml_visual_capture.py -q

update-qml-goldens: ## Regrava as baselines visuais (exige revisão do diff no commit)
	$(PY) tools/update_qml_goldens.py --write

check-qml-goldens: ## Relata divergências visuais sem regravar nada
	$(PY) tools/update_qml_goldens.py --check
