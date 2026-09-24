import csv
import hashlib
import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "psa_verify_source_tree.py"
SPEC = importlib.util.spec_from_file_location("psa_verify_source_tree", SCRIPT)
assert SPEC and SPEC.loader
verify = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verify)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_manifest(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "length", "sha256"])
        writer.writeheader()
        writer.writerows(rows)


def test_verify_one_accepts_exact_static_bytes(tmp_path):
    data = b"MZ" + bytes(range(32))
    (tmp_path / "7").write_bytes(data)
    result = verify.verify_one((str(tmp_path), "7", len(data), sha256(data)))
    assert result == {"sample_id": "7", "status": "verified", "bytes": len(data)}


def test_verify_one_reports_size_before_hash(tmp_path):
    (tmp_path / "8").write_bytes(b"wrong-size")
    result = verify.verify_one((str(tmp_path), "8", 3, sha256(b"abc")))
    assert result["status"] == "error"
    assert result["error_type"] == "size_mismatch"
    assert result["expected_size"] == 3
    assert result["actual_size"] == 10


def test_verify_one_reports_same_size_hash_mismatch(tmp_path):
    (tmp_path / "9").write_bytes(b"abd")
    result = verify.verify_one((str(tmp_path), "9", 3, sha256(b"abc")))
    assert result["status"] == "error"
    assert result["error_type"] == "sha256_mismatch"
    assert result["actual_sha256"] == sha256(b"abd")


def test_manifest_and_directory_state_are_exact(tmp_path):
    samples = tmp_path / "samples"
    samples.mkdir()
    (samples / "1").write_bytes(b"a")
    (samples / "2").write_bytes(b"bb")
    (samples / "extra.jpg").write_bytes(b"extra")
    manifest = tmp_path / "samples.csv"
    write_manifest(
        manifest,
        [
            {"id": "2", "length": 2, "sha256": sha256(b"bb")},
            {"id": "1", "length": 1, "sha256": sha256(b"a")},
        ],
    )
    rows = verify.load_manifest(manifest, 2)
    assert [row[0] for row in rows] == ["1", "2"]
    state = verify.directory_state(samples, {"1", "2"})
    assert state == {
        "file_count": 3,
        "missing_ids": [],
        "unexpected_files": ["extra.jpg"],
        "zero_byte_count": 0,
    }


def test_manifest_rejects_duplicate_id(tmp_path):
    manifest = tmp_path / "samples.csv"
    write_manifest(
        manifest,
        [
            {"id": "1", "length": 1, "sha256": sha256(b"a")},
            {"id": "1", "length": 1, "sha256": sha256(b"a")},
        ],
    )
    with pytest.raises(ValueError, match="duplicate sample id"):
        verify.load_manifest(manifest, 2)
