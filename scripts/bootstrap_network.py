"""One-shot: fetch the current IDEAdif snapshot, build the DB, render a map.

Run with:  uv run python scripts/bootstrap_network.py
Requires network access to ideadif.adif.es (won't work offline).
"""

from __future__ import annotations

from redferro.db.duckdb_io import build
from redferro.sources.ideadif_wfs import fetch_all
from redferro.viz.maps import network_map


def main() -> None:
    gpkg = fetch_all()
    print(f"snapshot: {gpkg}")
    dbp = build(gpkg)
    print(f"duckdb:   {dbp}")
    html = network_map(gpkg)
    print(f"map:      {html}")


if __name__ == "__main__":
    main()
