"""Verify a restored PSA source tree without parsing or executing PE files.

Every expected file is checked against ``samples.csv`` using its byte length and
SHA-256. Unexpected directory entries are reported but never removed. Only failure
records and aggregate evidence are written; source bytes are never copied.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from pathlib import Path


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def verify_one(job: tuple[str, str, int, str]) -> dict:
    samples_dir, sample_id, expected_size, expected_sha256 = job
    path = Path(samples_dir) / sample_id
    record = {"sample_id": sample_id, "status": "error"}
    try:
        before = path.stat()
        if before.st_size != expected_size:
            record.update(
                error_type="size_mismatch",
                expected_size=expected_size,
                actual_size=before.st_size,
            )
            return record
        actual_sha256 = digest(path)
        after = path.stat()
        if after.st_size != before.st_size or after.st_mtime_ns != before.st_mtime_ns:
            record.update(error_type="changed_during_read")
            return record
        if actual_sha256 != expected_sha256:
            record.update(
                error_type="sha256_mismatch",
                expected_sha256=expected_sha256,
                actual_sha256=actual_sha256,
            )
            return record
        return {"sample_id": sample_id, "status": "verified", "bytes": expected_size}
    except Exception as exc:  # Every missing/denied/read failure must remain visible.
        record.update(error_type=type(exc).__name__, error=str(exc))
        return record


def load_manifest(path: Path, expected_count: int) -> list[tuple[str, int, str]]:
    rows: list[tuple[str, int, str]] = []
    seen: set[str] = set()
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        required = {"id", "sha256", "length"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError(f"samples.csv lacks required fields: {sorted(required)}")
        for row in reader:
            sample_id = row["id"]
            sha256 = row["sha256"].lower()
            if not sample_id.isdecimal() or sample_id in seen:
                raise ValueError(f"invalid or duplicate sample id: {sample_id!r}")
            if len(sha256) != 64 or any(ch not in "0123456789abcdef" for ch in sha256):
                raise ValueError(f"invalid SHA-256 for sample {sample_id}")
            length = int(row["length"])
            if length <= 0:
                raise ValueError(f"non-positive expected length for sample {sample_id}")
            seen.add(sample_id)
            rows.append((sample_id, length, sha256))
    if len(rows) != expected_count:
        raise ValueError(f"expected {expected_count} manifest rows, found {len(rows)}")
    rows.sort(key=lambda item: int(item[0]))
    return rows


def directory_state(samples_dir: Path, expected_ids: set[str]) -> dict:
    files = [path for path in samples_dir.iterdir() if path.is_file()]
    names = {path.name for path in files}
    return {
        "file_count": len(files),
        "missing_ids": sorted(expected_ids - names, key=int),
        "unexpected_files": sorted(names - expected_ids),
        "zero_byte_count": sum(path.stat().st_size == 0 for path in files),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples-dir", type=Path, required=True)
    parser.add_argument("--samples-csv", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--expected-count", type=int, default=201_549)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    if args.out_dir.exists():
        raise FileExistsError(f"refusing to overwrite {args.out_dir}")
    if not 1 <= args.workers <= 8:
        raise ValueError("workers must be between 1 and 8")

    manifest = load_manifest(args.samples_csv, args.expected_count)
    expected_ids = {sample_id for sample_id, _length, _sha in manifest}
    before = directory_state(args.samples_dir, expected_ids)
    if before["missing_ids"]:
        raise ValueError(f"source tree is missing {len(before['missing_ids'])} manifest IDs")
    if before["zero_byte_count"]:
        raise ValueError(f"source tree contains {before['zero_byte_count']} zero-byte files")

    args.out_dir.mkdir(parents=True)
    plan = {
        "version": "psa-source-tree-verification-v1",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "operation": "static length and SHA-256 reads only; no PE parsing or execution",
        "samples_dir": str(args.samples_dir),
        "samples_csv": str(args.samples_csv),
        "samples_csv_sha256": digest(args.samples_csv),
        "expected_count": args.expected_count,
        "workers": args.workers,
        "directory_before": before,
    }
    with (args.out_dir / "verification_plan.json").open("x", encoding="utf-8") as handle:
        json.dump(plan, handle, indent=2, allow_nan=False)

    jobs = [(str(args.samples_dir), sample_id, length, sha256)
            for sample_id, length, sha256 in manifest]
    counts: Counter[str] = Counter()
    verified_bytes = 0
    verified_set = hashlib.sha256()
    start = time.monotonic()
    with (args.out_dir / "verification_failures.jsonl").open("x", encoding="utf-8") as failures:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            for index, (expected, result) in enumerate(
                zip(manifest, pool.map(verify_one, jobs, chunksize=32), strict=True), start=1
            ):
                counts[result["status"]] += 1
                if result["status"] == "verified":
                    verified_bytes += int(result["bytes"])
                    verified_set.update(f"{expected[0]}\0{expected[2]}\n".encode())
                else:
                    counts[result.get("error_type", "unknown_error")] += 1
                    failures.write(json.dumps(result, ensure_ascii=True, allow_nan=False) + "\n")
                    failures.flush()
                if index % 5_000 == 0 or index == len(jobs):
                    elapsed = time.monotonic() - start
                    rate = verified_bytes / max(elapsed, 1e-9) / 2**20
                    print(
                        f"{index}/{len(jobs)} verified={counts['verified']} "
                        f"errors={counts['error']} rate={rate:.1f} MiB/s",
                        flush=True,
                    )

    after = directory_state(args.samples_dir, expected_ids)
    elapsed = time.monotonic() - start
    report = {
        **plan,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": round(elapsed, 3),
        "status_counts": dict(counts),
        "verified_bytes": verified_bytes,
        "throughput_mib_s": verified_bytes / max(elapsed, 1e-9) / 2**20,
        "verified_id_sha256_set_digest": verified_set.hexdigest(),
        "failures_sha256": digest(args.out_dir / "verification_failures.jsonl"),
        "directory_after": after,
        "expected_population_verified": counts["verified"] == len(jobs) and counts["error"] == 0,
        "exact_directory_match": not after["missing_ids"] and not after["unexpected_files"],
        "p2_integrity_gate_passed": counts["verified"] == len(jobs) and counts["error"] == 0,
    }
    with (args.out_dir / "source_integrity_report.json").open("x", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, allow_nan=False)
    print(json.dumps(report, indent=2, allow_nan=False))
    return 0 if report["p2_integrity_gate_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
