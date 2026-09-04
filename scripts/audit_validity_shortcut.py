"""Audit whether BIG2015 ``??``/address gaps form a family-label shortcut.

The raster format stores unknown bytes and virtual-address gaps as zero-valued
pixels plus a separate validity mask.  The first evidence run loaded the mask
but discarded it before feature extraction.  This audit uses only the
``valid_fraction`` already recorded in the manifest and asks how well that one
scalar predicts the family by nearest training-class centroid.

It does not establish that a trained classifier used the shortcut.  Accuracy
materially above the 1/K chance level establishes that the shortcut is
available, so conclusions from models that received unmasked zeros must be
treated as provisional until a mask-aware rerun agrees.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

import numpy as np


def nearest_centroids(
    train_rows: Sequence[dict[str, Any]], rows: Sequence[dict[str, Any]]
) -> tuple[float, dict[int, float]]:
    """Return accuracy and per-class mean validity fraction."""
    labels = sorted({int(row["label"]) for row in train_rows})
    centroids = {
        label: float(
            np.mean(
                [float(row["valid_fraction"]) for row in train_rows if int(row["label"]) == label]
            )
        )
        for label in labels
    }
    correct = 0
    for row in rows:
        value = float(row["valid_fraction"])
        predicted = min(labels, key=lambda label: (abs(value - centroids[label]), label))
        correct += int(predicted == int(row["label"]))
    return correct / len(rows) if rows else float("nan"), centroids


def summarize(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    values = np.asarray([float(row["valid_fraction"]) for row in rows], dtype=np.float64)
    return {
        "n": len(rows),
        "minimum": float(values.min()) if values.size else None,
        "median": float(np.median(values)) if values.size else None,
        "mean": float(values.mean()) if values.size else None,
        "below_0_5": int((values < 0.5).sum()),
        "below_0_1": int((values < 0.1).sum()),
    }


def build_report(manifest_path: str | Path, *, subset_ids: Sequence[str] = ()) -> dict[str, Any]:
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    rows = list(manifest["samples"])
    by_split = {
        split: [row for row in rows if row["split"] == split]
        for split in ("train", "validation", "test")
    }
    validation_accuracy, centroids = nearest_centroids(by_split["train"], by_split["validation"])
    test_accuracy, _ = nearest_centroids(by_split["train"], by_split["test"])

    subset_set = set(subset_ids)
    subset = [row for row in rows if row["sample_id"] in subset_set]
    per_family = {
        str(label): float(
            np.mean([float(row["valid_fraction"]) for row in subset if int(row["label"]) == label])
        )
        for label in sorted({int(row["label"]) for row in subset})
    }
    class_count = len(centroids)
    return {
        "format": "validity-shortcut-audit-1",
        "manifest": str(manifest_path),
        "interpretation": (
            "This is an availability audit, not proof that a neural model used the shortcut. "
            "Above-chance accuracy means validity/gap structure must be controlled in the rerun."
        ),
        "chance_accuracy": 1.0 / class_count if class_count else None,
        "train_class_centroids": {str(key): value for key, value in centroids.items()},
        "validation_accuracy": validation_accuracy,
        "test_accuracy": test_accuracy,
        "split_summary": {split: summarize(split_rows) for split, split_rows in by_split.items()},
        "protocol_subset": {
            **summarize(subset),
            "requested_ids": len(subset_ids),
            "matched_ids": len(subset),
            "per_family_mean": per_family,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument(
        "--evidence-results",
        help="Optional evidence_results.json whose 45-sample subset should be summarized",
    )
    parser.add_argument("--out", help="Optional JSON output path; stdout is always printed")
    args = parser.parse_args()

    subset_ids: list[str] = []
    if args.evidence_results:
        evidence = json.loads(Path(args.evidence_results).read_text(encoding="utf-8"))
        subset_ids = [str(value) for value in evidence.get("subset", [])]
    report = build_report(args.manifest, subset_ids=subset_ids)
    rendered = json.dumps(report, indent=2, ensure_ascii=False)
    print(rendered)
    if args.out:
        path = Path(args.out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
