"""Create an exact recovery manifest from a source-integrity failure ledger.

This utility reads metadata only. It does not open, move, overwrite, extract, or
execute any source sample.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples-csv", type=Path, required=True)
    parser.add_argument("--failures", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError(f"refusing to overwrite {args.out}")

    expected: dict[str, tuple[int, str]] = {}
    with args.samples_csv.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            expected[row["id"]] = (int(row["length"]), row["sha256"].lower())

    failures: dict[str, dict] = {}
    with args.failures.open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            sample_id = str(row["sample_id"])
            if sample_id in failures:
                raise ValueError(f"duplicate failure ID: {sample_id}")
            if sample_id not in expected:
                raise ValueError(f"failure ID absent from samples.csv: {sample_id}")
            failures[sample_id] = row
    if not failures:
        raise ValueError("failure ledger is empty")

    fields = [
        "sample_id",
        "expected_length",
        "expected_sha256",
        "observed_error",
        "observed_length",
        "observed_sha256",
    ]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    counts: Counter[str] = Counter()
    with args.out.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for sample_id in sorted(failures, key=int):
            failure = failures[sample_id]
            length, sha256 = expected[sample_id]
            error_type = failure.get("error_type", "unknown_error")
            counts[error_type] += 1
            writer.writerow(
                {
                    "sample_id": sample_id,
                    "expected_length": length,
                    "expected_sha256": sha256,
                    "observed_error": error_type,
                    "observed_length": failure.get("actual_size", ""),
                    "observed_sha256": failure.get("actual_sha256", ""),
                }
            )
    print(json.dumps({"recovery_count": len(failures), "error_counts": counts}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
