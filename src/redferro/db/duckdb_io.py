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
    """Load one stamped IDEAdif GeoPackage into linea/tramo/dependencia tables.

    Reads via geopandas, hands WKB to DuckDB. Re-loading the same snapshot is
    idempotent: rows for the incoming snapshot_date are deleted first.

    Identifiers come from INSPIRE `localId` (e.g. RailwayLink_017100070,
    TN_RailwayNode_80108), so they are stable across fetches and the temporal
    panel lines up snapshot to snapshot. Topology (nodo_ini/nodo_fin) is resolved
    upstream in sources.ideadif_wfs from the startNode/endNode xlink references.

    Adif's `use` vocabulary is mapped onto the schema's Spanish vocabulary:
    cargo -> mercancias, pasagens (sic) -> viajeros, mixed -> mixto.
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
        INSERT INTO tramo (tramo_id, linea_id, nodo_ini, nodo_fin, uso, snapshot_date, geom)
        SELECT localId,
               linea_id,
               nodo_ini,
               nodo_fin,
               CASE uso WHEN 'cargo' THEN 'mercancias'
                        WHEN 'pasagens' THEN 'viajeros'
                        WHEN 'mixed' THEN 'mixto'
                        ELSE uso END,
               CAST(snapshot_date AS DATE),
               ST_GeomFromWKB(geom_wkb)
        FROM links_df
        """
    )

    # linea: one row per (linea, year), derived from the snapshot. A line counts as
    # freight-relevant if any of its tramos carries cargo; otherwise mixed, else
    # passenger-only. Aggregated here because Adif classifies use per link, not per line.
    con.execute(
        """
        DELETE FROM linea
        WHERE anio IN (SELECT DISTINCT year(CAST(snapshot_date AS DATE)) FROM links_df)
          AND fuente = 'ideadif_wfs'
        """
    )
    con.execute(
        """
        INSERT INTO linea (linea_id, anio, nombre, uso, fuente)
        SELECT linea_id,
               year(CAST(min(snapshot_date) AS DATE)),
               max(linea_nombre),
               CASE WHEN bool_or(uso = 'cargo')    THEN 'mercancias'
                    WHEN bool_or(uso = 'mixed')    THEN 'mixto'
                    WHEN bool_or(uso = 'pasagens') THEN 'viajeros'
                    ELSE NULL END,
               'ideadif_wfs'
        FROM links_df
        WHERE linea_id IS NOT NULL
        GROUP BY linea_id
        """
    )
    con.unregister("links_df")

    for layer, tipo in (("railway_node", "nodo"), ("railway_station_node", "estacion")):
        gdf = gpd.read_file(gpkg, layer=layer)
        con.register("nodes_df", _to_wkb(gdf))
        con.execute(
            """
            DELETE FROM dependencia
            WHERE tipo = ?
              AND snapshot_date IN (SELECT DISTINCT CAST(snapshot_date AS DATE) FROM nodes_df)
            """,
            [tipo],
        )
        # dep_id uses gml_id (TN_RailwayNode_80108), which is exactly what the link
        # startNode/endNode references resolve to, so tramo joins dependencia directly.
        con.execute(
            """
            INSERT INTO dependencia (dep_id, nombre, tipo, snapshot_date, geom)
            SELECT gml_id, name, ?, CAST(snapshot_date AS DATE),
                   ST_GeomFromWKB(geom_wkb)
            FROM nodes_df
            """,
            [tipo],
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
