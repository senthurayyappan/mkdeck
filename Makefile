.DEFAULT_GOAL := help
.PHONY: help install check lint format typecheck test docs docs-test docs-deploy build smoke vendor

help: ## Show available commands
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z_-]+:.*## / {printf "%-16s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Install development tools and Git hooks
	uv sync --all-extras
	uv run pre-commit install --hook-type pre-commit --hook-type commit-msg

check: ## Run pre-commit and static checks
	uv run pre-commit run --all-files

lint: ## Check lint and formatting without changing files
	uv run ruff check .
	uv run ruff format --check .

format: ## Apply safe lint fixes and format
	uv run ruff check --fix .
	uv run ruff format .

typecheck: ## Check types with ty
	uv run ty check

test: ## Run the test suite (browser tests skip without the check extra and Chromium)
	uv run pytest --cov --cov-report=term-missing

docs: ## Serve documentation locally
	uv run --group docs mkdocs serve

docs-test: ## Build documentation and fail on warnings
	uv run --group docs mkdocs build --strict

docs-deploy: ## Publish documentation to the gh-pages branch
	uv run --group docs mkdocs gh-deploy

build: ## Build a wheel and source distribution
	uv build --no-sources

smoke: ## Build the wheel, check its metadata, and run it from a clean virtualenv
	uv build --no-sources --clear
	uvx twine==7.0.0 check --strict dist/*
	uv run --no-project python scripts/smoke_wheel.py dist

vendor: ## Re-download the vendored front-end libraries (reveal.js, KaTeX, Roboto, three.js)
	uv run scripts/vendor_assets.py
