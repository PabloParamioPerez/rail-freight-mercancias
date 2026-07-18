"""Download the INSPIRE Railway Transport Network from the IDEAdif WFS.

The service (https://ideadif.adif.es/services/wfs, deegree, INSPIRE Annex I
Transport Networks) publishes 14 feature types under the `tn-ra:` prefix
(namespace urn:x-inspire:specification:gmlas:RailwayTransportNetwork:3.0). The
five this module uses:

    tn-ra:RailwayLink         tramos / edges, LineString      (1689 features)
    tn-ra:RailwayNode         nodes, Point                    (3386)
    tn-ra:RailwayStationNode  stations, Point                 (2682)
    tn-ra:RailwayLine         lines (name + member links)     (355, no geometry)
    tn-ra:RailwayUse          passenger/freight use per link  (1689, no geometry)

Facts established against the live service (see docs/data-sources.md):

* **GeoJSON is not offered.** The only advertised outputFormats are
  `application/gml+xml; version=3.2` and `text/xml; subtype=gml/3.2.1`;
  requesting `application/json` returns an InvalidParameterValue exception.
* **DefaultCRS is EPSG:4258**, not 25830. 25830 is offered as an alternate CRS
  and is what we request, so the project's storage-CRS convention still holds.
* Link/node topology lives in `net:startNode` / `net:endNode`, which are
  `xlink:href` *references* carrying the node id in an `ID=` query parameter.
  GDAL only surfaces those with `GML_ATTRIBUTES_TO_OGR_FIELDS=YES`.

It is a *current snapshot* (versionId 2026/01 at time of writing), NOT a
historical archive, so snapshots are stamped with the fetch date.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import os
import re
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests

from redferro.config import settings

# Geometry-bearing feature types, written as GeoPackage layers.
FEATURE_TYPES: dict[str, str] = {
    "railway_link": "tn-ra:RailwayLink",
    "railway_node": "tn-ra:RailwayNode",
    "railway_station_node": "tn-ra:RailwayStationNode",
}

# Attribute-only feature types, folded into the link layer as columns.
LINE_TYPE = "tn-ra:RailwayLine"
USE_TYPE = "tn-ra:RailwayUse"

GML_FORMAT = "text/xml; subtype=gml/3.2.1"

# Node/link references are GetFeatureById URLs; the id sits in the ID= parameter.
# Anchored on [?&] so it cannot match STOREDQUERY_ID=.
_HREF_ID = re.compile(r"[?&]ID=([^&#]+)")

# GDAL emits <Type>Untyped</Type> for elements it cannot infer and <Type>*List</Type>
# for repeated ones. pyogrio cannot put either in a flat column and raises
# "setting an array element with a sequence", so they are stripped from the schema.
_UNREADABLE_PROPERTY = re.compile(
    r"\s*<PropertyDefn>(?:(?!</PropertyDefn>).)*?<Type>(?:Untyped|\w*List)</Type>.*?</PropertyDefn>",
    re.S,
)


def _getfeature_url(type_name: str, srs: str | None = None) -> tuple[str, dict[str, str]]:
    params = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeNames": type_name,
        "outputFormat": GML_FORMAT,
    }
    if srs:
        params["srsName"] = srs
    return settings.ideadif_wfs, params


def _get_gml(type_name: str, srs: str | None, timeout: int) -> bytes:
    url, params = _getfeature_url(type_name, srs)
    r = requests.get(url, params=params, timeout=timeout)
    r.raise_for_status()
    if b"ExceptionReport" in r.content[:2000]:
        text = re.search(rb"<ows:ExceptionText>(.*?)</ows:ExceptionText>", r.content, re.S)
        detail = text.group(1).decode("utf-8", "replace").strip() if text else "unknown"
        raise RuntimeError(f"WFS returned an exception for {type_name}: {detail}")
    return r.content


def _read_gml(path: Path) -> gpd.GeoDataFrame:
    """Read a GML file, working around GDAL's schema inference.

    GDAL writes a sidecar `.gfs` describing the fields it found. Repeated and
    untyped elements land there as types pyogrio cannot represent, so we let GDAL
    write the schema, strip those entries, and read again against the cleaned one.
    """
    gfs = path.with_suffix(".gfs")
    gfs.unlink(missing_ok=True)
    # This probe read is expected to fail on exactly the fields we are about to
    # strip; it is run only for its side effect of making GDAL write the .gfs.
    with contextlib.suppress(Exception):
        gpd.read_file(path, rows=1)
    if gfs.exists():
        gfs.write_text(_UNREADABLE_PROPERTY.sub("", gfs.read_text()))
    return gpd.read_file(path)


def fetch_feature_type(
    key: str,
    *,
    srs: str | None = None,
    timeout: int = 300,
) -> gpd.GeoDataFrame:
    """Fetch one geometry-bearing feature type as a GeoDataFrame."""
    srs = srs or settings.crs_storage
    content = _get_gml(FEATURE_TYPES[key], srs, timeout)
    # GML_ATTRIBUTES_TO_OGR_FIELDS exposes xlink:href attributes (startNode/endNode)
    # as fields; without it the topology is invisible and the graph has no edges.
    previous = os.environ.get("GML_ATTRIBUTES_TO_OGR_FIELDS")
    os.environ["GML_ATTRIBUTES_TO_OGR_FIELDS"] = "YES"
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir) / "wfs.gml"
            tmp.write_bytes(content)
            gdf = _read_gml(tmp)
    finally:
        if previous is None:
            os.environ.pop("GML_ATTRIBUTES_TO_OGR_FIELDS", None)
        else:
            os.environ["GML_ATTRIBUTES_TO_OGR_FIELDS"] = previous
    return gdf.set_crs(srs, allow_override=True)


def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _iter_features(content: bytes, feature: str) -> list[ET.Element]:
    root = ET.fromstring(content)
    return [el for el in root.iter() if _localname(el.tag) == feature]


def parse_link_use(content: bytes) -> pd.DataFrame:
    """RailwayUse GML -> one row per link: which traffic the tramo carries.

    Observed values across the full set: 'mixed' (904), 'cargo' (402),
    'pasagens' (138 - the typo is Adif's, in the source data).
    """
    rows: list[dict[str, str]] = []
    for feat in _iter_features(content, "RailwayUse"):
        use = next((e.text for e in feat.iter() if _localname(e.tag) == "use"), None)
        link = None
        for el in feat.iter():
            if _localname(el.tag) == "element":
                href = next((v for k, v in el.attrib.items() if _localname(k) == "href"), "")
                match = _HREF_ID.search(href)
                if match:
                    link = match.group(1)
                break
        if link and use:
            rows.append({"link_gml_id": link, "uso": use})
    return pd.DataFrame(rows, columns=["link_gml_id", "uso"])


def fetch_link_use(timeout: int = 300) -> pd.DataFrame:
    return parse_link_use(_get_gml(USE_TYPE, None, timeout))


def parse_line_membership(content: bytes) -> pd.DataFrame:
    """RailwayLine GML -> one row per (link, line): the authoritative link->linea map.

    Uses the explicit `net:link` references rather than slicing the link id, even
    though `RailwayLink_017100070` does embed line `01710`.
    """
    rows: list[dict[str, str]] = []
    for feat in _iter_features(content, "RailwayLine"):
        line_id = next(
            (e.text for e in feat.iter() if _localname(e.tag) == "localId"),
            None,
        )
        name = next((e.text for e in feat.iter() if _localname(e.tag) == "name"), None)
        if not line_id:
            continue
        for el in feat.iter():
            if _localname(el.tag) != "link":
                continue
            href = next((v for k, v in el.attrib.items() if _localname(k) == "href"), "")
            match = _HREF_ID.search(href)
            if match:
                rows.append(
                    {
                        "link_gml_id": match.group(1),
                        "linea_id": line_id.replace("RailwayLine_", ""),
                        "linea_nombre": name or "",
                    }
                )
    return pd.DataFrame(rows, columns=["link_gml_id", "linea_id", "linea_nombre"])


def fetch_line_membership(timeout: int = 300) -> pd.DataFrame:
    return parse_line_membership(_get_gml(LINE_TYPE, None, timeout))


def _node_id(href: object) -> str | None:
    if not isinstance(href, str):
        return None
    match = _HREF_ID.search(href)
    return match.group(1) if match else None


def enrich_links(
    links: gpd.GeoDataFrame, use: pd.DataFrame, lines: pd.DataFrame
) -> gpd.GeoDataFrame:
    """Resolve topology hrefs to node ids and attach uso / linea columns."""
    out = links.copy()
    out["nodo_ini"] = out.get("startNode_href", pd.Series(dtype=object)).map(_node_id)
    out["nodo_fin"] = out.get("endNode_href", pd.Series(dtype=object)).map(_node_id)

    if not use.empty:
        out = out.merge(use, how="left", left_on="gml_id", right_on="link_gml_id").drop(
            columns=["link_gml_id"], errors="ignore"
        )
    if not lines.empty:
        # A link can appear under more than one line; keep the first deterministically.
        first = lines.sort_values(["link_gml_id", "linea_id"]).drop_duplicates("link_gml_id")
        out = out.merge(first, how="left", left_on="gml_id", right_on="link_gml_id").drop(
            columns=["link_gml_id"], errors="ignore"
        )
    return out


def fetch_all(stamp: str | None = None) -> Path:
    """Fetch the network into a single stamped GeoPackage.

    Returns the path to data/raw/ideadif_<stamp>.gpkg. Each layer carries a
    `snapshot_date` column so repeated fetches build a temporal panel. The
    `railway_link` layer is enriched with nodo_ini/nodo_fin (resolved topology),
    `uso` and `linea_id`/`linea_nombre`.
    """
    stamp = stamp or dt.date.today().isoformat()
    settings.raw.mkdir(parents=True, exist_ok=True)
    out = settings.raw / f"ideadif_{stamp}.gpkg"

    use = fetch_link_use()
    lines = fetch_line_membership()

    for key in FEATURE_TYPES:
        gdf = fetch_feature_type(key)
        if key == "railway_link":
            gdf = enrich_links(gdf, use, lines)
        gdf["snapshot_date"] = stamp
        gdf.to_file(out, layer=key, driver="GPKG")
    return out
