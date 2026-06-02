# Makefile — single entry point for routine tasks.
# `make` or `make help` lists available targets.

VENV          ?= .venv
PY            := $(VENV)/bin/python
PIP           := $(VENV)/bin/pip
PYTEST        := $(VENV)/bin/pytest
DEPS_SENTINEL := $(VENV)/.deps-installed

.DEFAULT_GOAL := help

.PHONY: help
help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

$(VENV)/bin/python:                # venv is created automatically when missing
	python3 -m venv $(VENV)

$(DEPS_SENTINEL): $(VENV)/bin/python server/requirements-dev.txt
	$(PIP) install -r server/requirements-dev.txt
	touch $(DEPS_SENTINEL)

.PHONY: install
install: $(DEPS_SENTINEL) ## Create .venv and install backend dev/test deps

.PHONY: test
test: install ## Run backend tests (venv is bootstrapped automatically)
	$(PYTEST)

.PHONY: run
run: install ## Run the backend server (serves built frontend from server/static)
	$(PY) server/main.py

.PHONY: dev
dev: ## Run the Vite frontend dev server (proxies /api to the backend)
	npm install && npm run dev

.PHONY: build
build: ## Build the frontend into dist/
	npm install && npm run build

.PHONY: clean
clean: ## Remove the venv and test/python caches
	rm -rf $(VENV) .pytest_cache
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
