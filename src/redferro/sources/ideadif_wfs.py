"""Download the INSPIRE Railway Transport Network from the IDEAdif WFS.

The service (https://ideadif.adif.es/services/wfs, deegree, INSPIRE Annex I
Transport Networks) exposes three feature types:

    TN.RailTransportNetwork.RailwayLink         (tramos / edges, LineString)
    TN.RailTransportNetwork.RailwayNode          (nodes, Point)
    TN.RailTransportNetwork.RailwayStationNode   (stations, Point)

Native CRS is EPSG:25830 (ETRS89 UTM30N). It is a *current snapshot* — versioned
by Adif (July 2024 at time of writing), NOT a historical archive. Snapshots are
therefore stamped with the fetch date so the pipeline can keep a rolling panel.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import geopandas as gpd
import requests

from redferro.config import settings

FEATURE_TYPES: dict[str, str] = {
    "railway_link": "TN.RailTransportNetwork.RailwayLink",
    "railway_node": "TN.RailTransportNetwork.RailwayNode",
    "railway_station_node": "TN.RailTransportNetwork.RailwayStationNode",
}


def _getfeature_url(type_name: str, srs: str, output_format: str) -> tuple[str, dict[str, str]]:
    params = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeNames": type_name,
        "srsName": srs,
        "outputFormat": output_format,
    }
    return settings.ideadif_wfs, params


def fetch_feature_type(
    key: str,
    *,
    srs: str | None = None,
    timeout: int = 120,
) -> gpd.GeoDataFrame:
    """Fetch one feature type as a GeoDataFrame.

    deegree advertises GML by default; many builds also serve GeoJSON as
    'application/json'. We try GeoJSON first (simplest to parse) and fall back
    to GML 3.2 read via pyogrio.
    """
    type_name = FEATURE_TYPES[key]
    srs = srs or settings.crs_storage

    # 1) try GeoJSON
    url, params = _getfeature_url(type_name, srs, "application/json")
    r = requests.get(url, params=params, timeout=timeout)
    if r.ok and r.headers.get("content-type", "").startswith("application/json"):
        gdf = gpd.read_file(r.text)
        return gdf.set_crs(srs, allow_override=True)

    # 2) fall back to GML
    url, params = _getfeature_url(type_name, srs, "text/xml; subtype=gml/3.2.1")
    r = requests.get(url, params=params, timeout=timeout)
    r.raise_for_status()
    tmp = settings.raw / "_wfs_tmp.gml"
    tmp.write_bytes(r.content)
    gdf = gpd.read_file(tmp)
    tmp.unlink(missing_ok=True)
    return gdf.set_crs(srs, allow_override=True)


def fetch_all(stamp: str | None = None) -> Path:
    """Fetch all three feature types into a single stamped GeoPackage.

    Returns the path to data/raw/ideadif_<stamp>.gpkg. Each layer is written
    with a `snapshot_date` column so multiple fetches build a temporal panel.
    """
    stamp = stamp or dt.date.today().isoformat()
    settings.raw.mkdir(parents=True, exist_ok=True)
    out = settings.raw / f"ideadif_{stamp}.gpkg"

    for key in FEATURE_TYPES:
        gdf = fetch_feature_type(key)
        gdf["snapshot_date"] = stamp
        gdf.to_file(out, layer=key, driver="GPKG")
    return out
