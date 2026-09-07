"""PEAtlas: authoritative file-offset / RVA / VA coordinate mapping for PE files.

See ``docs/PEATLAS_CONTRACT.md`` for the data contract. This package is pure and
does not execute, disassemble, or download anything.
"""

from __future__ import annotations

from .atlas import (
    CoordinateComponent,
    MappedComponent,
    MapResult,
    MapStatus,
    PeAtlas,
    PeFormatError,
    PeLayout,
    Provenance,
    Section,
    Segment,
    parse_pe,
)
from .intervals import Interval, IntervalSet

__all__ = [
    "Interval",
    "IntervalSet",
    "PeAtlas",
    "PeLayout",
    "Section",
    "MapStatus",
    "MapResult",
    "Segment",
    "Provenance",
    "CoordinateComponent",
    "MappedComponent",
    "PeFormatError",
    "parse_pe",
]
