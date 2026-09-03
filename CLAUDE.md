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
- `sources/rfig.py` — parses the RFIG line numbering (nº de línea ↔ nombre ↔ ancho)
  from a committed wikitext snapshot of the Orden FOM/710/2015 catalogue.
- `sources/municipios.py` — fetches (by pinned SHA-256) the INE/IGN municipal
  boundaries and geocodes each station point to its municipio.
- `db/schema.sql` + `db/duckdb_io.py` — DuckDB store (spatial ext). Three blocks:
  infrastructure (open), habilitaciones (constructed/internal), derived graph.
- `analysis/lineas.py` — per-line reviewer products (catalogue, ordered stations,
  city list) written to `data/processed/lineas*.csv`.
- `habilitaciones/graph.py` — builds the networkx adjacency graph over
  habilitación units (shared physical node ⇒ geographic dependency).
- `viz/maps.py` — folium maps.

## Conventions
- Store geometry in **EPSG:25830** (native CRS of IDEAdif); reproject to 4326 only
  for web maps.
- Every table carries a validity period; queries are "as of" a date.
- Keep raw PDF/table extraction in `data/interim` for auditability before cleaning.
- **Reproducibility over leanness** (see `data/README.md`). Commit a dataset iff it
  cannot be re-fetched byte-identical: the exact IDEAdif snapshot (a moving source)
  is committed even though it is 20 MB; the 81 MB boundaries file is *not* (stable →
  fetched by checksum). Small reviewer-facing derived products (`lineas*.csv`, the
  geocode parquet, the four maps) are committed for convenience but stay regenerable
  by a `make` target; heavy regenerable artefacts (`redferro.duckdb`) are not. Every
  derived artefact must be rebuildable via `make reproduce` — never hand-edit one.
- `.gitignore` has **no inline comments** (a `!pattern  # note` matches nothing);
  keep negations on their own lines, after every guard they must override.

## Data-source facts worth remembering
- IDEAdif WFS: `https://ideadif.adif.es/services/wfs` — layers
  `TN.RailTransportNetwork.{RailwayLink,RailwayNode,RailwayStationNode}`.
- Habilitaciones are **not open data** at driver level (licencia = AESF;
  certificado = empresa ferroviaria). Populate `habilitacion_*` tables from an
  internal source if available, else reconstruct from the catálogo de líneas.

## Known gap (do not paper over)
The physical network is fully ingested (1 689 tramos, topology 100 % resolved, 1 306
freight-relevant). What is still missing:

- **Habilitaciones have no source.** The `habilitacion_*` tables are empty and this is
  not open data (licencia = AESF, certificado = each empresa ferroviaria). So
  `hab graph` returns an empty graph — not because adjacency is broken, but because
  there are no habilitación units to connect. Deciding this source is the project's
  real open question; see `docs/data-sources.md` §3 for the two options.
- **No history yet.** `DECLARACIONES` is empty and the WFS is a current snapshot only.
- `pk_ini`/`pk_fin` are not exposed by the WFS; they must come from the Catálogo.

Do not fabricate habilitación data to make the graph look populated.

## Working with the IDEAdif WFS
Hard-won facts, all in `sources/ideadif_wfs.py` and `docs/data-sources.md` §1:
feature types are `tn-ra:*` (not `TN.RailTransportNetwork.*`), GeoJSON is **not**
served (GML 3.2 only), DefaultCRS is 4258 (we request 25830), topology is in
`xlink:href` refs needing `GML_ATTRIBUTES_TO_OGR_FIELDS=YES`, and GDAL's autogenerated
`.gfs` must be stripped of `Untyped`/`*List` fields before pyogrio can read it.

## When unsure
Prefer adding a documented `TODO` and capturing raw data over silently guessing a
PDF table layout — annexes differ across years.
