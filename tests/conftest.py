"""Shared fixtures.

Every test in this suite is offline — nothing here touches ideadif.adif.es. The one
exception is DuckDB's spatial extension, which downloads from extensions.duckdb.org on
first install; tests needing it use the `duck` fixture, which skips when unavailable.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import duckdb
import geopandas as gpd
import pytest
from shapely.geometry import LineString, Point

SNAPSHOT = dt.date(2026, 1, 1)


@pytest.fixture
def snapshot_date() -> dt.date:
    """The date stamped into the `snapshot_gpkg` fixture."""
    return SNAPSHOT


@pytest.fixture
def duck(tmp_path: Path) -> duckdb.DuckDBPyConnection:
    """A DuckDB connection with the spatial extension, or skip."""
    con = duckdb.connect(str(tmp_path / "test.duckdb"))
    try:
        con.execute("INSTALL spatial; LOAD spatial;")
    except duckdb.Error as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"duckdb spatial extension unavailable: {exc}")
    yield con
    con.close()


@pytest.fixture
def snapshot_gpkg(tmp_path: Path) -> Path:
    """A synthetic IDEAdif-shaped GeoPackage, mirroring what `fetch_all` writes.

    Column names and id formats copy the real service (localId RailwayLink_*,
    gml_id TN_RailwayNode_*, Adif's own `use` vocabulary including the 'pasagens'
    typo) so the loader is exercised against the shapes it really meets.

    Two tramos on line 01710: one cargo-only, one mixed, sharing node 80106 so the
    pair is adjacent. Both node layers carry ids that would collide if dep_id were
    not qualified per layer.
    """
    stamp = SNAPSHOT.isoformat()
    out = tmp_path / f"ideadif_{stamp}.gpkg"
    layers = {
        "railway_link": gpd.GeoDataFrame(
            {
                "localId": ["RailwayLink_017100050", "RailwayLink_017100060"],
                "gml_id": ["TN_RailwayLink_017100050", "TN_RailwayLink_017100060"],
                "nodo_ini": ["TN_RailwayNode_80103", "TN_RailwayNode_80106"],
                "nodo_fin": ["TN_RailwayNode_80106", "TN_RailwayNode_80108"],
                "uso": ["cargo", "mixed"],
                "linea_id": ["01710", "01710"],
                "linea_nombre": ["ALTSASU-CASTEJON DE EBRO"] * 2,
                "snapshot_date": [stamp, stamp],
            },
            geometry=[LineString([(0, 0), (1, 1)]), LineString([(1, 1), (2, 2)])],
            crs="EPSG:25830",
        ),
        "railway_node": gpd.GeoDataFrame(
            {
                "gml_id": ["TN_RailwayNode_80103", "TN_RailwayNode_80106"],
                "name": ["ALTSASU", "OLAZAGUTIA"],
                "snapshot_date": [stamp, stamp],
            },
            geometry=[Point(0, 0), Point(1, 1)],
            crs="EPSG:25830",
        ),
        "railway_station_node": gpd.GeoDataFrame(
            {
                "gml_id": ["TN_RailwayStationNode_80106", "TN_RailwayStationNode_80108"],
                "name": ["OLAZAGUTIA", "ALSASUA"],
                "snapshot_date": [stamp, stamp],
            },
            geometry=[Point(1, 1), Point(2, 2)],
            crs="EPSG:25830",
        ),
    }
    for layer, gdf in layers.items():
        gdf.to_file(out, layer=layer, driver="GPKG")
    return out
