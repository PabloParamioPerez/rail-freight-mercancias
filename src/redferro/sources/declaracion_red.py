"""Ingest the annual 'Declaracion sobre la Red' (Adif) — the temporal backbone.

The live IDEAdif spatial service is only a current snapshot. The historical
dimension (2015-) comes from the yearly Network Statement PDFs, whose annexes
contain the 'Catalogo de Lineas': line number, name, gauge (ancho), electrification,
PK range and status per tramo. We parse those tables into a tidy per-year panel and
later join geometry from the WFS by linea/tramo id.

Adif publishes one Declaracion per horario de servicio (roughly per year). PDF URLs
change; keep them in `DECLARACIONES` as you collect them. Download PDFs into
data/external/declaracion_red/<year>.pdf, then run `parse_catalogo`.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pdfplumber

from redferro.config import settings

# Fill in as you gather them (portal: https://www.adif.es/sobre-adif/declaracion-red).
# year -> source PDF url (kept for provenance; download the PDFs manually).
DECLARACIONES: dict[int, str] = {
    # 2025: "https://www.adif.es/.../declaracion_red_2025.pdf",
    # 2024: "...",
}

EXPECTED_COLUMNS = [
    "linea_id",  # e.g. "100"
    "linea_nombre",
    "tramo",  # textual tramo description
    "pk_ini",
    "pk_fin",
    "ancho",  # iberico / UIC / metrico / mixto
    "electrificado",  # bool / tension
    "estado",  # en servicio / fuera de servicio / construccion
    "uso",  # viajeros / mercancias / mixto  (relevant for the freight subset)
]


def _pdf_path(year: int) -> Path:
    return settings.external / "declaracion_red" / f"{year}.pdf"


def parse_catalogo(year: int, pages: str | None = None) -> pd.DataFrame:
    """Extract the Catalogo de Lineas table from a downloaded Declaracion PDF.

    `pages` optionally restricts to the annex page range (e.g. "120-180"), since
    scanning the whole PDF is slow. Returns a tidy DataFrame stamped with `anio`.

    NOTE: table layout differs slightly across years — this is a starting point;
    inspect a couple of years and adjust the `extract_tables` settings / header
    mapping. Keep the raw extraction in data/interim for auditability.
    """
    path = _pdf_path(year)
    if not path.exists():
        raise FileNotFoundError(
            f"Missing {path}. Download the {year} Declaracion PDF into data/external/declaracion_red/."
        )

    page_range = _parse_page_range(pages)
    # pdfplumber leaves a cell as None when it extracts no text, so the row type is
    # Optional all the way down; normalisation happens at the (still TODO) header step.
    rows: list[list[str | None]] = []
    with pdfplumber.open(path) as pdf:
        targets = pdf.pages if page_range is None else [pdf.pages[i] for i in page_range]
        for page in targets:
            for table in page.extract_tables() or []:
                rows.extend(table)

    raw = pd.DataFrame(rows)
    settings.interim.mkdir(parents=True, exist_ok=True)
    raw.to_parquet(settings.interim / f"declaracion_{year}_raw.parquet")
    # Header normalisation is year-specific; left as a documented TODO so the
    # raw capture is never blocked on perfect parsing.
    df = raw.copy()
    df["anio"] = year
    return df


def _parse_page_range(pages: str | None) -> list[int] | None:
    """Turn a 1-indexed inclusive page spec into 0-indexed offsets.

    Accepts a range ("120-180") or a single page ("120"). Returns None for an
    empty spec, meaning "scan the whole PDF".
    """
    if not pages:
        return None
    lo, sep, hi = pages.partition("-")
    start = int(lo)
    end = int(hi) if sep else start
    return list(range(start - 1, end))  # 0-indexed, inclusive of `end`
