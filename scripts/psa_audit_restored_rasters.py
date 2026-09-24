"""Read-only comparison of restored source bytes with existing PSA raster rows.

The report contains hashes and counts only, never source bytes or raster values.
It does not alter the source tree, raster array, or raster index.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

import numpy as np

from ua_sahi_mal.kisa_xai.representation import SIDE, encode_interval_binned, raster_sha256


def load_targets(path: Path) -> dict[str, tuple[int, str]]:
    targets = {}
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        required = {"sample_id", "expected_length", "expected_sha256"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError("recovery manifest lacks required columns")
        for row in reader:
            sid = row["sample_id"]
            if not sid.isdecimal() or sid in targets:
                raise ValueError("invalid or duplicate sample ID")
            targets[sid] = (int(row["expected_length"]), row["expected_sha256"].lower())
    if not targets:
        raise ValueError("empty recovery manifest")
    return targets


def load_index(path: Path, targets: set[str]) -> dict[str, dict]:
    index = {}
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            sid = row["sample_id"]
            if sid in targets:
                if sid in index:
                    raise ValueError(f"duplicate raster ID: {sid}")
                index[sid] = row
    if index.keys() != targets:
        raise ValueError(f"missing raster IDs: {sorted(targets - index.keys())}")
    return index


def audit(targets: dict[str, tuple[int, str]], index: dict[str, dict],
          samples_dir: Path, rasters_path: Path) -> dict:
    rasters = np.load(rasters_path, mmap_mode="r", allow_pickle=False)
    if rasters.ndim != 2 or rasters.shape[1] != SIDE * SIDE or rasters.dtype != np.float32:
        raise ValueError("unexpected raster shape or dtype")
    root = samples_dir.resolve()
    if len({int(index[sid]["row"]) for sid in targets}) != len(targets):
        raise ValueError("target sample IDs share a raster row")
    rows = []
    counts = Counter()
    for sid in sorted(targets, key=int):
        expected_size, expected_sha = targets[sid]
        idx = index[sid]
        row_number = int(idx["row"])
        if not 0 <= row_number < rasters.shape[0]:
            raise ValueError(f"raster row outside array: {sid}")
        source = (root / sid).resolve()
        if not source.is_relative_to(root):
            raise ValueError(f"source path escapes sample directory: {sid}")
        data = source.read_bytes()
        source_sha = hashlib.sha256(data).hexdigest()
        if len(data) != expected_size or source_sha != expected_sha:
            raise ValueError(f"restored source failed integrity check: {sid}")
        derived, imap = encode_interval_binned(data)
        current_raster_hash = raster_sha256(rasters[row_number].reshape(SIDE, SIDE))
        regenerated_hash = raster_sha256(derived)
        result = {
            "sample_id": sid,
            "row": row_number,
            "split": idx["split"],
            "label": idx["label"],
            "source_size": expected_size,
            "index_size": int(idx["file_size"]),
            "index_row_hash_valid": current_raster_hash == idx["raster_sha256"],
            "raster_matches_restored_source": current_raster_hash == regenerated_hash,
            "map_matches_restored_source": idx["map_sha256"] == imap.map_sha256(),
            "policy_matches_restored_source": idx["policy"] == imap.policy,
        }
        if not result["index_row_hash_valid"]:
            raise ValueError(f"existing raster row differs from its index hash: {sid}")
        rows.append(result)
        for key in ("raster_matches_restored_source", "map_matches_restored_source",
                    "policy_matches_restored_source", "index_row_hash_valid"):
            counts[key + "_true" if result[key] else key + "_false"] += 1
        counts["index_size_matches_source_true" if result["index_size"] == expected_size
               else "index_size_matches_source_false"] += 1
        counts["split_" + idx["split"]] += 1
    return {"version": "psa-restored-raster-audit-v1", "target_count": len(rows),
            "rasters_shape": list(rasters.shape), "counts": dict(counts), "rows": rows,
            "source_payload_executed": False, "raster_modified": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recovery-manifest", type=Path, required=True)
    parser.add_argument("--raster-index", type=Path, required=True)
    parser.add_argument("--rasters", type=Path, required=True)
    parser.add_argument("--samples-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError(f"refusing to overwrite {args.out}")
    targets = load_targets(args.recovery_manifest)
    index = load_index(args.raster_index, set(targets))
    report = audit(targets, index, args.samples_dir, args.rasters)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, allow_nan=False)
    print(json.dumps({k: v for k, v in report.items() if k != "rows"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
