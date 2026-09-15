"""Build the interval-binned-v1 rasters for an eligible PSA split (P1 materialisation).

For every sample in the split manifest this writes one 224x224 float32 raster into a
single .npy memmap and records the per-sample raster_sha256 and map_sha256 required by
the protocol's manifest.  The pixel->offset map itself is NOT stored: it is a pure
function of the file size, so the size plus map_sha256 reproduces it exactly.

Nothing here executes, imports or dynamically loads a sample; bytes are read and
reduced arithmetically, using the frozen encoder in ua_sahi_mal.kisa_xai.

    python scripts/psa_build_rasters.py ^
        --samples-dir D:\\secure-malware-data\\psa\\pe-machine-learning-dataset\\samples ^
        --split       D:\\secure-malware-data\\psa\\audit\\split_manifest.csv ^
        --out-dir     D:\\secure-malware-data\\psa\\rasters

Output: rasters.npy  (N, 50176) float32, raster_index.csv, rasters_meta.json
Size:   N * 50176 * 4 bytes -- 199,316 samples is 40.0 GB, so target a data drive.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from ua_sahi_mal.kisa_xai import (  # noqa: E402
    PIXELS,
    REPRESENTATION_ID,
    SIDE,
    build_interval_map,
    encode_interval_binned,
    raster_sha256,
)

_MM = None  # per-worker memmap handle
_DIR = None


def _init(path: str, samples_dir: str) -> None:
    global _MM, _DIR
    _MM = np.load(path, mmap_mode="r+")
    _DIR = samples_dir


def _encode_one(job):
    row, sample_id = job
    path = os.path.join(_DIR, sample_id)
    with open(path, "rb") as fh:
        data = fh.read()
    raster, imap = encode_interval_binned(data)
    _MM[row] = raster.reshape(-1)
    return (row, sample_id, len(data), imap.policy,
            raster_sha256(raster), imap.map_sha256())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--samples-dir", required=True)
    ap.add_argument("--split", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--workers", type=int, default=max(1, min((os.cpu_count() or 4) - 1, 12)),
                    help="kept modest on purpose: the encoder makes an int64 copy, so a "
                         "worker peaks at ~8x the file size in RAM")
    ap.add_argument("--big-threshold", type=int, default=64 * 1024 * 1024,
                    help="files above this are encoded serially in the parent, after the "
                         "pool, so a burst of large files cannot exhaust RAM")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    os.makedirs(args.out_dir, exist_ok=True)

    with open(args.split, newline="", encoding="utf-8") as fh:
        split_rows = list(csv.DictReader(fh))
    if args.limit:
        split_rows = split_rows[: args.limit]
    n = len(split_rows)
    with open(args.split, "rb") as fh:
        split_hash = hashlib.sha256(fh.read()).hexdigest()

    gib = n * PIXELS * 4 / 2**30
    print(f"{n:,} samples -> rasters.npy  ({n:,} x {PIXELS:,} float32 = {gib:.1f} GiB)")
    print(f"representation: {REPRESENTATION_ID}  side={SIDE}  split_sha256={split_hash}")

    mm_path = os.path.join(args.out_dir, "rasters.npy")
    mm = np.lib.format.open_memmap(mm_path, mode="w+", dtype=np.float32, shape=(n, PIXELS))
    del mm

    sizes = {}
    for r in split_rows:
        p = os.path.join(args.samples_dir, r["sample_id"])
        try:
            sizes[r["sample_id"]] = os.path.getsize(p)
        except OSError:
            sizes[r["sample_id"]] = -1
    missing = [s for s, v in sizes.items() if v < 0]
    if missing:
        print(f"ERROR: {len(missing):,} samples missing from {args.samples_dir}", file=sys.stderr)
        print("  e.g. " + ", ".join(missing[:5]), file=sys.stderr)
        return 1

    small = [(i, r["sample_id"]) for i, r in enumerate(split_rows)
             if sizes[r["sample_id"]] <= args.big_threshold]
    big = [(i, r["sample_id"]) for i, r in enumerate(split_rows)
           if sizes[r["sample_id"]] > args.big_threshold]
    print(f"pool: {len(small):,} samples on {args.workers} workers; "
          f"serial: {len(big):,} above {args.big_threshold/2**20:.0f} MiB")

    results = {}
    t0 = time.time()
    done = 0
    total_bytes = 0
    import multiprocessing as mp

    with mp.Pool(args.workers, initializer=_init, initargs=(mm_path, args.samples_dir)) as pool:
        for row, sid, nbytes, policy, rhash, mhash in pool.imap_unordered(
            _encode_one, small, chunksize=16
        ):
            results[row] = (sid, nbytes, policy, rhash, mhash)
            done += 1
            total_bytes += nbytes
            if done % 5000 == 0:
                el = time.time() - t0
                print(f"  {done:,}/{n:,}  {total_bytes/2**30:.1f} GiB  {el/60:.1f} min  "
                      f"{total_bytes/2**20/max(el,1):.0f} MiB/s", flush=True)

    if big:
        _init(mm_path, args.samples_dir)
        for job in big:
            row, sid, nbytes, policy, rhash, mhash = _encode_one(job)
            results[row] = (sid, nbytes, policy, rhash, mhash)
            done += 1
            total_bytes += nbytes
            print(f"  serial {sid} {nbytes/2**20:.1f} MiB", flush=True)

    idx_path = os.path.join(args.out_dir, "raster_index.csv")
    policy_counts = {}
    with open(idx_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["row", "sample_id", "label", "split", "group", "pe_kind",
                    "file_size", "policy", "raster_sha256", "map_sha256"])
        for i, r in enumerate(split_rows):
            sid, nbytes, policy, rhash, mhash = results[i]
            assert sid == r["sample_id"], f"row {i} mismatch: {sid} != {r['sample_id']}"
            policy_counts[policy] = policy_counts.get(policy, 0) + 1
            w.writerow([i, sid, r["label"], r["split"], r["group"], r.get("pe_kind", ""),
                        nbytes, policy, rhash, mhash])

    meta = {
        "representation_id": REPRESENTATION_ID, "side": SIDE, "pixels": PIXELS,
        "dtype": "float32", "n": n, "split_manifest": os.path.abspath(args.split),
        "split_sha256": split_hash, "samples_dir": os.path.abspath(args.samples_dir),
        "policy_counts": policy_counts,
        "raster_file": os.path.abspath(mm_path),
        "elapsed_seconds": round(time.time() - t0, 1),
        "total_source_bytes": total_bytes,
    }
    with open(os.path.join(args.out_dir, "rasters_meta.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2)

    el = time.time() - t0
    print(f"\ndone: {n:,} rasters, {total_bytes/2**30:.1f} GiB read, {el/60:.1f} min")
    print(f"  policies: {policy_counts}")
    print(f"  {mm_path}\n  {idx_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
