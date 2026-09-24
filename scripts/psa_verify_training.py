"""Verify completed PSA training artifacts without loading a model or any PE bytes."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
from datetime import datetime, timezone
from pathlib import Path


def digest(path):
    with Path(path).open("rb") as fh:
        return hashlib.file_digest(fh, "sha256").hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def dataset_counts(rasters, split_manifest=None):
    seen, drop = set(), set()
    with (rasters / "raster_duplicate_groups.csv").open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            key = row["raster_sha256"]
            if key in seen:
                drop.add(row["sample_id"])
            seen.add(key)
    counts = {s: {"n": 0, "benign": 0, "malicious": 0} for s in ("train", "val", "test")}
    assignments = None
    if split_manifest is not None:
        assignments = {}
        with Path(split_manifest).open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                sample_id = row["sample_id"]
                require(sample_id not in assignments and row["split"] in counts,
                        "duplicate sample ID or invalid split in manifest")
                assignments[sample_id] = (row["split"], row["label"], row["group"])
    matched = set()
    with (rasters / "raster_index.csv").open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if assignments is not None:
                assignment = assignments.get(row["sample_id"])
                if assignment is None:
                    continue
                require((row["label"], row["group"]) == assignment[1:], "manifest/index mismatch")
                matched.add(row["sample_id"])
                selected_split = assignment[0]
            else:
                selected_split = row["split"]
            if row["sample_id"] in drop:
                continue
            require(row["label"] in ("0", "1"), "invalid label")
            count = counts[selected_split]
            count["n"] += 1
            count["malicious" if row["label"] == "1" else "benign"] += 1
    require(assignments is None or len(matched) == len(assignments), "manifest IDs absent from raster index")
    return counts


def verify_summary(summary, counts, seed, init="imagenet", batch=512):
    require((summary["seed"], summary["init"], summary["batch_size"], summary["device"])
            == (seed, init, batch, "cuda"), "run identity mismatch")
    require(summary["tag"] == f"seed{seed}_{init}_bs{batch}", "tag mismatch")
    require(summary["counts"] == counts, "dataset counts changed")
    history = summary["history"]
    require(len(history) == summary["epochs_ran"] and 0 < len(history) <= 30, "invalid epoch count")
    score, best_epoch, patience = -1.0, -1, 0
    metrics = ("macro_f1", "balanced_acc", "recall_ben", "recall_mal")
    for epoch, item in enumerate(history):
        require(item["epoch"] == epoch and item["val"]["n"] == counts["val"]["n"], "history mismatch")
        for key in metrics:
            value = item["val"][key]
            require(math.isfinite(value) and 0 <= value <= 1, f"invalid {key}")
        require(math.isfinite(item["train_sec"]) and item["train_sec"] > 0, "invalid duration")
        if item["val"]["macro_f1"] > score + 1e-4:
            score, best_epoch, patience = item["val"]["macro_f1"], epoch, 0
        else:
            patience += 1
        require(patience < 5 or epoch == len(history) - 1, "continued after early stop")
    require(len(history) == 30 or patience == 5, "incomplete training history")
    best = summary["best"]
    require(best["epoch"] == best_epoch and abs(best["val_macro_f1"] - score) < 1e-12,
            "best epoch mismatch")
    for key in (*metrics, "n"):
        require(best[key] == history[best_epoch]["val"][key], "best metrics mismatch")
    majority = max(counts["val"]["benign"], counts["val"]["malicious"])
    margin = score - majority / (counts["val"]["n"] + majority)
    gate = summary["sanity_gate"]
    require(abs(gate["macro_f1_margin_over_majority"] - margin) < 1e-12, "gate margin mismatch")
    passed = margin > 0.10 and best["balanced_acc"] >= 0.70 and min(
        best["recall_ben"], best["recall_mal"]) >= 0.60
    require(gate["balanced_acc_ge_0.70"] == (best["balanced_acc"] >= 0.70), "BA gate mismatch")
    require(gate["recall_both_ge_0.60"] == (min(best["recall_ben"], best["recall_mal"]) >= 0.60),
            "recall gate mismatch")
    return {"seed": seed, "initialization": init, "epochs_ran": len(history), "best": best,
            "sanity_gate_passed": passed, "margin_over_majority": margin,
            "train_plus_validation_seconds": sum(x["train_sec"] for x in history)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rasters-dir", type=Path, required=True)
    parser.add_argument("--split-manifest", type=Path, default=None,
                        help="optional split assignment CSV; default uses raster_index.csv")
    parser.add_argument("--runs-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    require(not args.out.exists(), "output already exists")
    counts = dataset_counts(args.rasters_dir, args.split_manifest)
    results = []
    for seed in (42, 43, 44):
        run = args.runs_dir / f"seed{seed}_imagenet_bs512"
        summary = json.loads((run / "summary.json").read_text(encoding="utf-8"))
        checkpoint_hash = digest(run / "best.pt")
        require(checkpoint_hash == summary["checkpoint_sha256"], f"seed {seed} checkpoint hash mismatch")
        result = verify_summary(summary, counts, seed)
        result.update(summary_path=str(run / "summary.json"), summary_sha256=digest(run / "summary.json"),
                      checkpoint_sha256=checkpoint_hash)
        results.append(result)
    passed = all(r["sanity_gate_passed"] for r in results)
    report = {"verified_at": datetime.now(timezone.utc).isoformat(), "split": "validation",
              "all_seeds_passed": passed, "direction_agreement": passed, "counts": counts,
              "results": results, "means": {k: statistics.mean(r["best"][k] for r in results)
                                              for k in ("macro_f1", "balanced_acc", "recall_ben", "recall_mal")},
              "test_evaluation_performed": False,
              "metadata_baseline_auroc": 0.95,
              "comparison_note": "Validation F1 cannot be compared directly to metadata AUROC."}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, allow_nan=False)
    print(json.dumps(report, indent=2))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
