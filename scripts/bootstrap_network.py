"""One-shot Python entry point: fetch a fresh IDEAdif snapshot → DB → maps.

The canonical, reproducible path is `make reproduce`, which rebuilds everything from
the committed snapshot offline (only the boundaries download touches the network). This
script is the in-process equivalent of the *fetch-a-new-snapshot* flow and therefore
needs network access to ideadif.adif.es. To rebuild from the committed snapshot instead,
skip `fetch_all()` and start at `build()`.
"""

from __future__ import annotations

from redferro.db.duckdb_io import build
from redferro.sources.ideadif_wfs import fetch_all
from redferro.viz.maps import freight_map, network_map


def main() -> None:
    gpkg = fetch_all()
    print(f"snapshot: {gpkg}")
    dbp = build(gpkg)
    print(f"duckdb:   {dbp}")
    # maps read the newest snapshot from the store; do not pass the gpkg as `out`.
    print(f"network:  {network_map()}")
    print(f"freight:  {freight_map()}")


if __name__ == "__main__":
    main()
