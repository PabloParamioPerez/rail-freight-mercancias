"""Schema packaging and snapshot loading. Offline (see conftest for the spatial caveat)."""

from __future__ import annotations

import datetime as dt
from importlib.resources import files
from pathlib import Path

import duckdb
import geopandas as gpd
import pytest
from shapely.geometry import Point

from redferro.db.duckdb_io import _to_wkb, init_schema, load_snapshot_gpkg


def test_schema_sql_is_packaged():
    """init_schema resolves schema.sql via importlib.resources, so it must ship."""
    sql = (files("redferro.db") / "schema.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS tramo" in sql
    assert "v_red_mercancias" in sql


def test_to_wkb_drops_geometry_and_numbers_rows():
    gdf = gpd.GeoDataFrame(
        {"snapshot_date": ["2026-01-01", "2026-01-01"]},
        geometry=[Point(0, 0), Point(1, 1)],
        crs="EPSG:25830",
    )
    out = _to_wkb(gdf)

    assert "geometry" not in out.columns
    assert out["_row_no"].tolist() == [0, 1]
    assert out["geom_wkb"].notna().all()
    # must be a plain DataFrame for con.register
    assert not isinstance(out, gpd.GeoDataFrame)


def test_init_schema_creates_tables_and_view(duck: duckdb.DuckDBPyConnection):
    """Also proves con.execute() accepts the multi-statement schema script."""
    init_schema(duck)
    names = {r[0] for r in duck.execute("SHOW TABLES").fetchall()}
    assert {"linea", "tramo", "dependencia", "habilitacion_linea"} <= names
    assert "v_red_mercancias" in names


def test_init_schema_is_rerunnable(duck: duckdb.DuckDBPyConnection):
    init_schema(duck)
    init_schema(duck)  # CREATE TABLE IF NOT EXISTS / CREATE OR REPLACE VIEW


def test_load_snapshot_keeps_both_node_layers_apart(
    duck: duckdb.DuckDBPyConnection, snapshot_gpkg: Path
):
    """Regression: both node layers number rows from 0, so an unqualified dep_id
    collides on the (dep_id, snapshot_date) primary key and the load hard-fails."""
    init_schema(duck)
    load_snapshot_gpkg(duck, snapshot_gpkg)

    total, distinct = duck.execute(
        "SELECT count(*), count(DISTINCT dep_id) FROM dependencia"
    ).fetchone()
    assert total == 4, "2 nodes + 2 station nodes should all survive"
    assert distinct == 4, "dep_id must be unique across the two node layers"

    tipos = dict(duck.execute("SELECT tipo, count(*) FROM dependencia GROUP BY tipo").fetchall())
    assert tipos == {"nodo": 2, "estacion": 2}
    assert duck.execute("SELECT count(*) FROM tramo").fetchone()[0] == 2


def test_load_snapshot_is_idempotent(duck: duckdb.DuckDBPyConnection, snapshot_gpkg: Path):
    """Re-running `redferro db build` on the same snapshot must not duplicate or raise."""
    init_schema(duck)
    load_snapshot_gpkg(duck, snapshot_gpkg)
    load_snapshot_gpkg(duck, snapshot_gpkg)

    assert duck.execute("SELECT count(*) FROM tramo").fetchone()[0] == 2
    assert duck.execute("SELECT count(*) FROM dependencia").fetchone()[0] == 4


def test_geometry_round_trips_as_storage_crs(duck: duckdb.DuckDBPyConnection, snapshot_gpkg: Path):
    init_schema(duck)
    load_snapshot_gpkg(duck, snapshot_gpkg)
    wkt = duck.execute("SELECT ST_AsText(geom) FROM tramo ORDER BY tramo_id").fetchall()
    assert wkt[0][0].startswith("LINESTRING")


def test_snapshot_date_is_stored_as_date(
    duck: duckdb.DuckDBPyConnection, snapshot_gpkg: Path, snapshot_date: dt.date
):
    init_schema(duck)
    load_snapshot_gpkg(duck, snapshot_gpkg)
    assert duck.execute("SELECT DISTINCT snapshot_date FROM tramo").fetchone()[0] == snapshot_date


@pytest.mark.parametrize("layer", ["railway_link", "railway_node", "railway_station_node"])
def test_fixture_gpkg_retains_every_layer(snapshot_gpkg: Path, layer: str):
    """Guards the multi-layer GeoPackage write that fetch_all relies on."""
    assert len(gpd.read_file(snapshot_gpkg, layer=layer)) == 2
