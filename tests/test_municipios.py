"""Station→municipio geocoding. Offline: synthetic polygons, no boundaries download."""

from __future__ import annotations

import geopandas as gpd
from shapely.geometry import Point, Polygon

from redferro.sources.municipios import geocode_points


def _square(cx: float, cy: float, r: float = 1.0) -> Polygon:
    return Polygon([(cx - r, cy - r), (cx + r, cy - r), (cx + r, cy + r), (cx - r, cy + r)])


def _muni() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {
            "mun_name": ["Alfa", "Beta"],
            "mun_code": ["00001", "00002"],
            "prov_name": ["ProvA", "ProvB"],
            "acom_name": ["ComA", "ComB"],
        },
        geometry=[_square(0, 0), _square(10, 10)],
        crs="EPSG:25830",
    )


def _points() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {"dep_id": ["inside_a", "inside_b", "far"]},
        geometry=[Point(0.2, 0.2), Point(10.1, 9.9), Point(3.0, 0.0)],
        crs="EPSG:25830",
    )


def test_containment_assigns_the_enclosing_municipio():
    out = geocode_points(_points(), _muni())
    assert out.loc[0, "municipio"] == "Alfa"
    assert out.loc[0, "provincia"] == "ProvA"
    assert out.loc[0, "geocode_match"] == "within"
    assert out.loc[0, "dist_m"] == 0.0
    assert out.loc[1, "municipio"] == "Beta"


def test_outside_point_falls_back_to_nearest_and_is_flagged():
    out = geocode_points(_points(), _muni())
    # (3,0) is 2 m east of Alfa's edge at x=1; nearest, not within
    assert out.loc[2, "municipio"] == "Alfa"
    assert out.loc[2, "geocode_match"] == "nearest"
    assert out.loc[2, "dist_m"] > 0


def test_one_row_per_input_point_in_order():
    pts = _points()
    out = geocode_points(pts, _muni())
    assert list(out.index) == list(pts.index)
    assert list(out.columns) == ["municipio", "provincia", "ccaa", "geocode_match", "dist_m"]
