.PHONY: install sync lint fmt test network hooks
install:      ## create venv + install (dev)
	uv sync --all-extras --group dev
sync:         ## fetch network snapshot + build DB
	uv run redferro network fetch
	uv run redferro db build
lint:
	uv run ruff check src tests
	uv run mypy src
fmt:
	uv run ruff format src tests
	uv run ruff check --fix src tests
test:
	uv run pytest
hooks:
	uv run pre-commit install
