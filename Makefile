# SPDX-License-Identifier: GPL-3.0-or-later
# Harness de qualidade. Todos os gates do DoD (docs/IMPLEMENTATION-PROMPT §4.2).
VENV ?= .venv
PY := $(VENV)/bin/python
RUFF := $(VENV)/bin/ruff
MYPY := $(VENV)/bin/mypy
COVERAGE := $(VENV)/bin/coverage
TEST_RUNNER := $(PY) tools/run_tests_isolated.py
RELEASE_HOST := $(PY) tools/release_host.py

.PHONY: help venv lint format format-check typecheck boundaries independence test cov check clean release-inspect release-verify

help:
	@echo "Alvos: venv lint format-check typecheck boundaries test cov check"
	@echo "Visual: qml-visual check-qml-goldens update-qml-goldens"
	@echo "Operação: release-inspect release-verify BUNDLE=/caminho"

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
	$(TEST_RUNNER)

cov:
	$(COVERAGE) erase
	$(TEST_RUNNER) --cov=steamzero --cov-report=term-missing

# Gate completo: ordem barata->cara. Nenhum commit sem `make check` verde.
check: format-check lint boundaries independence typecheck cov

clean:
	rm -rf .mypy_cache .ruff_cache .pytest_cache .hypothesis htmlcov .coverage

qml-visual: ## Gate visual: renderiza os cenários e compara com as baselines
	$(TEST_RUNNER) tests/integration/test_qml_visual_capture.py -q

update-qml-goldens: ## Regrava as baselines visuais (exige revisão do diff no commit)
	$(PY) tools/update_qml_goldens.py --write

check-qml-goldens: ## Relata divergências visuais sem regravar nada
	$(PY) tools/update_qml_goldens.py --check

release-inspect: ## Diagnóstico read-only de checkout, host, daemon e componentes
	$(RELEASE_HOST) inspect

release-verify: ## Confere bundle CI; uso: make release-verify BUNDLE=/caminho
	test -n "$(BUNDLE)"
	$(RELEASE_HOST) verify-bundle --bundle "$(BUNDLE)"
