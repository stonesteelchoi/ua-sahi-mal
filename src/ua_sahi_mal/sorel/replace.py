"""Deterministic replacement of failed effective samples from the frozen reserve.

Amendment §6.3 freezes a replacement order (20% reserve per split, det-key order)
*before* any result is seen, and §8 forbids swapping a failed file for an
arbitrarily convenient one. This module is the mechanical implementation:

  * The frozen selection files are never modified. Callers write *derived*
    ``*_effective_*`` files.
  * A failed effective row (a ``primary`` or an earlier ``replacement``) is marked
    with ``exclusion_reason = "<stage>:<reason>"`` and stays in the manifest.
  * The next unused ``reserve`` row **of the same split, in manifest order** (which is
    the frozen det-key order) is promoted to ``selection_role = "replacement"`` with
    ``replaces_sha256`` pointing at the row it replaces.
  * Idempotent / iterative: rows already excluded are untouched; rows not covered by
    the supplied results are untouched; a replacement that later fails is excluded
    and the next reserve is promoted (a chain of ``replaces_sha256``).

No network. Pure manifest + result bookkeeping, fully unit-testable.
"""

from __future__ import annotations

import copy
import re
from collections.abc import Iterable
from dataclasses import dataclass, field

from .acquire import HeadResult, error_bucket
from .manifest import ManifestRow
from .select import SPLITS

EFFECTIVE_ROLES = ("primary", "replacement")
_SHA_RE = re.compile(r"[0-9a-f]{64}")


@dataclass
class ReplacementReport:
    stage: str
    excluded: int = 0
    promoted: int = 0
    per_split: dict[str, dict[str, int]] = field(default_factory=dict)
    reserve_exhausted: list[str] = field(default_factory=list)
    reasons: dict[str, int] = field(default_factory=dict)   # SHA-free reason -> count

    def as_dict(self) -> dict[str, object]:
        return {
            "stage": self.stage,
            "excluded": self.excluded,
            "promoted": self.promoted,
            "per_split": self.per_split,
            "reserve_exhausted": self.reserve_exhausted,
            "reasons": self.reasons,
        }


def _mask(text: str) -> str:
    return _SHA_RE.sub("<sha>", text or "")


def effective_rows(rows: Iterable[ManifestRow]) -> list[ManifestRow]:
    """Rows that currently constitute the sample: primary/replacement, not excluded."""
    return [r for r in rows if r.selection_role in EFFECTIVE_ROLES and not r.exclusion_reason]


def apply_replacements(rows: list[ManifestRow], results: Iterable[HeadResult], *,
                       stage: str = "preflight") -> tuple[list[ManifestRow], ReplacementReport]:
    """Exclude failed effective rows and promote reserves deterministically.

    ``results`` are per-sha outcomes for the *current* effective list (e.g. preflight
    HEAD results). Returns (new_rows, report); the input list is not mutated.
    """
    by_sha = {h.sha256: h for h in results}
    new_rows = [copy.copy(r) for r in rows]
    report = ReplacementReport(stage=stage)

    for split in SPLITS:
        split_rows = [r for r in new_rows if r.official_split == split]
        effective = [r for r in split_rows if r.selection_role in EFFECTIVE_ROLES and not r.exclusion_reason]
        reserve = [r for r in split_rows if r.selection_role == "reserve" and not r.exclusion_reason]
        excluded_n = promoted_n = 0

        for r in effective:
            h = by_sha.get(r.sorel_original_sha256)
            if h is None or h.ok:
                continue  # not covered by these results, or fine
            reason = _mask(h.error) or "unknown"
            r.exclusion_reason = f"{stage}:{reason}"
            key = error_bucket(h.error)
            report.reasons[key] = report.reasons.get(key, 0) + 1
            excluded_n += 1
            if reserve:
                rep = reserve.pop(0)  # frozen det-key order within the split
                rep.selection_role = "replacement"
                rep.replaces_sha256 = r.sorel_original_sha256
                promoted_n += 1
            elif split not in report.reserve_exhausted:
                report.reserve_exhausted.append(split)

        report.excluded += excluded_n
        report.promoted += promoted_n
        report.per_split[split] = {
            "excluded": excluded_n,
            "promoted": promoted_n,
            "effective_after": len(effective_rows(split_rows)),
            "reserve_remaining": len(reserve),
        }
    return new_rows, report
