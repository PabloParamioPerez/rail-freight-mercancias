"""Declaracion sobre la Red parsing helpers. Offline — no PDF downloads."""

from __future__ import annotations

import pytest

from redferro.sources.declaracion_red import _parse_page_range, _pdf_path, parse_catalogo


def test_page_range_is_one_indexed_and_inclusive():
    # "120-125" means pages 120..125 inclusive -> 0-indexed offsets 119..124
    assert _parse_page_range("120-125") == [119, 120, 121, 122, 123, 124]


def test_page_range_accepts_a_single_page():
    """Regression: "120".partition("-") leaves an empty upper bound -> int("")."""
    assert _parse_page_range("120") == [119]


@pytest.mark.parametrize("spec", [None, ""])
def test_page_range_empty_means_whole_pdf(spec: str | None):
    assert _parse_page_range(spec) is None


def test_missing_pdf_raises_actionable_error(tmp_path, monkeypatch):
    monkeypatch.setattr("redferro.config.settings.data_dir", tmp_path)
    with pytest.raises(FileNotFoundError, match="declaracion_red"):
        parse_catalogo(2024)


def test_pdf_path_is_year_stamped_under_external():
    path = _pdf_path(2024)
    assert path.name == "2024.pdf"
    assert path.parent.name == "declaracion_red"
