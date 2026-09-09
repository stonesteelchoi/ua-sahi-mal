"""Aggregate reporting for the SOREL cohort, behind the G0-S publication gate.

G0-S (2026-09-08): aggregate publication requires written clarification of SOREL
Terms §2(c); public SHA manifests and public sample-linked derived intervals are
not permitted. This module therefore:

  * emits ONLY aggregate distributions and rates — never a SHA, never a
    sample-linked interval;
  * verifies its own output carries no 64-hex SHA before returning it;
  * stamps every report ``INTERNAL_ONLY`` with a "Terms §2(c) clarification
    pending" note, unless an explicit operator-attested authorization reference is
    supplied — and even then the payload stays aggregate-only.
"""

from __future__ import annotations

import json
import re
import statistics
from collections.abc import Iterable
from dataclasses import dataclass

from .static_stage import StaticResult

_SHA_RE = re.compile(r"[0-9a-f]{64}")

PENDING_NOTE = "Terms §2(c) clarification pending; sample-linked publication not permitted (G0-S)."


class SampleLinkedLeakError(RuntimeError):
    """Raised if an aggregate payload would contain a 64-hex SHA (a leak)."""


@dataclass
class AggregateReport:
    n: int
    disarm_ok_rate: float
    decompress_ok_rate: float
    peatlas_ok_rate: float
    independent_agree_rate: float
    coverage_mean: float | None
    coverage_median: float | None
    status_histogram_bytes: dict[str, int]
    exclusion_reasons: dict[str, int]
    publication_status: str
    note: str


def _rate(num: int, den: int) -> float:
    return (num / den) if den else 0.0


def summarize(results: Iterable[StaticResult]) -> dict[str, object]:
    """Compute aggregate-only metrics from static-stage results. No SHAs retained."""
    rs = list(results)
    n = len(rs)
    decompress_ok = [r for r in rs if r.decompressed_size > 0]
    disarm_ok = [r for r in rs if r.disarm_ok]
    peatlas_ok = [r for r in rs if r.peatlas_status == "ok"]
    indep_considered = [r for r in rs if r.independent_parser_status
                        and not r.independent_parser_status.startswith("skipped")]
    indep_agree = [r for r in indep_considered if r.independent_parser_status == "ok"]

    coverages = [r.coverage_ok_fraction for r in rs if r.coverage_ok_fraction is not None]
    cov_mean = round(statistics.fmean(coverages), 6) if coverages else None
    cov_median = round(statistics.median(coverages), 6) if coverages else None

    hist: dict[str, int] = {}
    for r in rs:
        for status, length in r.status_histogram.items():
            hist[status] = hist.get(status, 0) + length

    excl: dict[str, int] = {}
    for r in rs:
        if r.exclusion_reason:
            key = r.exclusion_reason.split(":", 1)[0]
            excl[key] = excl.get(key, 0) + 1

    parsed = [r for r in rs if r.is_pe32_plus is not None]
    pe32_plus = sum(1 for r in parsed if r.is_pe32_plus)
    n_sections = sorted(r.n_sections for r in parsed if r.n_sections is not None)
    overlay_present = sum(1 for r in parsed if (r.overlay_bytes or 0) > 0)

    return {
        "n": n,
        "disarm_ok_rate": round(_rate(len(disarm_ok), n), 6),
        "decompress_ok_rate": round(_rate(len(decompress_ok), n), 6),
        "peatlas_ok_rate": round(_rate(len(peatlas_ok), n), 6),
        "independent_agree_rate": round(_rate(len(indep_agree), len(indep_considered)), 6),
        "independent_considered": len(indep_considered),
        "coverage_mean": cov_mean,
        "coverage_median": cov_median,
        "status_histogram_bytes": hist,
        "exclusion_reasons": excl,
        # post-download strata (amendment §6.3) — counts/distributions only
        "parsed_n": len(parsed),
        "pe32_plus_count": pe32_plus,
        "pe32_count": len(parsed) - pe32_plus,
        "n_sections_median": (statistics.median(n_sections) if n_sections else None),
        "overlay_present_count": overlay_present,
    }


def assert_no_sample_link(payload: object) -> None:
    """Fail loudly if a serialized payload contains any 64-hex SHA."""
    blob = json.dumps(payload, ensure_ascii=False)
    hit = _SHA_RE.search(blob)
    if hit:
        raise SampleLinkedLeakError(
            f"aggregate payload contains a 64-hex token ({hit.group()[:12]}...); "
            "sample-linked data must not appear in an aggregate report (G0-S)."
        )


def build_report(results: Iterable[StaticResult], *,
                 authorization_ref: str | None = None) -> dict[str, object]:
    """Build the gated aggregate report.

    Without ``authorization_ref`` the report is INTERNAL_ONLY with the pending note.
    With one (operator-attested written clarification), it is marked cleared — but
    the payload is aggregate-only either way, and is checked for SHA leakage.
    """
    summary = summarize(results)
    if authorization_ref:
        summary["publication_status"] = "cleared"
        summary["authorization_ref"] = authorization_ref
        summary["note"] = "aggregate-only; sample-linked publication still not permitted (G0-S)."
    else:
        summary["publication_status"] = "INTERNAL_ONLY"
        summary["note"] = PENDING_NOTE
    assert_no_sample_link(summary)
    return summary
