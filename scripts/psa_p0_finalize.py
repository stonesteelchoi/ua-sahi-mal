"""Close the remaining P0 gate items on real data before the protocol freeze.

  - SHA-256 of every label / manifest / split / index file that the freeze will cite
  - PE32 / PE32+ counts by class and split
  - exact-duplicate check at RASTER level (two different files can still collapse to
    one raster; a duplicate that crosses the split boundary is leakage, one that
    crosses the label is label noise)
  - source bytes sha256 == the published sha256 in samples.csv (restored/replaced files)
  - representation round-trip on a random sample of real files: re-encode from bytes,
    compare raster_sha256 and map_sha256 with the index AND with the stored memmap
    row bit-for-bit, and check the interval-map invariants the contract promises

Reads sample bytes for the round-trip only; nothing is executed or loaded.
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

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from ua_sahi_mal.kisa_xai import (  # noqa: E402
    PIXELS, build_interval_map, encode_interval_binned, raster_sha256,
)


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--samples-dir", required=True)
    ap.add_argument("--rasters-dir", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--labels", nargs="+", required=True, help="samples.csv samples-augmented.csv ...")
    ap.add_argument("--split", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--roundtrip-n", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    rng = random.Random(args.seed)
    report: dict = {"seed": args.seed}
    ok_all = True

    # --- 1. hashes -----------------------------------------------------------
    print("=== file hashes ===")
    idx_path = os.path.join(args.rasters_dir, "raster_index.csv")
    hashes = {}
    for p in [*args.labels, args.manifest, args.split, idx_path,
              os.path.join(args.rasters_dir, "rasters_meta.json")]:
        hashes[os.path.basename(p)] = {"path": os.path.abspath(p), "sha256": sha256_file(p),
                                       "bytes": os.path.getsize(p)}
        print(f"  {os.path.basename(p):28} {hashes[os.path.basename(p)]['sha256']}")
    report["file_sha256"] = hashes

    # --- 2. load index + manifest -------------------------------------------
    with open(idx_path, newline="", encoding="utf-8") as fh:
        index = list(csv.DictReader(fh))
    pe_kind = {}
    with open(args.manifest, newline="", encoding="utf-8", errors="replace") as fh:
        for r in csv.DictReader(fh):
            pe_kind[r["sample_id"]] = r["pe_kind"]
    # published sha256 per sample, from the first label file that has the column
    label_sha = {}
    for lp in args.labels:
        with open(lp, newline="", encoding="utf-8", errors="replace") as fh:
            rd = csv.DictReader(fh)
            if "sha256" in (rd.fieldnames or []):
                for r in rd:
                    label_sha[r["id"]] = r["sha256"].lower()
                break
    n = len(index)
    print(f"\nindex rows: {n:,}")

    # --- 3. PE kind by class / split ----------------------------------------
    print("\n=== PE32 / PE32+ by class and split ===")
    tab = Counter((r["label"], pe_kind.get(r["sample_id"], "?"), r["split"]) for r in index)
    kinds = sorted({k[1] for k in tab})
    for label, name in (("0", "benign"), ("1", "malicious")):
        for kind in kinds:
            row = {s: tab.get((label, kind, s), 0) for s in ("train", "val", "test")}
            tot = sum(row.values())
            print(f"  {name:10} {kind:6} total {tot:8,}  train {row['train']:8,}  "
                  f"val {row['val']:7,}  test {row['test']:7,}")
    report["pe_kind_table"] = {f"{l}|{k}|{s}": v for (l, k, s), v in tab.items()}

    # --- 4. raster-level exact duplicates ------------------------------------
    print("\n=== raster-level exact duplicates ===")
    by_hash = defaultdict(list)
    for r in index:
        by_hash[r["raster_sha256"]].append(r)
    dups = {h: rs for h, rs in by_hash.items() if len(rs) > 1}
    n_dup_rows = sum(len(rs) for rs in dups.values())
    cross_split = sum(1 for rs in dups.values() if len({r["split"] for r in rs}) > 1)
    cross_label = sum(1 for rs in dups.values() if len({r["label"] for r in rs}) > 1)
    print(f"  duplicate groups {len(dups):,}  rows involved {n_dup_rows:,}")
    print(f"  groups crossing SPLIT boundary (leakage): {cross_split:,}")
    print(f"  groups crossing LABEL (label noise):       {cross_label:,}")
    sizes = Counter(len(rs) for rs in dups.values())
    print(f"  group size histogram: {dict(sorted(sizes.items()))}")
    report["raster_duplicates"] = {"groups": len(dups), "rows": n_dup_rows,
                                   "cross_split_groups": cross_split,
                                   "cross_label_groups": cross_label,
                                   "size_histogram": {str(k): v for k, v in sorted(sizes.items())}}
    # sha256 of source bytes was unique per samples.csv; raster collisions are therefore
    # files that differ only in bytes the 224x224 mean pooling cannot see. They are
    # written out so eligibility can collapse them to one representative.
    dup_path = os.path.join(args.rasters_dir, "raster_duplicate_groups.csv")
    with open(dup_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["raster_sha256", "sample_id", "label", "split", "file_size"])
        for h, rs in sorted(dups.items(), key=lambda kv: -len(kv[1])):
            for r in rs:
                w.writerow([h, r["sample_id"], r["label"], r["split"], r["file_size"]])
    if cross_split:
        ok_all = False
        print("  !! cross-split raster duplicates exist -> split must collapse them before freeze")

    # --- 5. round trip on real files -----------------------------------------
    print(f"\n=== representation round-trip on {args.roundtrip_n:,} random samples ===")
    mm = np.load(os.path.join(args.rasters_dir, "rasters.npy"), mmap_mode="r")
    assert mm.shape == (n, PIXELS), f"memmap shape {mm.shape} != ({n}, {PIXELS})"
    pool_by_policy = defaultdict(list)
    for r in index:
        pool_by_policy[r["policy"]].append(r)
    picks = []
    for pol, rs in pool_by_policy.items():
        k = max(1, round(args.roundtrip_n * len(rs) / n))
        picks += rng.sample(rs, min(k, len(rs)))
    fails = Counter()
    checked = 0
    unreadable = []
    for r in picks:
        try:
            with open(os.path.join(args.samples_dir, r["sample_id"]), "rb") as fh:
                data = fh.read()
        except OSError as exc:  # locked by a scanner, quarantined, ACL changed ...
            fails["unreadable"] += 1
            unreadable.append((r["sample_id"], type(exc).__name__))
            continue
        if len(data) != int(r["file_size"]):
            fails["file_size"] += 1
        if label_sha and hashlib.sha256(data).hexdigest() != label_sha.get(r["sample_id"], ""):
            fails["source_sha256_vs_label_file"] += 1
        raster, imap = encode_interval_binned(data)
        if raster_sha256(raster) != r["raster_sha256"]:
            fails["raster_sha256"] += 1
        if build_interval_map(len(data)).map_sha256() != r["map_sha256"]:
            fails["map_sha256_from_size"] += 1
        if imap.map_sha256() != r["map_sha256"]:
            fails["map_sha256_from_encode"] += 1
        stored = np.asarray(mm[int(r["row"])])
        if not np.array_equal(stored, raster.reshape(-1)):
            fails["memmap_row_mismatch"] += 1
        # contract invariants
        s, e = imap.starts, imap.ends
        if s[0] != 0 or np.any(e <= s) or np.any(e > len(data)):
            fails["interval_bounds"] += 1
        if imap.policy == "contiguous_interval_mean_pool":
            if e[-1] != len(data) or np.any(s[1:] != e[:-1]):
                fails["mean_pool_partition"] += 1
        else:
            if np.any(e - s != 1) or len(set(s.tolist())) != len(data):
                fails["nearest_coverage"] += 1
        if imap.policy != r["policy"]:
            fails["policy"] += 1
        checked += 1
    print(f"  checked {checked:,}   failures: {dict(fails) if fails else 'none'}")
    if unreadable:
        print(f"  unreadable during round-trip: {unreadable[:10]}")
    report["roundtrip"] = {"checked": checked, "failures": dict(fails),
                           "unreadable": unreadable,
                           "by_policy": {p: len(rs) for p, rs in pool_by_policy.items()}}
    if fails:
        ok_all = False

    # --- 6. whole-directory readability: is the extracted set intact right now? ----
    print("\n=== whole-directory readability (open each file once) ===")
    present = 0
    denied, gone, other = [], [], []
    for r in index:
        pth = os.path.join(args.samples_dir, r["sample_id"])
        try:
            with open(pth, "rb") as fh:
                fh.read(1)
            present += 1
        except PermissionError:
            denied.append(r["sample_id"])
        except FileNotFoundError:
            gone.append(r["sample_id"])
        except OSError as exc:
            other.append((r["sample_id"], type(exc).__name__))
    print(f"  readable {present:,} / {n:,}   permission-denied {len(denied):,}   "
          f"missing {len(gone):,}   other {len(other):,}")
    if denied[:10]:
        print(f"  denied e.g. {denied[:10]}")
    if gone[:10]:
        print(f"  missing e.g. {gone[:10]}")
    report["readability"] = {"readable": present, "denied": denied, "missing": gone,
                             "other": other}
    if denied or gone or other:
        ok_all = False
        print("  !! extracted samples are being altered after extraction -- check AV "
              "protection history before anything else")

    report["all_gates_ok"] = ok_all
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)
    print(f"\n{'ALL P0 DATA GATES OK' if ok_all else 'P0 GATE FAILURES PRESENT'} -> {args.out}")
    return 0 if ok_all else 2


if __name__ == "__main__":
    sys.exit(main())
