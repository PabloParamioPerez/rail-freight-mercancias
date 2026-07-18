"""Lightweight domain types for habilitaciones (mirror the DuckDB schema)."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field


@dataclass(frozen=True)
class HabilitacionLinea:
    hab_id: str
    descripcion: str
    tramos: frozenset[str]              # tramo_ids it authorizes
    valid_from: dt.date
    valid_to: dt.date | None = None
    fuente: str = "reconstruida"


@dataclass(frozen=True)
class HabilitacionMaquina:
    maq_id: str
    descripcion: str
    valid_from: dt.date
    valid_to: dt.date | None = None


@dataclass
class LineaMaquinaLink:
    hab_id: str
    maq_id: str
    operador: str | None = None
    valid_from: dt.date = field(default_factory=dt.date.today)
    valid_to: dt.date | None = None
