"""KISA-XAI-v5 research line: static PE binary detection with structure-mapped XAI.

Protocol: ``paper/v5-kisa-xai/protocol/KISA_XAI_V5_0_DRAFT.yaml``. This package is
kept separate from the preserved v1-v4 code paths. Nothing in it executes,
imports, emulates, or dynamically loads an input file; the representation code
only reads bytes.
"""

from __future__ import annotations

from .representation import (
    PIXELS,
    REPRESENTATION_ID,
    SIDE,
    BudgetSelection,
    IntervalBinnedMap,
    build_interval_map,
    encode_interval_binned,
    raster_sha256,
    select_source_bytes_by_budget,
)

__all__ = [
    "PIXELS",
    "REPRESENTATION_ID",
    "SIDE",
    "BudgetSelection",
    "IntervalBinnedMap",
    "build_interval_map",
    "encode_interval_binned",
    "raster_sha256",
    "select_source_bytes_by_budget",
]
