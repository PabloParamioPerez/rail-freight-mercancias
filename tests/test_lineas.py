"""Line-level product builders. Offline: synthetic DuckDB + injected reference frames."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from redferro.analysis.lineas import build_line_catalogue, build_station_tables
from redferro.db.duckdb_io import init_schema, load_snapshot_gpkg

RFIG = pd.DataFrame(
    {
        "numero_rfig": ["710"],
        "wiki_linea": ["Castejón de Ebro a Alsasua"],
        "wiki_longitud": ["100,0 km"],
        "wiki_ancho": ["Ibérico"],
        "wiki_historica": [False],
    }
)

# The two named tramo endpoints in the fixture (TN_RailwayNode_* ids).
GEO = pd.DataFrame(
    {
        "dep_id": ["TN_RailwayNode_80103", "TN_RailwayNode_80106"],
        "municipio": ["Altsasu", "Olazti"],
        "provincia": ["Navarra", "Navarra"],
        "ccaa": ["Navarra", "Navarra"],
        "geocode_match": ["within", "within"],
        "dist_m": [0.0, 0.0],
    }
)


def test_catalogue_joins_rfig_numbering_and_counts_uso(
    duck: duckdb.DuckDBPyConnection, snapshot_gpkg: Path
):
    init_schema(duck)
    load_snapshot_gpkg(duck, snapshot_gpkg)
    cat = build_line_catalogue(duck, RFIG)

    assert list(cat.codigo_linea) == ["01710"]
    row = cat.iloc[0]
    assert row.numero_rfig == "710"  # último-3 of the código
    assert row.wiki_linea == "Castejón de Ebro a Alsasua"  # RFIG join landed
    assert row.wiki_ancho == "Ibérico"
    assert row.n_solo_carga == 1 and row.n_mixto == 1
    assert bool(row.apto_mercancias) is True


def test_station_tables_attach_municipio_and_list_cities(
    duck: duckdb.DuckDBPyConnection, snapshot_gpkg: Path
):
    init_schema(duck)
    load_snapshot_gpkg(duck, snapshot_gpkg)
    estaciones, ciudades = build_station_tables(duck, GEO)

    assert set(estaciones.municipio.dropna()) == {"Altsasu", "Olazti"}
    assert "municipio" in estaciones.columns and "geocode_match" in estaciones.columns

    line = ciudades.iloc[0]
    assert line.codigo_linea == "01710"
    assert line.n_municipios == 2
    assert set(line.municipios.split(" > ")) == {"Altsasu", "Olazti"}
