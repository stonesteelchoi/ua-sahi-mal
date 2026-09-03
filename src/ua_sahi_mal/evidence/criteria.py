"""The pre-registered decision table (research plan v2 §6).

Thresholds live in code, in one place, and the verdict is computed rather than
written down.  That is the whole point of pre-registration: the failure of a
criterion has to be as easy to publish as its success, and a threshold that can
be edited after seeing the numbers is not a threshold.

======  =========================================================  ==========================
key     condition                                                  failing means
======  =========================================================  ==========================
D1      Byte-IoU >= 0.50 on the synthetic control                   protocol misses a known answer
D2      dNLL_B beats the random-location control (95% CI > 0)       evidence is model A's quirk
D3      dNLL_text beats the random-location control                 evidence is a rasterizing artifact
D4      fill-value rank agreement, Kendall tau >= 0.6               occlusion artifact dominates
D5      Evidence Recall at B = 1/16 >= 0.70                         routing cannot replace a sweep
D6      UA beats bilinear by >= 3.0 percentage points               drop the UA term
======  =========================================================  ==========================

D1-D3 are the conditions for the paper to exist at all.  D6 is expected to fail
-- edge-aware upsampling already lost to bilinear on real byte images -- and the
paper stands without it, minus the UA in its title.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

BYTE_IOU_FLOOR = 0.50
KENDALL_TAU_FLOOR = 0.60
EVIDENCE_RECALL_FLOOR = 0.70
UA_MARGIN_POINTS = 3.0
PRIMARY_BUDGET = 1.0 / 16.0
PRIMARY_BLOCK_BYTES = 4096

PAPER_CRITICAL = ("D1", "D2", "D3")


@dataclass(frozen=True)
class Verdict:
    """One criterion's outcome, with the number that decided it."""

    key: str
    description: str
    passed: bool | None  # None = not measured in this run
    observed: float | None
    threshold: float | None
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "description": self.description,
            "passed": self.passed,
            "observed": self.observed,
            "threshold": self.threshold,
            "note": self.note,
        }


def d1_synthetic_iou(byte_iou: float | None) -> Verdict:
    return Verdict(
        key="D1",
        description="Byte-IoU on the synthetic control set",
        passed=None if byte_iou is None else bool(byte_iou >= BYTE_IOU_FLOOR),
        observed=byte_iou,
        threshold=BYTE_IOU_FLOOR,
        note="A protocol that cannot recover a planted range says nothing about an unplanted one.",
    )


def _significant_gain(difference_low: float | None, difference: float | None) -> bool | None:
    if difference is None or difference_low is None:
        return None
    return bool(difference > 0 and difference_low > 0)


def d2_cross_model(difference: float | None, difference_low: float | None) -> Verdict:
    return Verdict(
        key="D2",
        description="dNLL on model B, evidence range minus random-location control",
        passed=_significant_gain(difference_low, difference),
        observed=difference,
        threshold=0.0,
        note="Model B never took part in the search; without this the result is model A's quirk.",
    )


def d3_cross_representation(difference: float | None, difference_low: float | None) -> Verdict:
    return Verdict(
        key="D3",
        description="dNLL on the text model, evidence range minus random-location control",
        passed=_significant_gain(difference_low, difference),
        observed=difference,
        threshold=0.0,
        note="The text model sees no image; a gain here rules out a rasterizing artifact.",
    )


def d4_fill_agreement(kendall_tau: float | None) -> Verdict:
    return Verdict(
        key="D4",
        description="Kendall tau of block rankings across fill values",
        passed=None if kendall_tau is None else bool(kendall_tau >= KENDALL_TAU_FLOOR),
        observed=kendall_tau,
        threshold=KENDALL_TAU_FLOOR,
        note="Agreement across fills separates removed information from the trace of the mask.",
    )


def d5_evidence_recall(recall: float | None) -> Verdict:
    return Verdict(
        key="D5",
        description=f"Evidence Recall at budget {PRIMARY_BUDGET:.4f}",
        passed=None if recall is None else bool(recall >= EVIDENCE_RECALL_FLOOR),
        observed=recall,
        threshold=EVIDENCE_RECALL_FLOOR,
        note="Routing has to recover the sweep it replaces, or the sweep is the method.",
    )


def d6_upsampler_margin(margin_points: float | None, *, measured: bool = True) -> Verdict:
    return Verdict(
        key="D6",
        description="UA minus bilinear Evidence Recall, in percentage points",
        passed=None if (margin_points is None or not measured) else bool(margin_points >= UA_MARGIN_POINTS),
        observed=margin_points,
        threshold=UA_MARGIN_POINTS,
        note=(
            "Expected to fail: edge-aware upsampling already lost to bilinear on byte images. "
            "Unmeasured on CPU-only runs -- the reference implementation requires CUDA."
        ),
    )


def assemble(verdicts: Sequence[Verdict]) -> dict[str, Any]:
    """Collect verdicts into the summary that goes in the results file."""
    table = {verdict.key: verdict for verdict in verdicts}
    critical = [table[key] for key in PAPER_CRITICAL if key in table]
    measured_critical = [verdict for verdict in critical if verdict.passed is not None]

    if not measured_critical:
        standing = "unmeasured"
    elif len(measured_critical) < len(PAPER_CRITICAL):
        standing = "incomplete"
    elif all(verdict.passed for verdict in measured_critical):
        standing = "supported"
    else:
        standing = "not-supported"

    failed = sorted(key for key, verdict in table.items() if verdict.passed is False)
    unmeasured = sorted(key for key, verdict in table.items() if verdict.passed is None)

    return {
        "primary_budget": PRIMARY_BUDGET,
        "primary_block_bytes": PRIMARY_BLOCK_BYTES,
        "criteria": [verdict.to_dict() for verdict in verdicts],
        "paper_critical": list(PAPER_CRITICAL),
        "paper_standing": standing,
        "failed": failed,
        "unmeasured": unmeasured,
        "title_keeps_ua": table["D6"].passed is True if "D6" in table else False,
        "reporting_rule": (
            "Failing criteria are reported as failures. Thresholds are not adjusted after "
            "the fact, and a failed D6 removes UA from the title rather than from the results."
        ),
    }
