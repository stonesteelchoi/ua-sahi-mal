"""Protocol section 5, step 2: analyse WHY metadata alone separates the classes.

The combined metadata-only model reached AUROC 0.9526 on group-disjoint folds, which
trips the 0.90 gate.  The protocol does not stop there -- it requires the label-source
relationship to be analysed, and the main claim to be narrowed only if the effect
survives matching or stratification.  This script does that analysis:

  1. ABLATION -- refit the combined model with each feature family removed, and with
     each family alone, so the shortcut can be attributed rather than just observed.
  2. MATCHING -- build a subset in which benign and malicious are matched on the
     dominant confounders, then re-measure the metadata AUROC inside it.  If the
     metadata signal collapses there, that subset is where the semantics question
     can actually be asked.
  3. PROFILES -- per-class distributions of the strongest features, so the confound
     can be described in the paper rather than merely flagged.

Reads only the stage-2 manifest and the label CSV.  No sample bytes are opened.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import Counter, defaultdict

import numpy as np

FAMILIES = {
    "entropy":    ["file_entropy", "max_section_entropy"],
    "size":       ["archive_size", "size_of_image", "size_of_headers",
                   "executable_section_bytes", "non_executable_section_bytes",
                   "overlay_bytes", "entry_point"],
    "toolchain":  ["linker_major", "linker_minor", "timestamp", "subsystem",
                   "dll_characteristics", "is_pe32plus"],
    "signing":    ["certificate_bytes", "signed"],
    "structure":  ["section_count", "nonstandard_section_names", "has_imphash"],
}
ALL_FEATURES = [f for fs in FAMILIES.values() for f in fs]
LOG_FEATURES = {"archive_size", "size_of_image", "size_of_headers", "entry_point",
                "executable_section_bytes", "non_executable_section_bytes", "overlay_bytes"}


def auroc(scores: np.ndarray, labels: np.ndarray) -> float:
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
    n1, n0 = float(y.sum()), float(len(y) - y.sum())
    if n1 == 0 or n0 == 0:
        return float("nan")
    return float((ranks[y == 1].sum() - n1 * (n1 + 1) / 2.0) / (n1 * n0))


def f(v, d=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def cv_auroc(X, y, groups, feats, idx, folds=5, seed=42):
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import GroupKFold
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    if not idx or len(np.unique(y)) < 2:
        return float("nan")
    Xs = X[:, idx]
    oof = np.zeros(len(y))
    for tr, te in GroupKFold(n_splits=folds).split(Xs, y, groups):
        if len(np.unique(y[tr])) < 2:
            oof[te] = y[tr].mean()
            continue
        m = make_pipeline(StandardScaler(),
                          LogisticRegression(max_iter=2000, class_weight="balanced"))
        m.fit(Xs[tr], y[tr])
        oof[te] = m.predict_proba(Xs[te])[:, 1]
    return auroc(oof, y)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--split", required=True, help="split_manifest.csv from psa_shortcut_audit.py")
    ap.add_argument("--labels", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)
    rng = np.random.default_rng(args.seed)

    keep = {}
    with open(args.split, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            keep[r["sample_id"]] = r
    lab = {}
    with open(args.labels, newline="", encoding="utf-8", errors="replace") as fh:
        for r in csv.DictReader(fh):
            lab[r["id"]] = r

    rows, y, groups = [], [], []
    with open(args.manifest, newline="", encoding="utf-8", errors="replace") as fh:
        for m in csv.DictReader(fh):
            k = keep.get(m["sample_id"])
            if k is None:
                continue
            rows.append(m)
            y.append(int(k["label"]))
            groups.append(k["group"])
    y = np.array(y)
    groups = np.array(groups)
    print(f"eligible samples: {len(rows):,}  benign {int((y==0).sum()):,}  malicious {int(y.sum()):,}")

    X = np.zeros((len(rows), len(ALL_FEATURES)))
    for i, m in enumerate(rows):
        l = lab[m["sample_id"]]
        for j, name in enumerate(ALL_FEATURES):
            if name == "has_imphash":
                v = 1.0 if l.get("imphash") else 0.0
            elif name == "is_pe32plus":
                v = 1.0 if m["pe_kind"] == "PE32+" else 0.0
            else:
                v = f(m.get(name))
            if name in LOG_FEATURES:
                v = np.log1p(max(v, 0.0))
            X[i, j] = v
    pos = {name: j for j, name in enumerate(ALL_FEATURES)}

    full = cv_auroc(X, y, groups, ALL_FEATURES, list(range(len(ALL_FEATURES))))
    print(f"\n=== combined (all families) AUROC = {full:.4f} ===")

    print("\n=== family alone / family removed ===")
    ab = {}
    for fam, feats in FAMILIES.items():
        only = cv_auroc(X, y, groups, ALL_FEATURES, [pos[f_] for f_ in feats])
        drop = cv_auroc(X, y, groups, ALL_FEATURES,
                        [pos[f_] for f_ in ALL_FEATURES if f_ not in feats])
        ab[fam] = {"alone": only, "without": drop, "delta_when_removed": full - drop}
        print(f"  {fam:10} alone {only:.4f}   without {drop:.4f}   "
              f"(drop {full-drop:+.4f})")

    # --- matching on the dominant confounders -------------------------------
    # Coarse exact matching on deciles of size and entropy plus the linker major
    # version: inside a cell benign and malicious look alike on the variables that
    # carry most of the shortcut, so anything left is not those variables.
    print("\n=== matched subset ===")
    size_b = np.digitize(X[:, pos["archive_size"]],
                         np.quantile(X[:, pos["archive_size"]], np.linspace(0.1, 0.9, 9)))
    ent_b = np.digitize(X[:, pos["file_entropy"]],
                        np.quantile(X[:, pos["file_entropy"]], np.linspace(0.1, 0.9, 9)))
    lnk = X[:, pos["linker_major"]].astype(int)
    cells = defaultdict(lambda: ([], []))
    for i in range(len(rows)):
        cells[(int(size_b[i]), int(ent_b[i]), int(lnk[i]))][int(y[i])].append(i)
    sel = []
    for (_, (b, m)) in cells.items():
        k = min(len(b), len(m))
        if k == 0:
            continue
        sel.extend(rng.permutation(b)[:k].tolist())
        sel.extend(rng.permutation(m)[:k].tolist())
    sel = np.array(sorted(sel), dtype=int)
    print(f"  cells {len(cells):,}   matched samples {len(sel):,} "
          f"({100*len(sel)/len(rows):.1f}% of eligible)")
    if len(sel) > 100 and len(np.unique(y[sel])) == 2:
        matched = cv_auroc(X[sel], y[sel], groups[sel], ALL_FEATURES,
                           list(range(len(ALL_FEATURES))))
        print(f"  benign {int((y[sel]==0).sum()):,}  malicious {int(y[sel].sum()):,}")
        print(f"  metadata-only AUROC inside the matched subset = {matched:.4f}")
        print(f"  -> {'shortcut persists' if matched >= 0.90 else 'shortcut substantially reduced'}")
    else:
        matched = float("nan")
        print("  matched subset too small or single-class")

    print("\n=== per-feature AUROC, full vs matched ===")
    per = {}
    for name, j in pos.items():
        a_full = auroc(X[:, j], y)
        a_mat = auroc(X[sel, j], y[sel]) if len(sel) > 100 else float("nan")
        per[name] = {"full": a_full, "matched": a_mat}
        print(f"  {name:30} full {a_full:.4f}   matched {a_mat:.4f}")

    print("\n=== class profiles of the strongest confounders ===")
    prof = {}
    for name in ("linker_major", "max_section_entropy", "timestamp", "subsystem", "signed",
                 "is_pe32plus"):
        j = pos[name]
        d = {}
        for lname, lv in (("benign", 0), ("malicious", 1)):
            v = X[y == lv, j]
            d[lname] = {"p25": float(np.quantile(v, .25)), "median": float(np.median(v)),
                        "p75": float(np.quantile(v, .75)), "mean": float(v.mean())}
        prof[name] = d
        b, m = d["benign"], d["malicious"]
        print(f"  {name:22} benign med {b['median']:>12,.1f} | malicious med {m['median']:>12,.1f}")
    for name in ("linker_major", "subsystem"):
        j = pos[name]
        print(f"  -- {name} top values --")
        for lname, lv in (("benign", 0), ("malicious", 1)):
            c = Counter(X[y == lv, j].astype(int)).most_common(5)
            print(f"     {lname:10} {c}")

    out = {"combined_auroc": full, "ablation": ab, "matched_auroc": matched,
           "matched_n": int(len(sel)), "eligible_n": len(rows),
           "per_feature": per, "profiles": prof, "seed": args.seed}
    p = os.path.join(args.outdir, "confound_drilldown.json")
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2, ensure_ascii=False)
    np.save(os.path.join(args.outdir, "matched_indices.npy"), sel)
    with open(os.path.join(args.outdir, "matched_sample_ids.txt"), "w", encoding="utf-8") as fh:
        for i in sel:
            fh.write(rows[i]["sample_id"] + "\n")
    print(f"\nwrote {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
