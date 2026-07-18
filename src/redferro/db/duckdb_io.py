"""Build and load the DuckDB store from raw GeoPackage snapshots."""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path

import duckdb
import geopandas as gpd
import pandas as pd

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

    Reads via geopandas, hands WKB to DuckDB. Re-loading the same snapshot is
    idempotent: rows for the incoming snapshot_date are deleted first.

    TODO(ideadif-mapping): this loader is deliberately minimal until we have seen
    the real IDEAdif attribute names (they need an actual fetch to inspect — see
    docs/data-sources.md §1). Three consequences today, all intentional:

      1. `tramo_id` / `dep_id` are synthesised from GeoPackage row order, so they
         are NOT stable across fetches. A second snapshot renumbers everything,
         which defeats the temporal-panel premise of the schema. Replace with the
         real stable feature id (INSPIRE `inspireId` / `gml_id`) once known.
      2. `linea_id`, `pk_ini`, `pk_fin`, `nodo_ini`, `nodo_fin` and
         `dependencia.nombre` are all left NULL. Because nodo_ini/nodo_fin drive
         adjacency, `habilitaciones.graph.build_dependency_graph` is edgeless by
         construction until they are populated.
      3. The `linea` table is never written here, so the `v_red_mercancias` view
         (which joins linea) returns no rows.
    """
    links = gpd.read_file(gpkg, layer="railway_link")
    con.register("links_df", _to_wkb(links))
    con.execute(
        """
        DELETE FROM tramo
        WHERE snapshot_date IN (SELECT DISTINCT CAST(snapshot_date AS DATE) FROM links_df)
        """
    )
    con.execute(
        """
        INSERT INTO tramo (tramo_id, linea_id, snapshot_date, geom)
        SELECT 'link-' || CAST(_row_no AS VARCHAR), NULL, CAST(snapshot_date AS DATE),
               ST_GeomFromWKB(geom_wkb)
        FROM links_df
        """
    )
    con.unregister("links_df")

    for layer, tipo in (("railway_node", "nodo"), ("railway_station_node", "estacion")):
        gdf = gpd.read_file(gpkg, layer=layer)
        con.register("nodes_df", _to_wkb(gdf))
        # dep_id must be qualified by layer: both node layers number from 0, so an
        # unqualified id collides on the (dep_id, snapshot_date) primary key.
        con.execute(
            """
            DELETE FROM dependencia
            WHERE tipo = ?
              AND snapshot_date IN (SELECT DISTINCT CAST(snapshot_date AS DATE) FROM nodes_df)
            """,
            [tipo],
        )
        con.execute(
            """
            INSERT INTO dependencia (dep_id, tipo, snapshot_date, geom)
            SELECT ? || '-' || CAST(_row_no AS VARCHAR), ?, CAST(snapshot_date AS DATE),
                   ST_GeomFromWKB(geom_wkb)
            FROM nodes_df
            """,
            [layer, tipo],
        )
        con.unregister("nodes_df")


def _to_wkb(gdf: gpd.GeoDataFrame) -> pd.DataFrame:
    """Drop the geometry column in favour of a plain WKB column DuckDB can read."""
    df = gdf.copy()
    df["geom_wkb"] = df.geometry.to_wkb()
    df["_row_no"] = range(len(df))
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
