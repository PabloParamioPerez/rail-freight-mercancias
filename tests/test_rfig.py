"""RFIG wikitext parsing. Offline: a synthetic fragment, no network to Wikipedia."""

from __future__ import annotations

from redferro.sources.rfig import parse_rfig_table

FRAGMENT = """
{| class="wikitable sortable"
| '''Número''' || '''Línea''' || '''Longitud''' || '''Ancho'''
|-
| 100||[[Línea 100|Hendaya a Madrid-Chamartín]]||640,9 km
| Ibérico
|-style="font-style: italic; color: grey"
| 012||Madrid a Cambiador Atocha||1,3 km|| Estándar
|-
| 13G||Bifurcación León||2,0 km|| Ibérico
|}
"""


def test_parse_extracts_numero_name_and_gauge():
    df = parse_rfig_table(FRAGMENT).set_index("numero_rfig")
    assert df.loc["100", "wiki_linea"] == "Hendaya a Madrid-Chamartín"  # wikilink unwrapped
    assert df.loc["100", "wiki_ancho"] == "Ibérico"  # cell spread across two source lines
    assert df.loc["100", "wiki_longitud"] == "640,9 km"


def test_greyed_rows_are_flagged_not_dropped():
    df = parse_rfig_table(FRAGMENT).set_index("numero_rfig")
    assert bool(df.loc["012", "wiki_historica"]) is True
    assert bool(df.loc["100", "wiki_historica"]) is False


def test_letter_suffixed_codigo_is_kept():
    """Adif uses variante códigos like 13G; the último-3 join key must survive."""
    nums = set(parse_rfig_table(FRAGMENT).numero_rfig)
    assert "13G" in nums


def test_empty_table_returns_typed_frame():
    df = parse_rfig_table("no table here")
    assert list(df.columns) == [
        "numero_rfig",
        "wiki_linea",
        "wiki_longitud",
        "wiki_ancho",
        "wiki_historica",
    ]
    assert df.empty
