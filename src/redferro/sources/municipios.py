"""Municipal boundaries → the municipio each station point falls in.

The boundaries file (all ~8 200 Spanish municipios, INE codes, provincia and CCAA)
is the one heavy input we do **not** commit: it is a stable, versioned public dataset,
so instead of a 72 MB blob in git we fetch it once and verify it against a pinned
SHA-256. That keeps the pipeline reproducible (a different file fails the check) without
bloating the repository. Everything downstream — the point-in-polygon assignment — is a
pure function of that file plus the station geometry, and is unit-tested offline against
synthetic polygons.
"""

from __future__ import annotations

import hashlib
import urllib.request
from pathlib import Path

import geopandas as gpd
import pandas as pd

from redferro.config import settings

#: Opendatasoft export of INE/IGN municipal boundaries (georef-spain-municipio, 2022).
MUNICIPIOS_URL = (
    "https://public.opendatasoft.com/api/explore/v2.1/catalog/datasets/"
    "georef-spain-municipio/exports/geojson?lang=es&timezone=Europe%2FMadrid"
)
#: Pin the exact bytes so a re-download is verifiably the same dataset revision.
MUNICIPIOS_SHA256 = "aacf6037af06369fca285792e59bfe9005b6df48462591897b3bc26477145c9a"
MUNICIPIOS_PATH: Path = settings.external / "municipios" / "georef-spain-municipio.geojson"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch_municipios(dest: Path | None = None, *, verify: bool = True) -> Path:
    """Download the boundaries file if absent, and verify its checksum.

    Idempotent: an already-present file with the right hash is left untouched.
    """
    out = dest or MUNICIPIOS_PATH
    if out.exists() and (not verify or _sha256(out) == MUNICIPIOS_SHA256):
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(MUNICIPIOS_URL, headers={"User-Agent": "redferro/1.0"})
    with urllib.request.urlopen(req) as resp, out.open("wb") as fh:
        fh.write(resp.read())
    if verify:
        got = _sha256(out)
        if got != MUNICIPIOS_SHA256:
            raise ValueError(
                f"Boundaries checksum mismatch: expected {MUNICIPIOS_SHA256}, got {got}. "
                "The upstream dataset may have been revised; update MUNICIPIOS_SHA256 "
                "deliberately after reviewing the change."
            )
    return out


def load_municipios(path: Path | None = None) -> gpd.GeoDataFrame:
    """Read the boundaries, healed and reprojected to the storage CRS."""
    src = path or MUNICIPIOS_PATH
    muni = gpd.read_file(src)[
        ["mun_name", "mun_code", "prov_name", "acom_name", "geometry"]
    ].to_crs(settings.crs_storage)
    muni["geometry"] = muni.geometry.buffer(0)  # heal self-intersecting rings
    return muni


def geocode_points(points: gpd.GeoDataFrame, muni: gpd.GeoDataFrame) -> pd.DataFrame:
    """Assign each point its containing municipio, falling back to the nearest.

    Returns one row per input point (indexed as ``points`` is), with ``municipio``,
    ``provincia``, ``ccaa``, ``geocode_match`` ('within' | 'nearest') and ``dist_m``
    (0 for a containment hit). The nearest fallback catches stations on a municipal
    border, on reclaimed port land, or just across a national frontier.
    """
    cols = {"mun_name": "municipio", "prov_name": "provincia", "acom_name": "ccaa"}
    within = gpd.sjoin(points, muni, predicate="within", how="left").drop(columns="index_right")
    within = within[~within.index.duplicated(keep="first")]  # point on a shared border
    hit = within[within.mun_name.notna()].copy()
    hit["geocode_match"] = "within"
    hit["dist_m"] = 0.0

    missing = points[~points.index.isin(hit.index)]
    if len(missing):
        near = gpd.sjoin_nearest(missing, muni, how="left", distance_col="dist_m").drop(
            columns="index_right"
        )
        near = near[~near.index.duplicated(keep="first")]
        near["geocode_match"] = "nearest"
        hit = pd.concat([hit, near])

    return (
        hit.rename(columns=cols)[["municipio", "provincia", "ccaa", "geocode_match", "dist_m"]]
        .reindex(points.index)
        .round({"dist_m": 1})
    )
