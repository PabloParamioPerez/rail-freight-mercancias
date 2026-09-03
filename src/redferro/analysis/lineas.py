"""Per-line reviewer products: line catalogue, ordered stations, and the city list.

Three CSVs are produced from the DuckDB store plus two reference joins (RFIG numbering
and station→municipio geocoding):

- ``lineas.csv``            one row per línea: RFIG número, name, gauge, uso mix, length.
- ``lineas_estaciones.csv`` one row per station node on a line: name + geocoded municipio.
- ``lineas_ciudades.csv``   one row per línea: the ordered, de-duplicated municipio list.

Station order along a line is *geographic-approximate*: nodes are projected onto the
line's principal axis (the direction between its two farthest-apart nodes). That is exact
for a corridor and a reasonable linearisation for a branching line — it is not a
guaranteed operational stop sequence. See ``data/README.md``.
"""

from __future__ import annotations

import re
from pathlib import Path

import duckdb
import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

from redferro.config import settings
from redferro.db.duckdb_io import connect
from redferro.sources.municipios import fetch_municipios, geocode_points, load_municipios
from redferro.sources.rfig import load_rfig

# A named node is an operating/technical point, not a locality, when it matches this.
_TECH = re.compile(
    r"\b(BIF\.?|BIFURCACION|AGUJA|AG\.\s?KM|CAMBIADOR|KM\.?\s?\d|K\.?M\.?\s?\d|P\.?K\.?\s?\d|"
    r"PK\b|CARGADERO|APT\b|APD\b|EMPALME|EMP\.|DERIVACION|PARTICULAR|CLASIF|TRIANGULO|"
    r"PUESTO|BANALIZ|PT\.?\s?BAN|\bRIO\b|\bCTT\b|BASE DE MONTAJE|\bTUNEL\b|VARIANTE|"
    r"\bRAMAL\b|\bENLACE\b|\bACCESO\b|TERMINAL|\bAG\.\b|FRONTERA|LIMITE|BIFURC)",
    re.I,
)


def _order_along_axis(pts: np.ndarray) -> np.ndarray:
    """Indices that sort points along the line's principal (longest) axis."""
    if len(pts) <= 2:
        return np.arange(len(pts))
    dist = np.linalg.norm(pts[:, None, :] - pts[None, :, :], axis=-1)
    i, j = np.unravel_index(np.argmax(dist), dist.shape)
    axis = pts[j] - pts[i]
    norm = np.linalg.norm(axis)
    if norm == 0:
        return np.arange(len(pts))
    return np.argsort((pts - pts[i]) @ (axis / norm), kind="stable")


def _newest(con: duckdb.DuckDBPyConnection) -> str:
    return "(SELECT max(snapshot_date) FROM tramo)"


def geocode_stations(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Geocode every station node used by a tramo to its municipio; cache to interim."""
    st = con.execute(
        f"""
        SELECT DISTINCT d.dep_id, d.nombre, ST_AsWKB(d.geom) AS wkb
        FROM tramo t
        JOIN dependencia d ON d.dep_id IN (t.nodo_ini, t.nodo_fin)
        WHERE t.snapshot_date = {_newest(con)} AND d.geom IS NOT NULL
        """
    ).df()
    points = gpd.GeoDataFrame(
        st.drop(columns="wkb"),
        geometry=shapely.from_wkb(st["wkb"].apply(bytes)),
        crs=settings.crs_storage,
    )
    muni = load_municipios(fetch_municipios())
    geo = points[["dep_id", "nombre"]].join(geocode_points(points, muni))
    settings.interim.mkdir(parents=True, exist_ok=True)
    geo.to_parquet(settings.interim / "station_municipio.parquet", index=False)
    return geo


def build_line_catalogue(
    con: duckdb.DuckDBPyConnection, rfig: pd.DataFrame | None = None
) -> pd.DataFrame:
    """One row per línea: uso mix and geometry-derived length, joined to RFIG numbering."""
    rfig = load_rfig() if rfig is None else rfig
    df = con.execute(
        f"""
        SELECT l.linea_id AS codigo_linea, l.nombre, l.uso AS uso_dominante,
               count(*) AS n_tramos,
               count(*) FILTER (WHERE t.uso='mercancias') AS n_solo_carga,
               count(*) FILTER (WHERE t.uso='mixto')      AS n_mixto,
               count(*) FILTER (WHERE t.uso='viajeros')   AS n_viajeros,
               count(*) FILTER (WHERE t.uso IS NULL)      AS n_sin_clasificar,
               count(*) FILTER (WHERE t.uso IN ('mercancias','mixto')) AS n_aptos_mercancias,
               (count(*) FILTER (WHERE t.uso IN ('mercancias','mixto')) > 0) AS apto_mercancias,
               round(sum(ST_Length(t.geom))/1000.0, 3) AS longitud_km,
               round(coalesce(sum(ST_Length(t.geom))
                     FILTER (WHERE t.uso IN ('mercancias','mixto')), 0)/1000.0, 3) AS km_mercancias
        FROM linea l JOIN tramo t ON t.linea_id = l.linea_id
        WHERE t.snapshot_date = {_newest(con)}
        GROUP BY l.linea_id, l.nombre, l.uso
        ORDER BY l.linea_id
        """
    ).df()
    df.insert(1, "numero_rfig", df["codigo_linea"].str[-3:])
    df = df.merge(rfig, on="numero_rfig", how="left")
    order = [
        "codigo_linea",
        "numero_rfig",
        "nombre",
        "wiki_linea",
        "wiki_ancho",
        "wiki_longitud",
        "wiki_historica",
        "uso_dominante",
        "n_tramos",
        "n_solo_carga",
        "n_mixto",
        "n_viajeros",
        "n_sin_clasificar",
        "n_aptos_mercancias",
        "apto_mercancias",
        "longitud_km",
        "km_mercancias",
    ]
    return df[order]


def build_station_tables(
    con: duckdb.DuckDBPyConnection, geo: pd.DataFrame | None = None
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (estaciones long, ciudades wide) with municipio joined and stations ordered."""
    geo = geocode_stations(con) if geo is None else geo
    rows = con.execute(
        f"""
        SELECT t.linea_id, l.nombre AS linea_nombre, d.dep_id, d.nombre AS punto,
               ST_X(d.geom) AS x, ST_Y(d.geom) AS y
        FROM tramo t
        JOIN linea l ON l.linea_id = t.linea_id
        JOIN dependencia d ON d.dep_id IN (t.nodo_ini, t.nodo_fin)
        WHERE t.snapshot_date = {_newest(con)} AND d.nombre IS NOT NULL
        """
    ).df()
    rows = rows.merge(
        geo[["dep_id", "municipio", "provincia", "ccaa", "geocode_match", "dist_m"]],
        on="dep_id",
        how="left",
    )

    long_recs: list[dict[str, object]] = []
    wide_recs: list[dict[str, object]] = []
    for linea_id, group in rows.groupby("linea_id"):
        group = group.drop_duplicates("dep_id")
        group = group.iloc[_order_along_axis(group[["x", "y"]].to_numpy())].reset_index(drop=True)
        municipios: list[str] = []
        provincias: list[str] = []
        for orden, (_, r) in enumerate(group.iterrows(), start=1):
            long_recs.append(
                {
                    "codigo_linea": linea_id,
                    "numero_rfig": linea_id[-3:],
                    "orden": orden,
                    "nombre_estacion": r.punto,
                    "es_localidad": not bool(_TECH.search(r.punto)),
                    "municipio": r.municipio,
                    "provincia": r.provincia,
                    "ccaa": r.ccaa,
                    "geocode_match": r.geocode_match,
                    "dist_m": r.dist_m,
                    "dep_id": r.dep_id,
                }
            )
            if pd.notna(r.municipio) and r.municipio not in municipios:
                municipios.append(r.municipio)
                if pd.notna(r.provincia):
                    provincias.append(r.provincia)
        wide_recs.append(
            {
                "codigo_linea": linea_id,
                "numero_rfig": linea_id[-3:],
                "nombre": group.linea_nombre.iloc[0],
                "n_estaciones": len(group),
                "n_municipios": len(municipios),
                "municipios": " > ".join(municipios),
                "provincias": " · ".join(dict.fromkeys(provincias)),
            }
        )
    estaciones = pd.DataFrame(long_recs)
    ciudades = pd.DataFrame(wide_recs).sort_values("codigo_linea").reset_index(drop=True)
    return estaciones, ciudades


def build_line_products(outdir: Path | None = None) -> dict[str, pd.DataFrame]:
    """Build and write all three line-level CSVs. Returns them keyed by stem."""
    out = outdir or settings.processed
    out.mkdir(parents=True, exist_ok=True)
    con = connect()
    try:
        catalogue = build_line_catalogue(con)
        geo = geocode_stations(con)
        estaciones, ciudades = build_station_tables(con, geo)
    finally:
        con.close()
    products = {"lineas": catalogue, "lineas_estaciones": estaciones, "lineas_ciudades": ciudades}
    for stem, frame in products.items():
        frame.to_csv(out / f"{stem}.csv", index=False)
    return products
