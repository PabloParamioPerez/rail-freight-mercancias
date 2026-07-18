"""Build and load the DuckDB store from raw GeoPackage snapshots."""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path

import duckdb
import geopandas as gpd

from redferro.config import settings


def connect(path: Path | None = None) -> duckdb.DuckDBPyConnection:
    path = path or settings.duckdb_path
    path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(path))
    con.execute("INSTALL spatial; LOAD spatial;")
    return con


def init_schema(con: duckdb.DuckDBPyConnection) -> None:
    sql = (files("redferro.db") / "schema.sql").read_text(encoding="utf-8")
    con.execute(sql)


def load_snapshot_gpkg(con: duckdb.DuckDBPyConnection, gpkg: Path) -> None:
    """Load one stamped IDEAdif GeoPackage into tramo/dependencia tables.

    Reads via geopandas, hands WKB to DuckDB. Column mapping is intentionally
    defensive: IDEAdif attribute names should be inspected on first real fetch
    and mapped here (see docs/data-sources.md).
    """
    links = gpd.read_file(gpkg, layer="railway_link")
    con.register("links_df", _to_wkb(links))
    con.execute(
        """
        INSERT INTO tramo (tramo_id, linea_id, snapshot_date, geom)
        SELECT CAST(rowid AS VARCHAR), NULL, CAST(snapshot_date AS DATE),
               ST_GeomFromWKB(geom_wkb)
        FROM links_df
        """
    )
    for layer, tipo in (("railway_node", "nodo"), ("railway_station_node", "estacion")):
        gdf = gpd.read_file(gpkg, layer=layer)
        con.register("nodes_df", _to_wkb(gdf))
        con.execute(
            """
            INSERT INTO dependencia (dep_id, tipo, snapshot_date, geom)
            SELECT CAST(rowid AS VARCHAR), ?, CAST(snapshot_date AS DATE),
                   ST_GeomFromWKB(geom_wkb)
            FROM nodes_df
            """,
            [tipo],
        )
        con.unregister("nodes_df")
    con.unregister("links_df")


def _to_wkb(gdf: gpd.GeoDataFrame):
    df = gdf.copy()
    df["geom_wkb"] = df.geometry.to_wkb()
    df["rowid"] = range(len(df))
    return df.drop(columns=df.geometry.name)


def build(gpkg: Path | None = None) -> Path:
    """Fresh build: init schema and load the newest snapshot if present."""
    con = connect()
    init_schema(con)
    if gpkg is None:
        snaps = sorted(settings.raw.glob("ideadif_*.gpkg"))
        gpkg = snaps[-1] if snaps else None
    if gpkg is not None:
        load_snapshot_gpkg(con, gpkg)
    con.close()
    return settings.duckdb_path
