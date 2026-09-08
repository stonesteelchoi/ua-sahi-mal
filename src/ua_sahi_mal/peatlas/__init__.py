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
from .pebuild import SectionSpec, build_pe
from .projection import (
    PixelProjection,
    UnsupportedProjectionError,
    project_pixels_to_atlas,
)
from .synthetic import (
    PlantSpec,
    SyntheticSample,
    default_specs,
    generate_pair,
    write_dataset,
)

__all__ = [
    "Interval",
    "IntervalSet",
    "PixelProjection",
    "UnsupportedProjectionError",
    "project_pixels_to_atlas",
    "SectionSpec",
    "build_pe",
    "PlantSpec",
    "SyntheticSample",
    "generate_pair",
    "write_dataset",
    "default_specs",
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
