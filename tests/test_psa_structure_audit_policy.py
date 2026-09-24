"""Synthetic-only checks for P2 structure-audit adjudication policy."""

import hashlib
import csv
import json
import struct
from collections import Counter

import pytest

from scripts.psa_structure_audit import (POLICY_STRICT, POLICY_UNKNOWN, audit_one,
                                         count_ledger_record, mark_test_attribution, select_rows)
from ua_sahi_mal.peatlas.pebuild import SectionSpec, build_pe


def _write_sample(tmp_path, sample_id, data):
    samples = tmp_path / "samples"
    samples.mkdir(exist_ok=True)
    (samples / sample_id).write_bytes(data)
    return samples


def test_strict_mode_keeps_malformed_header_as_error(tmp_path):
    data = bytearray(build_pe(sections=[SectionSpec(".text", 0x1000, 0x200, 0x200, 0x200)]))
    pe_offset = struct.unpack_from("<I", data, 0x3C)[0]
    optional_offset = pe_offset + 24
    struct.pack_into("<I", data, optional_offset + 92, 17)
    samples = _write_sample(tmp_path, "7", bytes(data))

    record = audit_one((str(samples), "7", "train", len(data), hashlib.sha256(data).hexdigest(), POLICY_STRICT))

    assert record["status"] == "error"
    assert record["error_type"] == "PeFormatError"
    assert record["p2_reason"] == "directory_count_exceeds_optional_header_capacity"


@pytest.mark.parametrize("fault,reason", [
    ("directory_count", "directory_count_exceeds_optional_header_capacity"),
    ("short_optional_header", "declared_optional_header_missing_or_truncated"),
])
def test_unknown_policy_retains_malformed_header_as_unknown(tmp_path, fault, reason):
    data = bytearray(build_pe(sections=[SectionSpec(".text", 0x1000, 0x200, 0x200, 0x200)]))
    pe_offset = struct.unpack_from("<I", data, 0x3C)[0]
    optional_offset = pe_offset + 24
    if fault == "directory_count":
        struct.pack_into("<I", data, optional_offset + 92, 17)
    else:
        struct.pack_into("<H", data, pe_offset + 20, 80)
    samples = _write_sample(tmp_path, "7", bytes(data))

    record = audit_one((str(samples), "7", "train", len(data), hashlib.sha256(data).hexdigest(), POLICY_UNKNOWN))

    assert record["status"] == "accepted_unknown_fallback"
    assert record["p2_reason"] == reason
    assert record["adjudication"]["reason"] == reason
    assert record["structure"]["region_bytes"]["unknown"] == len(data)
    assert record["structure"]["warnings"] == [f"conservative_unknown_v1:{reason}"]
    assert record["crosscheck"]["comparison_available"] is False
    assert record["crosscheck"]["status"] == "parse_error"


def test_synthetic_ledger_counts_fallbacks_and_reasons(tmp_path):
    records = []
    for sid, fault in (("7", "directory_count"), ("8", "short_optional_header")):
        data = bytearray(build_pe(sections=[SectionSpec(".text", 0x1000, 0x200, 0x200, 0x200)]))
        pe_offset = struct.unpack_from("<I", data, 0x3C)[0]
        if fault == "directory_count":
            struct.pack_into("<I", data, pe_offset + 24 + 92, 17)
        else:
            struct.pack_into("<H", data, pe_offset + 20, 80)
        samples = _write_sample(tmp_path, sid, bytes(data))
        records.append(audit_one((str(samples), sid, "train", len(data),
                                  hashlib.sha256(data).hexdigest(), POLICY_UNKNOWN)))
    counts = {"status": Counter(), "mismatch_fields": Counter(), "warnings": Counter(),
              "p2_reason": Counter(), "fallback_reason": Counter(),
              "native_overlay_disagreements": 0}
    ledger_path = tmp_path / "synthetic_ledger.jsonl"
    ledger_path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
    for line in ledger_path.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        count_ledger_record(record, counts)

    assert counts["status"] == {"accepted_unknown_fallback": 2}
    assert counts["p2_reason"] == {
        "directory_count_exceeds_optional_header_capacity": 1,
        "declared_optional_header_missing_or_truncated": 1,
    }
    assert counts["fallback_reason"] == counts["p2_reason"]
    assert sum(counts["fallback_reason"].values()) == 2


def test_unknown_policy_does_not_mask_source_hash_mismatch(tmp_path):
    samples = _write_sample(tmp_path, "7", b"changed")

    record = audit_one((str(samples), "7", "train", 7, hashlib.sha256(b"expected").hexdigest(), POLICY_UNKNOWN))

    assert record["status"] == "error"
    assert record["error"] == "source SHA256 differs from manifest"


def _csv(path, columns, rows):
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(columns)
        writer.writerows(rows)


def test_main_and_era_test_selection_preserves_train_val_default(tmp_path):
    _csv(tmp_path / "raster_duplicate_groups.csv", ["sample_id", "raster_sha256"],
         [["1", "a"], ["2", "b"], ["3", "c"], ["4", "d"], ["5", "d"]])
    _csv(tmp_path / "raster_index.csv", ["sample_id", "split", "file_size"],
         [["1", "train", 1], ["2", "val", 1], ["3", "test", 1],
          ["4", "test", 1], ["5", "test", 1]])
    era = tmp_path / "era.csv"
    _csv(era, ["sample_id", "split"],
         [["1", "test"], ["2", "train"], ["3", "val"],
          ["4", "test"], ["5", "test"]])
    assert [r["sample_id"] for r in select_rows(tmp_path, "train-val")[0]] == ["1", "2"]
    assert [r["sample_id"] for r in select_rows(tmp_path, "test")[0]] == ["3", "4"]
    assert [r["sample_id"] for r in select_rows(tmp_path, "test", era)[0]] == ["1", "4"]


def test_test_anomalies_remain_without_structure_attribution():
    parse_error = {"status": "error", "source_sha256": "abc", "error_type": "PeFormatError"}
    disagreement = {"status": "disagreement", "structure": {"region_bytes": {"header": 1}}}
    valid = {"status": "accepted_unknown_fallback", "structure": {"region_bytes": {"unknown": 1}}}
    assert mark_test_attribution(parse_error) == "unclassified_parse_error"
    assert parse_error["structure_attribution_available"] is False
    assert mark_test_attribution(disagreement) == "non_target_disagreement"
    assert disagreement["structure"] is None
    counts = {"status": Counter(), "mismatch_fields": Counter(), "warnings": Counter(),
              "p2_reason": Counter(), "fallback_reason": Counter(),
              "native_overlay_disagreements": 0}
    count_ledger_record(disagreement, counts)
    assert counts["status"] == {"disagreement": 1}
    assert mark_test_attribution(valid) is None
    assert valid["structure_attribution_available"] is True
