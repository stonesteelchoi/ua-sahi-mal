"""Synthetic-only P2 edge-diagnostic tests."""

import hashlib
import json
import struct

import pytest

from scripts.psa_diagnose_p2_edge_cases import diagnose
from ua_sahi_mal.peatlas.pebuild import SectionSpec, build_pe


def test_declared_directory_overflow_is_reported(tmp_path):
    data = bytearray(build_pe(sections=[SectionSpec(".text", 0x1000, 0x200, 0x200, 0x200)]))
    pe_offset = struct.unpack_from("<I", data, 0x3C)[0]
    optional_offset = pe_offset + 24
    struct.pack_into("<I", data, optional_offset + 92, 17)
    samples_dir = tmp_path / "samples"
    samples_dir.mkdir()
    (samples_dir / "7").write_bytes(data)
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text(json.dumps({"sample_id": "7", "status": "error",
                                  "source_sha256": hashlib.sha256(data).hexdigest(),
                                  "error": "data directories exceed declared optional header"}) + "\n")

    report = diagnose(ledger, samples_dir)

    assert report["cases_n"] == 1
    assert report["counts"]["directory_count_exceeds_declared_capacity"] == 1
    assert report["cases"][0]["directory_capacity_by_declared_size"] == 16
    assert report["cases"][0]["declared_directories"] == 17


def test_changed_source_is_rejected(tmp_path):
    samples_dir = tmp_path / "samples"
    samples_dir.mkdir()
    (samples_dir / "7").write_bytes(b"changed")
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text(json.dumps({"sample_id": "7", "status": "error",
                                  "source_sha256": hashlib.sha256(b"original").hexdigest(),
                                  "error": "sample parser error"}) + "\n")

    with pytest.raises(ValueError, match="source changed"):
        diagnose(ledger, samples_dir)
