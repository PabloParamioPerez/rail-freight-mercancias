"""Attribute mapping from the real IDEAdif GML. Offline: no service calls.

The GML fragments below are trimmed copies of real GetFeature responses, so the
parsers are exercised against the shapes the service actually returns.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import geopandas as gpd
import pytest

from redferro.db.duckdb_io import init_schema, load_snapshot_gpkg
from redferro.sources.ideadif_wfs import (
    _HREF_ID,
    FEATURE_TYPES,
    _node_id,
    enrich_links,
    parse_line_membership,
    parse_link_use,
)

# The node id sits in ID=, but STOREDQUERY_ID= appears earlier in the same URL.
REAL_HREF = (
    "https://ideadif.adif.es:443/services/wfs?SERVICE=WFS&VERSION=2.0.0"
    "&REQUEST=GetFeature&OUTPUTFORMAT=application%2Fgml%2Bxml%3B+version%3D3.2"
    "&STOREDQUERY_ID=urn:ogc:def:query:OGC-WFS::GetFeatureById"
    "&ID=TN_RailwayNode_80108#TN_RailwayNode_80108"
)


def test_feature_type_names_match_the_service():
    """The service advertises tn-ra:*, not the TN.RailTransportNetwork.* guess."""
    assert FEATURE_TYPES == {
        "railway_link": "tn-ra:RailwayLink",
        "railway_node": "tn-ra:RailwayNode",
        "railway_station_node": "tn-ra:RailwayStationNode",
    }


def test_href_id_is_anchored_past_storedquery_id():
    """Regression: an unanchored ID= match returns the stored-query URN instead."""
    assert _HREF_ID.search(REAL_HREF).group(1) == "TN_RailwayNode_80108"
    assert _node_id(REAL_HREF) == "TN_RailwayNode_80108"


@pytest.mark.parametrize("value", [None, float("nan"), 123, "no-id-here"])
def test_node_id_tolerates_junk(value):
    assert _node_id(value) is None


USE_GML = b"""<?xml version="1.0" encoding="UTF-8"?>
<wfs:FeatureCollection xmlns:wfs="http://www.opengis.net/wfs/2.0"
  xmlns:tn-ra="urn:x-inspire:specification:gmlas:RailwayTransportNetwork:3.0"
  xmlns:net="urn:x-inspire:specification:gmlas:Network:3.2"
  xmlns:xlink="http://www.w3.org/1999/xlink">
  <wfs:member><tn-ra:RailwayUse>
    <net:networkRef><net:LinkReference>
      <net:element xlink:href="x?STOREDQUERY_ID=urn:ogc&amp;ID=TN_RailwayLink_011020010#f"/>
    </net:LinkReference></net:networkRef>
    <tn-ra:use>cargo</tn-ra:use>
  </tn-ra:RailwayUse></wfs:member>
  <wfs:member><tn-ra:RailwayUse>
    <net:networkRef><net:LinkReference>
      <net:element xlink:href="x?STOREDQUERY_ID=urn:ogc&amp;ID=TN_RailwayLink_011020020#f"/>
    </net:LinkReference></net:networkRef>
    <tn-ra:use>pasagens</tn-ra:use>
  </tn-ra:RailwayUse></wfs:member>
</wfs:FeatureCollection>"""

LINE_GML = b"""<?xml version="1.0" encoding="UTF-8"?>
<wfs:FeatureCollection xmlns:wfs="http://www.opengis.net/wfs/2.0"
  xmlns:tn-ra="urn:x-inspire:specification:gmlas:RailwayTransportNetwork:3.0"
  xmlns:net="urn:x-inspire:specification:gmlas:Network:3.2"
  xmlns:base="urn:x-inspire:specification:gmlas:BaseTypes:3.2"
  xmlns:gml="http://www.opengis.net/gml/3.2"
  xmlns:xlink="http://www.w3.org/1999/xlink">
  <wfs:member><tn-ra:RailwayLine>
    <gml:name>ALTSASU-CASTEJON DE EBRO</gml:name>
    <net:inspireId><base:Identifier>
      <base:localId>RailwayLine_01710</base:localId>
    </base:Identifier></net:inspireId>
    <net:link xlink:href="x?STOREDQUERY_ID=urn:ogc&amp;ID=TN_RailwayLink_017100070#f"/>
    <net:link xlink:href="x?STOREDQUERY_ID=urn:ogc&amp;ID=TN_RailwayLink_017100050#f"/>
  </tn-ra:RailwayLine></wfs:member>
</wfs:FeatureCollection>"""


def test_parse_link_use_keeps_adif_vocabulary():
    df = parse_link_use(USE_GML)
    assert dict(zip(df.link_gml_id, df.uso, strict=True)) == {
        "TN_RailwayLink_011020010": "cargo",
        "TN_RailwayLink_011020020": "pasagens",
    }


def test_parse_line_membership_expands_every_link_reference():
    df = parse_line_membership(LINE_GML)
    assert len(df) == 2
    assert set(df.link_gml_id) == {"TN_RailwayLink_017100070", "TN_RailwayLink_017100050"}
    assert set(df.linea_id) == {"01710"}
    assert df.linea_nombre.iloc[0] == "ALTSASU-CASTEJON DE EBRO"


def test_parsers_return_typed_empty_frames_on_empty_input():
    empty = (
        b'<?xml version="1.0"?><wfs:FeatureCollection xmlns:wfs="http://www.opengis.net/wfs/2.0"/>'
    )
    assert list(parse_link_use(empty).columns) == ["link_gml_id", "uso"]
    assert list(parse_line_membership(empty).columns) == [
        "link_gml_id",
        "linea_id",
        "linea_nombre",
    ]


def test_enrich_links_resolves_topology_and_joins_attributes():
    import pandas as pd
    from shapely.geometry import LineString

    links = gpd.GeoDataFrame(
        {
            "gml_id": ["TN_RailwayLink_A", "TN_RailwayLink_B"],
            "startNode_href": [REAL_HREF, None],
            "endNode_href": [REAL_HREF, REAL_HREF],
        },
        geometry=[LineString([(0, 0), (1, 1)])] * 2,
        crs="EPSG:25830",
    )
    use = pd.DataFrame({"link_gml_id": ["TN_RailwayLink_A"], "uso": ["cargo"]})
    lines = pd.DataFrame(
        {
            "link_gml_id": ["TN_RailwayLink_A"],
            "linea_id": ["01710"],
            "linea_nombre": ["ALTSASU-CASTEJON DE EBRO"],
        }
    )
    out = enrich_links(links, use, lines)

    assert out.loc[0, "nodo_ini"] == "TN_RailwayNode_80108"
    assert out.loc[0, "uso"] == "cargo"
    assert out.loc[0, "linea_id"] == "01710"
    # An unresolved reference stays missing rather than becoming a bogus id; DuckDB
    # writes both None and NaN into a VARCHAR column as a real NULL (verified), so
    # this never lands as the literal string "nan".
    assert pd.isna(out.loc[1, "nodo_ini"])
    assert pd.isna(out.loc[1, "uso"])
    assert "link_gml_id" not in out.columns


def test_uso_vocabulary_is_translated(duck: duckdb.DuckDBPyConnection, snapshot_gpkg: Path):
    """Adif ships cargo/mixed/pasagens; the schema stores mercancias/mixto/viajeros."""
    init_schema(duck)
    load_snapshot_gpkg(duck, snapshot_gpkg)
    usos = dict(duck.execute("SELECT uso, count(*) FROM tramo GROUP BY uso").fetchall())
    assert usos == {"mercancias": 1, "mixto": 1}


def test_linea_is_populated_and_view_returns_freight(
    duck: duckdb.DuckDBPyConnection, snapshot_gpkg: Path
):
    init_schema(duck)
    load_snapshot_gpkg(duck, snapshot_gpkg)

    linea = duck.execute("SELECT linea_id, nombre, uso FROM linea").fetchall()
    assert linea == [("01710", "ALTSASU-CASTEJON DE EBRO", "mercancias")]
    # both tramos are freight-relevant (cargo + mixto)
    assert duck.execute("SELECT count(*) FROM v_red_mercancias").fetchone()[0] == 2


def test_topology_joins_dependencia(duck: duckdb.DuckDBPyConnection, snapshot_gpkg: Path):
    """The whole point: tramo endpoints must resolve to real dependencia rows."""
    init_schema(duck)
    load_snapshot_gpkg(duck, snapshot_gpkg)
    resolved = duck.execute(
        """
        SELECT count(d.dep_id) FROM tramo t
        JOIN dependencia d ON d.dep_id = t.nodo_ini
        """
    ).fetchone()[0]
    assert resolved >= 1, "nodo_ini must join dependencia.dep_id"


def test_station_names_are_stored(duck: duckdb.DuckDBPyConnection, snapshot_gpkg: Path):
    init_schema(duck)
    load_snapshot_gpkg(duck, snapshot_gpkg)
    names = {r[0] for r in duck.execute("SELECT nombre FROM dependencia").fetchall()}
    assert "ALTSASU" in names
