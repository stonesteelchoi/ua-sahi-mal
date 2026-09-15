"""Section 5 leakage / confounder audit for the PSA dataset.

Joins the stage-2 manifest (per-sample PE facts, produced by psa_stream_audit.py)
with samples-augmented.csv (labels + imphash), then answers three questions the
KISA-XAI v5 protocol gates on before anything may be frozen:

  1. Eligibility -- how many samples survive an explicit label rule, MZ/PE parse,
     and duplicate collapse.
  2. Metadata-only shortcut -- per-feature AUROC and a combined logistic model
     evaluated with GROUP-disjoint folds (groups = imphash).  Protocol section 5
     limits the main claim to "dataset-specific static discrimination" when the
     metadata-only AUROC reaches 0.90.
  3. Split feasibility -- a group-disjoint 70/15/15 split over eligible samples,
     with the split manifest and its hash.

Reads only derived facts.  No sample bytes are opened here.

    python scripts/psa_shortcut_audit.py ^
        --manifest D:\\secure-malware-data\\psa\\manifest_stage2.csv ^
        --labels   C:\\research\\ua-sahi-mal\\datasets\\samples-augmented.csv ^
        --outdir   D:\\secure-malware-data\\psa\\audit
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import random
import sys
from collections import Counter, defaultdict

import numpy as np

# Byte-derivable features only: a value the model could in principle read off the
# file.  `submitted`, `total` and `positives` are collection metadata and are
# reported separately as provenance evidence -- never fed to the combined model.
BYTE_FEATURES = [
    "archive_size", "file_entropy", "section_count", "size_of_headers", "size_of_image",
    "entry_point", "executable_section_bytes", "non_executable_section_bytes",
    "overlay_bytes", "certificate_bytes", "signed", "max_section_entropy",
    "nonstandard_section_names", "linker_major", "linker_minor", "timestamp",
    "subsystem", "dll_characteristics", "has_imphash", "is_pe32plus",
]
PROVENANCE_FEATURES = ["submitted_ts", "total", "positives"]


def auroc(scores: np.ndarray, labels: np.ndarray) -> float:
    """Mann-Whitney U form, average ranks for ties."""
    order = np.argsort(scores, kind="mergesort")
    s = scores[order]
    ranks = np.empty(len(s), dtype=np.float64)
    i = 0
    while i < len(s):
        j = i
        while j + 1 < len(s) and s[j + 1] == s[i]:
            j += 1
        ranks[i:j + 1] = (i + j) / 2.0 + 1.0
        i = j + 1
    y = labels[order]
    n1 = float(y.sum())
    n0 = float(len(y) - n1)
    if n1 == 0 or n0 == 0:
        return float("nan")
    return float((ranks[y == 1].sum() - n1 * (n1 + 1) / 2.0) / (n1 * n0))


def to_float(v, default=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def load(manifest: str, labels: str) -> list[dict]:
    lab = {}
    with open(labels, newline="", encoding="utf-8", errors="replace") as fh:
        for r in csv.DictReader(fh):
            lab[r["id"]] = r
    rows = []
    missing = 0
    with open(manifest, newline="", encoding="utf-8", errors="replace") as fh:
        for m in csv.DictReader(fh):
            sid = m["sample_id"]
            l = lab.get(sid)
            if l is None:
                missing += 1
                continue
            m["_label_row"] = l
            rows.append(m)
    print(f"manifest rows joined: {len(rows):,}   unmatched: {missing:,}   labels: {len(lab):,}")
    return rows


def eligibility(rows, benign_min_total, malicious_min_positives):
    """Explicit label rule. The `list` column alone is not a clean threshold:
    1,771 whitelisted samples carry AV detections and 105 blacklisted ones carry
    none, so the boundary band is excluded from the main analysis and counted."""
    stats = Counter()
    out = []
    for r in rows:
        l = r["_label_row"]
        pos = to_float(l["positives"], -1)
        tot = to_float(l["total"], -1)
        listed = l["list"]
        if listed == "Whitelist":
            label = 0
            ok = tot >= benign_min_total and pos == 0
        else:
            label = 1
            ok = pos >= malicious_min_positives
        if not ok:
            stats["label_band_excluded"] += 1
            continue
        if r["magic_ok"] != "1":
            stats["not_mz"] += 1
            continue
        if r["parser_status"] != "ok":
            stats[f"parser_{r['parser_status'] or 'blank'}"] += 1
            continue
        if r["pe_kind"] not in ("PE32", "PE32+"):
            stats["not_pe32_or_plus"] += 1
            continue
        r["_label"] = label
        out.append(r)
        stats["eligible"] += 1
    return out, stats


def featurise(rows):
    X = np.zeros((len(rows), len(BYTE_FEATURES)), dtype=np.float64)
    P = np.zeros((len(rows), len(PROVENANCE_FEATURES)), dtype=np.float64)
    y = np.zeros(len(rows), dtype=np.int64)
    groups = []
    for i, r in enumerate(rows):
        l = r["_label_row"]
        vals = []
        for f in BYTE_FEATURES:
            if f == "has_imphash":
                vals.append(1.0 if l.get("imphash") else 0.0)
            elif f == "is_pe32plus":
                vals.append(1.0 if r["pe_kind"] == "PE32+" else 0.0)
            else:
                vals.append(to_float(r.get(f)))
        X[i] = vals
        ts = l.get("submitted", "")[:19].replace("-", "").replace(":", "").replace(" ", "")
        P[i] = [to_float(ts), to_float(l.get("total")), to_float(l.get("positives"))]
        y[i] = r["_label"]
        groups.append(l.get("imphash") or f"__noimp_{r['sample_id']}")
    return X, P, y, np.array(groups)


def combined_auroc(X, y, groups, seed=42, folds=5):
    """Group-disjoint CV so a family cannot be memorised across the fold boundary."""
    try:
        from sklearn.linear_model import LogisticRegression
        from sklearn.model_selection import GroupKFold
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler
    except ImportError:
        print("scikit-learn not installed -- skipping the combined model", file=sys.stderr)
        return None
    # log1p the heavy-tailed size columns so the linear model is not dominated by scale
    Xs = X.copy()
    for j, f in enumerate(BYTE_FEATURES):
        if "bytes" in f or f in ("archive_size", "size_of_image", "size_of_headers", "entry_point"):
            Xs[:, j] = np.log1p(np.clip(Xs[:, j], 0, None))
    if len(np.unique(y)) < 2:
        print("only one class present -- combined model skipped", file=sys.stderr)
        return None
    n_groups = len(np.unique(groups))
    folds = max(2, min(folds, n_groups))
    oof = np.zeros(len(y), dtype=np.float64)
    gkf = GroupKFold(n_splits=folds)
    for tr, te in gkf.split(Xs, y, groups):
        if len(np.unique(y[tr])) < 2:
            oof[te] = float(y[tr].mean())
            continue
        model = make_pipeline(
            StandardScaler(),
            LogisticRegression(max_iter=2000, C=1.0, class_weight="balanced"),
        )
        model.fit(Xs[tr], y[tr])
        oof[te] = model.predict_proba(Xs[te])[:, 1]
    return auroc(oof, y)


def make_split(rows, groups, seed=42, ratios=(0.70, 0.15, 0.15)):
    by_group = defaultdict(list)
    for r, g in zip(rows, groups, strict=True):
        by_group[g].append(r["sample_id"])
    order = sorted(by_group.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    rng = random.Random(seed)
    # largest group first into train (it can exceed a whole split on its own),
    # remainder shuffled then greedily filled to target sizes
    head, tail = order[:1], order[1:]
    rng.shuffle(tail)
    total = len(rows)
    targets = [ratios[0] * total, ratios[1] * total, ratios[2] * total]
    names = ["train", "val", "test"]
    counts = [0, 0, 0]
    assign = {}
    for g, ids in head + tail:
        k = 0 if counts[0] < targets[0] else (1 if counts[1] < targets[1] else 2)
        counts[k] += len(ids)
        for sid in ids:
            assign[sid] = names[k]
    return assign, dict(zip(names, counts, strict=True))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--labels", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--benign-min-total", type=float, default=40.0)
    ap.add_argument("--malicious-min-positives", type=float, default=10.0)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)

    rows = load(args.manifest, args.labels)
    elig, stats = eligibility(rows, args.benign_min_total, args.malicious_min_positives)
    print("\n=== eligibility ===")
    for k, v in sorted(stats.items(), key=lambda kv: -kv[1]):
        print(f"  {k:28} {v:8,}")
    if not elig:
        print("no eligible samples", file=sys.stderr)
        return 1
    n_mal = sum(r["_label"] for r in elig)
    print(f"  eligible benign {len(elig)-n_mal:,} / malicious {n_mal:,}")

    X, P, y, groups = featurise(elig)

    print("\n=== per-feature AUROC (malicious = positive; 0.5 = uninformative) ===")
    per = {}
    for j, f in enumerate(BYTE_FEATURES):
        a = auroc(X[:, j], y)
        per[f] = a
        print(f"  {f:30} {a:.4f}   (symmetric {max(a, 1-a):.4f})")
    print("  -- provenance only, NOT model inputs --")
    for j, f in enumerate(PROVENANCE_FEATURES):
        a = auroc(P[:, j], y)
        per[f] = a
        print(f"  {f:30} {a:.4f}   (symmetric {max(a, 1-a):.4f})")

    print("\n=== combined metadata-only model (group-disjoint 5-fold) ===")
    comb = combined_auroc(X, y, groups, seed=args.seed)
    verdict = "n/a"
    if comb is not None:
        print(f"  AUROC = {comb:.4f}")
        verdict = "SHORTCUT_GATE_TRIPPED" if comb >= 0.90 else "below_0.90_gate"
        print(f"  protocol section 5 gate (0.90): {verdict}")
        if comb >= 0.90:
            print("  -> the gate requires the label-source relationship to be ANALYSED next")
            print("     (psa_confound_drilldown.py: family ablation + matching). The main")
            print("     claim is narrowed to dataset-specific static discrimination only if")
            print("     the effect survives matching or stratification -- not on this number")
            print("     alone.")

    assign, counts = make_split(elig, groups, seed=args.seed)
    print("\n=== group-disjoint split ===")
    for k, v in counts.items():
        print(f"  {k:6} {v:8,} ({100*v/len(elig):.1f}%)")
    split_path = os.path.join(args.outdir, "split_manifest.csv")
    with open(split_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["sample_id", "label", "group", "split", "pe_kind", "repr_policy"])
        for r, g in zip(elig, groups, strict=True):
            w.writerow([r["sample_id"], r["_label"], g, assign[r["sample_id"]],
                        r["pe_kind"], r["repr_policy"]])
    with open(split_path, "rb") as fh:
        split_hash = hashlib.sha256(fh.read()).hexdigest()
    print(f"  split manifest: {split_path}\n  split_sha256 : {split_hash}")

    pol = Counter((r["repr_policy"], r["_label"]) for r in elig)
    print("\n=== interval-binned-v1 policy vs label (confound check) ===")
    for lab_name, lab_val in (("benign", 0), ("malicious", 1)):
        tot = sum(v for (p, l), v in pol.items() if l == lab_val)
        near = pol.get(("nearest_repetition", lab_val), 0)
        print(f"  {lab_name:10} nearest_repetition {near:7,} / {tot:7,} = {100*near/max(tot,1):.1f}%")

    summary = {
        "eligibility": dict(stats),
        "eligible_benign": len(elig) - n_mal,
        "eligible_malicious": n_mal,
        "per_feature_auroc": per,
        "combined_metadata_auroc": comb,
        "section5_verdict": verdict,
        "split_counts": counts,
        "split_sha256": split_hash,
        "seed": args.seed,
        "benign_min_total": args.benign_min_total,
        "malicious_min_positives": args.malicious_min_positives,
    }
    sp = os.path.join(args.outdir, "shortcut_audit.json")
    with open(sp, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, ensure_ascii=False)
    print(f"\nwrote {sp}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
