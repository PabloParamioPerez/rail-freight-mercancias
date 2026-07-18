"""Smoke tests that don't hit the network."""

from __future__ import annotations

import datetime as dt


def test_import():
    import redferro

    assert redferro.__version__


def test_settings_paths():
    from redferro.config import settings

    assert settings.raw.name == "raw"
    assert settings.crs_storage == "EPSG:25830"


def test_feature_types():
    from redferro.sources.ideadif_wfs import FEATURE_TYPES

    assert FEATURE_TYPES["railway_link"] == "TN.RailTransportNetwork.RailwayLink"


def test_empty_graph_builds():
    # graph builder should be importable and construct types without a DB call
    from redferro.habilitaciones.model import HabilitacionLinea

    h = HabilitacionLinea("H1", "test", frozenset({"t1"}), dt.date(2020, 1, 1))
    assert "t1" in h.tramos
