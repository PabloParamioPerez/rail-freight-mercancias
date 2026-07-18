.PHONY: help install lock sync lint fmt test build hooks

.DEFAULT_GOAL := help

help:         ## show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

install:      ## create venv + install (dev)
	uv sync --all-extras --group dev

lock:         ## refresh uv.lock (commit the result)
	uv lock --upgrade

sync:         ## fetch network snapshot + build DB  (needs ideadif.adif.es)
	uv run redferro network fetch
	uv run redferro db build

lint:         ## ruff check + format check + mypy
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy src

fmt:          ## autoformat and autofix
	uv run ruff format .
	uv run ruff check --fix .

test:         ## run the (offline) test suite
	uv run pytest

build:        ## build the wheel/sdist into dist/
	uv build

hooks:        ## install pre-commit hooks
	uv run pre-commit install
