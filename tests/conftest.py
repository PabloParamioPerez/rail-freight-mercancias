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
    """A synthetic IDEAdif-shaped GeoPackage with all three layers.

    Both node layers deliberately number their rows from 0, which is what makes the
    dep_id primary-key collision reproducible.
    """
    stamp = SNAPSHOT.isoformat()
    out = tmp_path / f"ideadif_{stamp}.gpkg"
    layers = {
        "railway_link": gpd.GeoDataFrame(
            {"snapshot_date": [stamp, stamp]},
            geometry=[LineString([(0, 0), (1, 1)]), LineString([(1, 1), (2, 2)])],
            crs="EPSG:25830",
        ),
        "railway_node": gpd.GeoDataFrame(
            {"snapshot_date": [stamp, stamp]},
            geometry=[Point(0, 0), Point(1, 1)],
            crs="EPSG:25830",
        ),
        "railway_station_node": gpd.GeoDataFrame(
            {"snapshot_date": [stamp, stamp]},
            geometry=[Point(1, 1), Point(2, 2)],
            crs="EPSG:25830",
        ),
    }
    for layer, gdf in layers.items():
        gdf.to_file(out, layer=layer, driver="GPKG")
    return out
