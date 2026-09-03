"""RFIG line numbering, parsed from the Wikipedia transcription of Orden FOM/710/2015.

The IDEAdif código is ``eje(2) + número(3)`` (see ``docs/data-sources.md`` §1), so a
line's RFIG número is the last three characters of its ``codigo_linea``. This module
supplies the número → nombre / ancho / longitud reference table used to enrich the
lines, from a **committed** wikitext snapshot (``data/external/rfig/``) so the join is
reproducible offline and pinned to a known revision of the page.

The wikitext is the raw source of truth; ``parse_rfig_table`` is a pure function so it
is unit-tested against a synthetic fragment with no network.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from redferro.config import settings

#: Committed source-of-truth snapshot of the RFIG lines table.
RFIG_WIKITEXT: Path = settings.external / "rfig" / "lineas_rfig.wikitext"

_REF = re.compile(r"<ref[^>]*>.*?</ref>|<ref[^>]*/>", re.S)
_WIKILINK_PIPE = re.compile(r"\[\[[^\]|]*\|([^\]]*)\]\]")
_WIKILINK = re.compile(r"\[\[([^\]]*)\]\]")
_TEMPLATE = re.compile(r"\{\{[^}]*\}\}")
#: A 3-digit número, or the letter-suffixed variant códigos Adif also uses (e.g. 13G).
_NUMERO = re.compile(r"\d{3}|\d{2}[A-Za-z]")


def _clean_cell(text: str) -> str:
    text = _REF.sub("", text)
    text = _WIKILINK_PIPE.sub(r"\1", text)
    text = _WIKILINK.sub(r"\1", text)
    text = _TEMPLATE.sub("", text)
    return text.replace("'''", "").replace("''", "").strip()


def parse_rfig_table(wikitext: str) -> pd.DataFrame:
    """Parse the first ``wikitable`` into rows of (número, nombre, longitud, ancho).

    Rows Wikipedia greys out (historical / future RFIG lines) are flagged rather than
    dropped, via ``wiki_historica``.
    """
    body = wikitext.split('{| class="wikitable', 1)[-1].split("\n|}", 1)[0]
    rows: list[list[str]] = []
    italics: list[bool] = []
    current: list[str] = []
    italic = False
    for raw in body.splitlines():
        line = raw.rstrip()
        if line.startswith("|-"):
            if current:
                rows.append(current)
                italics.append(italic)
            current = []
            italic = any(k in line for k in ("italic", "grey", "gray"))
            continue
        if line.startswith(("|}", "{|", "!")):
            continue
        if line.startswith("|"):
            current.extend(_clean_cell(cell) for cell in line[1:].split("||"))
    if current:
        rows.append(current)
        italics.append(italic)

    records: list[dict[str, object]] = []
    for cells, is_italic in zip(rows, italics, strict=True):
        if not cells:
            continue
        numero = cells[0].strip()
        if not _NUMERO.fullmatch(numero):
            continue
        records.append(
            {
                "numero_rfig": numero,
                "wiki_linea": cells[1] if len(cells) > 1 else "",
                "wiki_longitud": cells[2] if len(cells) > 2 else "",
                "wiki_ancho": cells[3] if len(cells) > 3 else "",
                "wiki_historica": is_italic,
            }
        )
    return pd.DataFrame.from_records(
        records,
        columns=["numero_rfig", "wiki_linea", "wiki_longitud", "wiki_ancho", "wiki_historica"],
    ).drop_duplicates("numero_rfig", keep="first")


def load_rfig(path: Path | None = None) -> pd.DataFrame:
    """Load and parse the committed RFIG wikitext snapshot."""
    src = path or RFIG_WIKITEXT
    if not src.exists():
        raise FileNotFoundError(
            f"RFIG wikitext not found at {src}. It ships with the repo under data/external/rfig/."
        )
    return parse_rfig_table(src.read_text(encoding="utf-8"))
