"""Summarize hash-valid P2 parser edge cases without executing source files.

Only failure-ledger IDs are opened. Output contains parser metadata and error
classes, not source bytes or reversible representations.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

import pefile


def diagnose(ledger_path: Path, samples_dir: Path) -> dict:
    cases = []
    counts = Counter()
    root = samples_dir.resolve()
    with ledger_path.open(encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            if record["status"] not in {"error", "disagreement"}:
                continue
            if "source_sha256" not in record:
                counts["source_integrity_errors_skipped"] += 1
                continue
            sid = record["sample_id"]
            if not sid.isdecimal():
                raise ValueError("nondecimal sample ID in ledger")
            source = (root / sid).resolve()
            if not source.is_relative_to(root):
                raise ValueError(f"source path escapes sample directory: {sid}")
            data = source.read_bytes()
            if hashlib.sha256(data).hexdigest() != record["source_sha256"]:
                raise ValueError(f"source changed since P2 ledger: {sid}")
            case = {"sample_id": sid, "status": record["status"],
                    "p2_error": record.get("error"),
                    "mismatch_fields": [m["field"] for m in record.get("crosscheck", {}).get("mismatches", [])]}
            try:
                pe = pefile.PE(data=data, fast_load=True)
                try:
                    declared_sections = int(pe.FILE_HEADER.NumberOfSections)
                    accepted_sections = len(pe.sections)
                    size_opt = int(pe.FILE_HEADER.SizeOfOptionalHeader)
                    magic = int(pe.OPTIONAL_HEADER.Magic)
                    num_dirs = int(pe.OPTIONAL_HEADER.NumberOfRvaAndSizes)
                    directory_start = 112 if magic == 0x20B else 96
                    capacity = max(0, (size_opt - directory_start) // 8)
                    case.update(pefile_parsed=True, declared_sections=declared_sections,
                                accepted_sections=accepted_sections,
                                size_of_optional_header=size_opt,
                                declared_directories=num_dirs,
                                directory_capacity_by_declared_size=capacity,
                                pefile_parsed_directories=len(pe.OPTIONAL_HEADER.DATA_DIRECTORY),
                                pefile_warning_count=len(pe.get_warnings()))
                    counts["pefile_parsed"] += 1
                    if num_dirs > capacity:
                        counts["directory_count_exceeds_declared_capacity"] += 1
                    if accepted_sections != declared_sections:
                        counts["pefile_accepts_fewer_sections"] += 1
                finally:
                    pe.close()
            except pefile.PEFormatError as exc:
                case.update(pefile_parsed=False, pefile_error=str(exc))
                counts["pefile_parse_error"] += 1
            counts["p2_" + record["status"]] += 1
            cases.append(case)
    return {"version": "psa-p2-edge-diagnostic-v1", "cases_n": len(cases),
            "counts": dict(counts), "cases": cases, "source_payload_executed": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--samples-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError(f"refusing to overwrite {args.out}")
    report = diagnose(args.ledger, args.samples_dir)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, allow_nan=False)
    print(json.dumps({k: v for k, v in report.items() if k != "cases"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
