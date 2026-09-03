.PHONY: help install lock lint fmt test build hooks \
        snapshot db reference lines maps reproduce

.DEFAULT_GOAL := help

help:         ## show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-11s\033[0m %s\n", $$1, $$2}'

install:      ## create venv + install (dev)
	uv sync --all-extras --group dev

lock:         ## refresh uv.lock (commit the result)
	uv lock --upgrade

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

# ---- data pipeline ----------------------------------------------------------
# `reproduce` rebuilds every derived artefact from the committed inputs. Only
# `reference` and `snapshot` touch the network; everything else is offline.

snapshot:     ## re-fetch a FRESH IDEAdif snapshot (network; changes the pinned data)
	uv run redferro network fetch

db:           ## build the DuckDB store from the committed snapshot (offline)
	uv run redferro db build

reference:    ## download + checksum the municipal boundaries (network, one-time)
	uv run redferro reference fetch

lines:        ## build lineas.csv / lineas_estaciones.csv / lineas_ciudades.csv
	uv run redferro lines build

maps:         ## render the four HTML maps (offline)
	uv run redferro map
	uv run redferro map --theme dark
	uv run redferro map --freight-only
	uv run redferro map --freight-only --theme dark

reproduce: db reference lines maps  ## rebuild ALL derived artefacts from pinned inputs
	@echo "Reproduced: DuckDB, line CSVs, station geocoding, and the four maps."
