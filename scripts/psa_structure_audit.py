"""Static-only structure audit on a deduplicated split population.

The default train/validation path retains its pre-freeze gate. The explicit test
path is descriptive after protocol freeze. No model is evaluated, and every
selected ID receives a ledger row, including parser disagreements and errors.
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

from ua_sahi_mal.kisa_xai.structure import (
    STRUCTURE_VERSION,
    UNKNOWN_FALLBACK_POLICY,
    P2_SECTION_DISAGREEMENT_POLICY,
    build_structure_map,
    build_unknown_structure_map,
    compare_pefile,
    p2_malformed_header_reason,
    p2_section_disagreement_reason,
)


POLICY_STRICT = "strict"
POLICY_UNKNOWN = UNKNOWN_FALLBACK_POLICY
P2_EXPECTED_FALLBACK_REASONS = {
    "directory_count_exceeds_optional_header_capacity": 62,
    "declared_optional_header_missing_or_truncated": 1,
    "section_count_disagreement": 10,
}


def _unknown_adjudication(reason: str, detail: dict | None = None,
                          policy_version: str = "P2-MALFORMED-HEADER-V1") -> dict:
    return {
        "policy": POLICY_UNKNOWN,
        "policy_version": policy_version,
        "action": "map_entire_file_as_unknown",
        "reason": reason,
        "detail": detail or {},
        "claim": "sample_retained_without_fabricated_structure_labels",
    }


def digest(path):
    with Path(path).open("rb") as fh:
        return hashlib.file_digest(fh, "sha256").hexdigest()


def audit_one(job):
    root, sid, split, expected_size, expected_hash, adjudication_policy = job
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
        try:
            structure = build_structure_map(data)
        except Exception as exc:
            reason = p2_malformed_header_reason(exc)
            if reason is not None:
                record["p2_reason"] = reason
            if adjudication_policy == POLICY_UNKNOWN and reason is not None:
                record["structure"] = build_unknown_structure_map(data, reason).to_dict()
                record["crosscheck"] = {
                    "raw_fields_agree": False,
                    "mismatches": [],
                    "fields_compared": 0,
                    "comparison_available": False,
                    "status": "parse_error",
                    "comparison_blocked_by": str(exc),
                }
                record["adjudication"] = _unknown_adjudication(
                    reason,
                    {"error_type": type(exc).__name__, "error": str(exc)},
                )
                record["status"] = "accepted_unknown_fallback"
                return record
            raise
        record["structure"] = structure.to_dict()
        comparison = compare_pefile(data)
        record["crosscheck"] = comparison
        if comparison["raw_fields_agree"]:
            record["status"] = "agreement"
        else:
            reason = p2_section_disagreement_reason(comparison)
            if adjudication_policy == POLICY_UNKNOWN and reason is not None:
                fields = {m["field"] for m in comparison["mismatches"]}
                record["pre_adjudication_region_bytes"] = record["structure"]["region_bytes"]
                record["structure"] = build_unknown_structure_map(data, reason).to_dict()
                record["p2_reason"] = reason
                record["adjudication"] = _unknown_adjudication(
                    reason,
                    {"mismatch_fields": sorted(fields), "mismatches": comparison["mismatches"]},
                    P2_SECTION_DISAGREEMENT_POLICY,
                )
                record["status"] = "accepted_unknown_fallback"
            else:
                record["status"] = "disagreement"
    except Exception as exc:  # Preserve parse/missing-file failures in the ledger, never skip.
        record["error_type"] = type(exc).__name__
        record["error"] = str(exc)
    return record


def count_ledger_record(record, counts):
    """Count only fields persisted in the ledger, including adjudication reasons."""
    counts["status"][record["status"]] += 1
    comparison = record.get("crosscheck", {})
    counts["mismatch_fields"].update(m["field"] for m in comparison.get("mismatches", []))
    counts["native_overlay_disagreements"] += int(comparison.get("native_overlay", {}).get("agrees") is False)
    counts["warnings"].update((record.get("structure") or {}).get("warnings", []))
    if record.get("p2_reason") is not None:
        counts["p2_reason"][record["p2_reason"]] += 1
    if record["status"] == "accepted_unknown_fallback":
        counts["fallback_reason"][record["adjudication"]["reason"]] += 1


def select_rows(rasters, population, split_manifest=None):
    """Apply the same duplicate exclusion to the main or an assigned split."""
    seen, drop = set(), set()
    duplicate_file = rasters / "raster_duplicate_groups.csv"
    with duplicate_file.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row["raster_sha256"] in seen:
                drop.add(row["sample_id"])
            seen.add(row["raster_sha256"])
    assignments = None
    if split_manifest is not None:
        with split_manifest.open(newline="", encoding="utf-8") as fh:
            assignments = {}
            for row in csv.DictReader(fh):
                sid = row["sample_id"]
                if sid in assignments or row["split"] not in ("train", "val", "test"):
                    raise ValueError("duplicate ID or invalid split in split manifest")
                assignments[sid] = row["split"]
    rows, raster_ids = [], set()
    with (rasters / "raster_index.csv").open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            sid = row["sample_id"]
            if assignments is not None:
                raster_ids.add(sid)
            split = assignments.get(sid) if assignments is not None else row["split"]
            if sid not in drop and split in (("test",) if population == "test" else ("train", "val")):
                rows.append(row)
    if assignments is not None and assignments.keys() - raster_ids:
        raise ValueError("split manifest contains IDs absent from raster index")
    return rows, duplicate_file


def mark_test_attribution(record):
    """Keep anomalous test IDs without claiming a trustworthy structure map."""
    if record["status"] == "error":
        reason = ("unclassified_parse_error" if "source_sha256" in record
                  else "source_validation_or_io_error")
        if "structure" in record:
            record["structure"] = None
    elif record["status"] == "disagreement":
        reason = "non_target_disagreement"
        record["structure"] = None
    else:
        record["structure_attribution_available"] = True
        return None
    record["structure_attribution_available"] = False
    record["structure_attribution_reason"] = reason
    return reason


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rasters-dir", type=Path, required=True)
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--samples-dir", type=Path, required=True)
    ap.add_argument("--outdir", type=Path, required=True)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--limit", type=int, default=0, help="0 = full selected population; positive = diagnostic subset")
    ap.add_argument("--static-only", action="store_true", required=True)
    ap.add_argument("--adjudication-policy", choices=[POLICY_STRICT, POLICY_UNKNOWN], default=POLICY_STRICT)
    ap.add_argument("--population", choices=["train-val", "test"], default="train-val")
    ap.add_argument("--split-manifest", type=Path, help="alternate split assignments, for era test")
    ap.add_argument("--split-manifest-sha256", help="expected SHA-256 of alternate split manifest")
    args = ap.parse_args()
    if args.limit < 0 or not 1 <= args.workers <= 8 or args.outdir.exists():
        raise ValueError("invalid worker/limit setting or output already exists")
    if (args.split_manifest is None) != (args.split_manifest_sha256 is None):
        raise ValueError("alternate split manifest and expected SHA-256 must be supplied together")
    if args.split_manifest is not None and args.population != "test":
        raise ValueError("alternate split manifest is supported only for test population")
    # Check optional parser before starting; absence must not produce a false success.
    import pefile

    rasters = args.rasters_dir
    expected = {
        rasters / "raster_index.csv": "94d02b247fc761d64fdea5aeac9afe2da6dc56bdcc998cc84d4a5c7d3f76f785",
        args.manifest: "3dc0bd7fb42935692462013f716bbd8ccd339b20bb436289aa93e78852b17414",
    }
    if args.split_manifest is not None:
        expected[args.split_manifest] = args.split_manifest_sha256.lower()
    for path, sha in expected.items():
        if digest(path) != sha:
            raise ValueError(f"protocol input hash mismatch: {path.name}")
    rows, duplicate_file = select_rows(rasters, args.population, args.split_manifest)
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
    jobs = [(str(args.samples_dir), r["sample_id"], r["split"], int(r["file_size"]), hashes[r["sample_id"]],
             args.adjudication_policy)
            for r in rows]
    args.outdir.mkdir(parents=True)
    plan = {"version": STRUCTURE_VERSION,
            "population": ("deduplicated_test_only" if args.population == "test"
                           else "deduplicated_train_and_validation_only"),
            "population_n": population_n, "selected_n": len(rows), "limit": args.limit,
            "sampling": "sample_id ascending; diagnostic subset only when limit > 0",
            "test_payload_access": args.population == "test", "workers": args.workers,
            "pefile_version": pefile.__version__,
            "inputs": {str(p): h for p, h in expected.items()}, "duplicate_file_sha256": digest(duplicate_file),
            "implementation_sha256": digest(Path(__file__)),
            "structure_source_sha256": digest(Path(__file__).resolve().parents[1] /
                                               "src/ua_sahi_mal/kisa_xai/structure.py"),
            "adjudication_policy": args.adjudication_policy,
            "section_disagreement_policy_version": P2_SECTION_DISAGREEMENT_POLICY,
            **({"p2_expected_fallback_reason_counts": (P2_EXPECTED_FALLBACK_REASONS
                 if args.adjudication_policy == POLICY_UNKNOWN else None)}
               if args.population != "test" else {}),
            "freeze_policy": ("Strict crosscheck: retain every disagreement/error for review."
                              if args.adjudication_policy == POLICY_STRICT
                              else "Conservative P2 adjudication: retain every selected file; map hash-valid malformed-header or isolated section disagreements entirely as unknown.")}
    with (args.outdir / "audit_plan.json").open("x", encoding="utf-8") as fh:
        json.dump(plan, fh, indent=2)
    counts = {"status": Counter(), "mismatch_fields": Counter(), "warnings": Counter(),
              "p2_reason": Counter(), "fallback_reason": Counter(),
              "unattributable_reason": Counter(),
              "native_overlay_disagreements": 0}
    start = time.monotonic()
    print((f"selected {len(rows)} / {population_n} test files" if args.population == "test"
           else f"selected {len(rows)} / {population_n} train/val files; test payloads locked"), flush=True)
    with (args.outdir / "structure_ledger.jsonl").open("x", encoding="utf-8") as ledger:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            for index, record in enumerate(pool.map(audit_one, jobs, chunksize=16), start=1):
                if args.population == "test":
                    reason = mark_test_attribution(record)
                    if reason is not None:
                        counts["unattributable_reason"][reason] += 1
                ledger.write(json.dumps(record, ensure_ascii=True, allow_nan=False) + "\n")
                count_ledger_record(record, counts)
                if index % 1000 == 0 or index == len(rows):
                    ledger.flush()
                    print(f"{index}/{len(rows)} {dict(counts['status'])} elapsed={time.monotonic()-start:.1f}s", flush=True)
    statuses = counts["status"]
    p2_gate_passed = args.population != "test" and (
        args.limit == 0
        and sum(statuses.values()) == len(rows)
        and statuses["error"] == 0
        and statuses["disagreement"] == 0
        and args.adjudication_policy == POLICY_UNKNOWN
        and dict(counts["fallback_reason"]) == P2_EXPECTED_FALLBACK_REASONS
        and dict(counts["p2_reason"]) == P2_EXPECTED_FALLBACK_REASONS
    )
    report = {**plan, "complete": sum(statuses.values()) == len(rows), "status_counts": dict(statuses),
              "mismatch_fields": dict(counts["mismatch_fields"]),
              "structure_warnings": dict(counts["warnings"]),
              "p2_reason_counts": dict(counts["p2_reason"]),
              "fallback_count": sum(counts["fallback_reason"].values()),
              "fallback_reason_counts": dict(counts["fallback_reason"]),
              "native_overlay_disagreements": counts["native_overlay_disagreements"],
              "elapsed_seconds": round(time.monotonic() - start, 3),
              "ledger_sha256": digest(args.outdir / "structure_ledger.jsonl"),
              **({"unattributable_count": sum(counts["unattributable_reason"].values()),
                  "unattributable_reason_counts": dict(counts["unattributable_reason"])}
                 if args.population == "test" else {}),
              **({} if args.population == "test" else
                 {"p2_structure_gate_passed": p2_gate_passed,
                  "protocol_freeze_authorized": False})}
    with (args.outdir / "structure_audit_summary.json").open("x", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, allow_nan=False)
    print(json.dumps({k: v for k, v in report.items() if k not in ("structure_warnings", "inputs")}, indent=2))
    if args.population == "test":
        return 0 if report["complete"] else 2
    return 0 if (p2_gate_passed or (args.limit > 0 and not statuses["error"]
                                   and not statuses["disagreement"])) else 2


if __name__ == "__main__":
    raise SystemExit(main())
