# CLAUDE.md

Guidance for Claude Code when working in this repo.

## What this project is
Raw data, maps and a **dependency graph** for the Spanish **freight** railway
network over time (target 2015–present), plus a model of **habilitaciones de
línea y de material rodante** (the certifications a maquinista needs per line and
per machine). The end goal is to visualise how line-habilitaciones depend on each
other geographically — read as an entry-barrier map for alternative freight
operators.

## Environment
- Python ≥3.11, managed by **uv**. Never call `pip` directly. Use:
  - `uv sync --all-extras --group dev` to install
  - `uv run <cmd>` to run anything (tests, CLI, scripts)
- `uv.lock` **is committed**. Use `uv sync --frozen` for reproducible installs and
  `uv lock --upgrade` (`make lock`) to bump on purpose.
- `make help` lists everything. Run `make lint && make test` before committing.
- Lint/format: **ruff** (`uv run ruff check`, `uv run ruff format`). Types: mypy.
- Tests: `uv run pytest`. CLI: `uv run redferro --help`.

## Testing rules
- **The whole suite must run offline.** Never add a test that hits `ideadif.adif.es` or
  downloads a Declaración PDF; build synthetic fixtures instead (see `tests/conftest.py`).
- The one permitted network touch is DuckDB installing its `spatial` extension. Tests
  needing it take the `duck` fixture, which skips when it is unavailable.
- When fixing a bug, first write the test that fails against the unfixed code.

## Architecture (src layout, package `redferro`)
- `sources/ideadif_wfs.py` — downloads INSPIRE feature types from the IDEAdif WFS.
  The service is a **current snapshot**, not historical; snapshots are date-stamped.
- `sources/declaracion_red.py` — parses the annual *Declaración sobre la Red* PDFs
  (Catálogo de Líneas). **This is the historical/temporal backbone.**
- `db/schema.sql` + `db/duckdb_io.py` — DuckDB store (spatial ext). Three blocks:
  infrastructure (open), habilitaciones (constructed/internal), derived graph.
- `habilitaciones/graph.py` — builds the networkx adjacency graph over
  habilitación units (shared physical node ⇒ geographic dependency).
- `viz/maps.py` — folium maps.

## Conventions
- Store geometry in **EPSG:25830** (native CRS of IDEAdif); reproject to 4326 only
  for web maps.
- `data/raw` is immutable, date-stamped, gitignored. Derived artefacts go to
  `data/interim` / `data/processed`. Never commit large binaries.
- Every table carries a validity period; queries are "as of" a date.
- Keep raw PDF/table extraction in `data/interim` for auditability before cleaning.

## Data-source facts worth remembering
- IDEAdif WFS: `https://ideadif.adif.es/services/wfs` — layers
  `TN.RailTransportNetwork.{RailwayLink,RailwayNode,RailwayStationNode}`.
- Habilitaciones are **not open data** at driver level (licencia = AESF;
  certificado = empresa ferroviaria). Populate `habilitacion_*` tables from an
  internal source if available, else reconstruct from the catálogo de líneas.

## Known gap (do not paper over)
`load_snapshot_gpkg` does not yet populate `tramo.nodo_ini`/`nodo_fin`, `linea_id` or
`pk_*` — those names need a real IDEAdif fetch to inspect. Consequences: the
habilitación graph is **edgeless by construction**, `v_red_mercancias` is empty, and the
synthetic `tramo_id`/`dep_id` are not stable across snapshots. Tracked as
`TODO(ideadif-mapping)` in `db/duckdb_io.py` with the mapping table in
`docs/data-sources.md` §1. Fill it from real data, don't guess.

## When unsure
Prefer adding a documented `TODO` and capturing raw data over silently guessing a
PDF table layout — annexes differ across years.
