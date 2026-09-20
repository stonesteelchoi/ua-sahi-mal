"""Static-only pre-freeze structure audit on deduplicated train/validation samples.

Never evaluates a model or opens a held-out test payload. A complete census is
diagnostic evidence, not an automatic protocol freeze decision. No sample is dropped
because its parser disagrees: every selected ID receives a ledger row.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from ua_sahi_mal.kisa_xai.structure import STRUCTURE_VERSION, build_structure_map, compare_pefile


def digest(path):
    with Path(path).open("rb") as fh:
        return hashlib.file_digest(fh, "sha256").hexdigest()


def audit_one(job):
    root, sid, split, expected_size, expected_hash = job
    record = {"sample_id": sid, "split": split, "status": "error"}
    try:
        if not sid.isdecimal():
            raise ValueError("sample ID is not decimal")
        root = Path(root).resolve()
        path = (root / sid).resolve()
        if not path.is_relative_to(root):
            raise ValueError("sample path escapes source directory")
        if path.stat().st_size != expected_size:
            raise ValueError("source file size differs from raster metadata")
        data = path.read_bytes()
        sha = hashlib.sha256(data).hexdigest()
        if sha != expected_hash:
            raise ValueError("source SHA256 differs from manifest")
        record["source_sha256"] = sha
        structure = build_structure_map(data)
        record["structure"] = structure.to_dict()
        comparison = compare_pefile(data)
        record["crosscheck"] = comparison
        record["status"] = "agreement" if comparison["raw_fields_agree"] else "disagreement"
    except Exception as exc:  # Preserve parse/missing-file failures in the ledger, never skip.
        record["error_type"] = type(exc).__name__
        record["error"] = str(exc)
    return record


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rasters-dir", type=Path, required=True)
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--samples-dir", type=Path, required=True)
    ap.add_argument("--outdir", type=Path, required=True)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--limit", type=int, default=0, help="0 = full train/val census; positive = diagnostic subset")
    ap.add_argument("--static-only", action="store_true", required=True)
    args = ap.parse_args()
    if args.limit < 0 or not 1 <= args.workers <= 8 or args.outdir.exists():
        raise ValueError("invalid worker/limit setting or output already exists")
    # Check optional parser before starting; absence must not produce a false success.
    import pefile

    rasters = args.rasters_dir
    expected = {
        rasters / "raster_index.csv": "94d02b247fc761d64fdea5aeac9afe2da6dc56bdcc998cc84d4a5c7d3f76f785",
        args.manifest: "3dc0bd7fb42935692462013f716bbd8ccd339b20bb436289aa93e78852b17414",
    }
    for path, sha in expected.items():
        if digest(path) != sha:
            raise ValueError(f"protocol input hash mismatch: {path.name}")
    seen, drop = set(), set()
    duplicate_file = rasters / "raster_duplicate_groups.csv"
    with duplicate_file.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row["raster_sha256"] in seen:
                drop.add(row["sample_id"])
            seen.add(row["raster_sha256"])
    with (rasters / "raster_index.csv").open(newline="", encoding="utf-8") as fh:
        rows = [r for r in csv.DictReader(fh) if r["split"] in ("train", "val") and r["sample_id"] not in drop]
    population_n = len(rows)
    rows.sort(key=lambda r: int(r["sample_id"]))
    if args.limit:
        rows = rows[:args.limit]
    wanted = {r["sample_id"] for r in rows}
    if len(wanted) != len(rows):
        raise ValueError("duplicate selected IDs")
    with args.manifest.open(newline="", encoding="utf-8") as fh:
        hashes = {r["sample_id"]: r["sha256"] for r in csv.DictReader(fh) if r["sample_id"] in wanted}
    if hashes.keys() != wanted:
        raise ValueError("missing source hashes")
    jobs = [(str(args.samples_dir), r["sample_id"], r["split"], int(r["file_size"]), hashes[r["sample_id"]])
            for r in rows]
    args.outdir.mkdir(parents=True)
    plan = {"version": STRUCTURE_VERSION, "population": "deduplicated_train_and_validation_only",
            "population_n": population_n, "selected_n": len(rows), "limit": args.limit,
            "sampling": "sample_id ascending; diagnostic subset only when limit > 0",
            "test_payload_access": False, "workers": args.workers, "pefile_version": pefile.__version__,
            "inputs": {str(p): h for p, h in expected.items()}, "duplicate_file_sha256": digest(duplicate_file),
            "implementation_sha256": digest(Path(__file__)),
            "structure_source_sha256": digest(Path(__file__).resolve().parents[1] /
                                               "src/ua_sahi_mal/kisa_xai/structure.py"),
            "freeze_policy": "No automatic freeze: retain every disagreement/error and review boundary semantics."}
    with (args.outdir / "audit_plan.json").open("x", encoding="utf-8") as fh:
        json.dump(plan, fh, indent=2)
    statuses, mismatch_fields, warnings = Counter(), Counter(), Counter()
    native_overlay_disagreements = 0
    start = time.monotonic()
    print(f"selected {len(rows)} / {population_n} train/val files; test payloads locked", flush=True)
    with (args.outdir / "structure_ledger.jsonl").open("x", encoding="utf-8") as ledger:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            for index, record in enumerate(pool.map(audit_one, jobs, chunksize=16), start=1):
                ledger.write(json.dumps(record, ensure_ascii=True, allow_nan=False) + "\n")
                statuses[record["status"]] += 1
                comparison = record.get("crosscheck", {})
                mismatch_fields.update(m["field"] for m in comparison.get("mismatches", []))
                native_overlay_disagreements += int(comparison.get("native_overlay", {}).get("agrees") is False)
                warnings.update(record.get("structure", {}).get("warnings", []))
                if index % 1000 == 0 or index == len(rows):
                    ledger.flush()
                    print(f"{index}/{len(rows)} {dict(statuses)} elapsed={time.monotonic()-start:.1f}s", flush=True)
    report = {**plan, "complete": sum(statuses.values()) == len(rows), "status_counts": dict(statuses),
              "mismatch_fields": dict(mismatch_fields), "structure_warnings": dict(warnings),
              "native_overlay_disagreements": native_overlay_disagreements,
              "elapsed_seconds": round(time.monotonic() - start, 3),
              "ledger_sha256": digest(args.outdir / "structure_ledger.jsonl"),
              "protocol_freeze_authorized": False}
    with (args.outdir / "structure_audit_summary.json").open("x", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, allow_nan=False)
    print(json.dumps({k: v for k, v in report.items() if k not in ("structure_warnings", "inputs")}, indent=2))
    return 0 if not statuses["error"] and not statuses["disagreement"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
