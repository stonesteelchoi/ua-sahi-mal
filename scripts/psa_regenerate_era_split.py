"""Regenerate the era split from verified eligible metadata; never read PE payloads.

New era splits are separate training experiments. The compatibility report explicitly
checks whether their holdout contains files/groups seen by the existing main models.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

from psa_shortcut_audit import make_split


def digest(path):
    with Path(path).open("rb") as fh:
        return hashlib.file_digest(fh, "sha256").hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--main-split", required=True, type=Path)
    ap.add_argument("--matched-ids", required=True, type=Path)
    ap.add_argument("--outdir", required=True, type=Path)
    args = ap.parse_args()
    if args.outdir.exists():
        raise ValueError("output directory already exists; use a new destination")
    original_hash = digest(args.main_split)
    if original_hash != "843bcb8033205a5b37b420b93cdf940ed69dce58d73e5f3eaf942d7cc318099b":
        raise ValueError("main split does not match PSA protocol")
    id_lines = [s.strip() for s in args.matched_ids.read_text(encoding="utf-8").splitlines() if s.strip()]
    allow = set(id_lines)
    if len(allow) != len(id_lines) or len(allow) != 70938:
        raise ValueError("unexpected era membership count or duplicate IDs")
    with args.main_split.open(newline="", encoding="utf-8") as fh:
        main_rows = list(csv.DictReader(fh))
    by_id = {r["sample_id"]: r for r in main_rows}
    if len(by_id) != len(main_rows) or not allow <= by_id.keys():
        raise ValueError("duplicate main ID or missing era member")
    rows = [dict(r, _label=int(r["label"])) for r in main_rows if r["sample_id"] in allow]
    if Counter(r["_label"] for r in rows) != {0: 35469, 1: 35469}:
        raise ValueError("era membership label totals differ from protocol")
    groups = [r["group"] for r in rows]
    assign, counts = make_split(rows, groups, seed=42)
    group_splits = defaultdict(set)
    strata = defaultdict(Counter)
    transitions = Counter()
    for row in rows:
        destination = assign[row["sample_id"]]
        group_splits[row["group"]].add(destination)
        strata[(row["label"], row["pe_kind"], row["repr_policy"])][destination] += 1
        transitions[(row["split"], destination)] += 1
    if any(len(v) != 1 for v in group_splits.values()) or sum(counts.values()) != len(rows):
        raise ValueError("group disjointness or assignment coverage failed")
    main_train_groups = {r["group"] for r in main_rows if r["split"] == "train"}
    era_test = [r for r in rows if assign[r["sample_id"]] == "test"]
    seen_test = sum(r["group"] in main_train_groups for r in era_test)
    previously_selected_test = sum(r["split"] == "val" for r in era_test)
    report = {
        "seed": 42, "source": "main eligible split metadata restricted to original era IDs",
        "main_split_sha256": original_hash, "matched_ids_sha256": digest(args.matched_ids),
        "n": len(rows), "counts": counts, "group_disjoint": True, "groups": len(group_splits),
        "strata": [{"label": int(st[0]), "pe_kind": st[1], "repr_policy": st[2],
                    "n": sum(ct.values()), "counts": dict(ct),
                    "shares": {s: ct[s] / sum(ct.values()) for s in ("train", "val", "test")}}
                   for st, ct in sorted(strata.items())],
        "main_to_era_transitions": {f"{a}->{b}": n for (a, b), n in sorted(transitions.items())},
        "era_test_files_in_main_training_groups": seen_test,
        "era_test_files_used_for_main_validation": previously_selected_test,
        "existing_main_models_can_evaluate_full_era_test_as_unseen": seen_test == 0 and previously_selected_test == 0,
        "usage": ("Separate split manifest only; do not use reassigned holdout "
                  "to claim unseen performance of main models."),
        "test_model_evaluation_performed": False,
    }
    args.outdir.mkdir(parents=True)
    split_file = args.outdir / "split_manifest_era.csv"
    with split_file.open("x", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(["sample_id", "label", "group", "split", "pe_kind", "repr_policy"])
        for row in rows:
            writer.writerow([row["sample_id"], row["label"], row["group"], assign[row["sample_id"]],
                             row["pe_kind"], row["repr_policy"]])
    report["split_sha256"] = digest(split_file)
    if digest(args.main_split) != original_hash:
        raise ValueError("main split changed concurrently")
    with (args.outdir / "era_split_report.json").open("x", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, allow_nan=False)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
