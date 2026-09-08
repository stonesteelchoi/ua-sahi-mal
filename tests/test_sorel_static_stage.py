"""Network-free, malware-free tests for the static-only analysis stage.

Uses hand-built minimal PE byte buffers (disarmed vs armed). No real sample is
ever decompressed here.
"""

from __future__ import annotations

import hashlib
import struct
import zlib

import pytest

from ua_sahi_mal.sorel.paths import UnsafeOutputPathError
from ua_sahi_mal.sorel.static_stage import (
    NotDisarmedError,  # noqa: F401 - part of the public surface
    StaticOnlyNotAcknowledgedError,
    analyze_bytes,
    analyze_dir,
    analyze_file,
    locate_pe_fields,
    verify_disarmed,
)


def build_min_pe(*, machine: int, subsystem: int, size: int = 512) -> bytes:
    """Minimal PE: e_lfanew=0x40, PE sig, COFF Machine, optional Subsystem@+68."""
    buf = bytearray(size)
    buf[0:2] = b"MZ"
    e_lfanew = 0x40
    struct.pack_into("<I", buf, 0x3C, e_lfanew)
    buf[e_lfanew:e_lfanew + 4] = b"PE\x00\x00"
    struct.pack_into("<H", buf, e_lfanew + 4, machine)          # COFF Machine
    struct.pack_into("<H", buf, e_lfanew + 24, 0x10B)           # optional Magic (PE32)
    struct.pack_into("<H", buf, e_lfanew + 24 + 68, subsystem)  # Subsystem
    return bytes(buf)


DISARMED = build_min_pe(machine=0, subsystem=0)
ARMED = build_min_pe(machine=0x8664, subsystem=2)


def test_locate_and_verify():
    assert locate_pe_fields(DISARMED) == (0, 0)
    assert locate_pe_fields(ARMED) == (0x8664, 2)
    assert verify_disarmed(DISARMED) is True
    assert verify_disarmed(ARMED) is False


def test_static_only_gate():
    with pytest.raises(StaticOnlyNotAcknowledgedError):
        analyze_bytes(zlib.compress(DISARMED), sha256="a" * 64, static_only=False)


def test_disarmed_decompress_and_hash():
    r = analyze_bytes(zlib.compress(DISARMED), sha256="a" * 64, static_only=True)
    assert r.disarm_ok is True
    assert r.decompressed_size == len(DISARMED)
    assert r.disarmed_local_sha256 == hashlib.sha256(DISARMED).hexdigest()
    assert not r.exclusion_reason
    # peatlas may be present or not; either is acceptable
    assert r.peatlas_status in ("ok", "skipped:peatlas_unavailable") or r.peatlas_status.startswith("error")
    if r.peatlas_status == "ok":
        assert r.coverage_ok_fraction is not None


def test_armed_is_refused_not_rearmed():
    r = analyze_bytes(zlib.compress(ARMED), sha256="b" * 64, static_only=True)
    assert r.disarm_ok is False
    assert r.exclusion_reason.startswith("not_disarmed")
    # armed file is not analyzed
    assert r.peatlas_status == ""
    assert r.independent_parser_status == ""
    # hash is still recorded (of the untouched decompressed bytes)
    assert r.disarmed_local_sha256 == hashlib.sha256(ARMED).hexdigest()


def test_not_pe():
    r = analyze_bytes(zlib.compress(b"\x00" * 256), sha256="c" * 64, static_only=True)
    assert r.exclusion_reason.startswith("not_pe")
    assert r.disarm_ok is False


def test_decompress_error():
    r = analyze_bytes(b"not-zlib-data", sha256="d" * 64, static_only=True)
    assert r.exclusion_reason.startswith("decompress_error")
    assert r.decompressed_size == 0


def test_analyze_file_no_disk_write(iso_dir):
    d = iso_dir / "sorel-private" / "compressed"
    d.mkdir(parents=True)
    sha = "e" * 64
    (d / f"{sha}.zlib").write_bytes(zlib.compress(DISARMED))
    before = {p.name for p in d.iterdir()}
    r = analyze_file(d / f"{sha}.zlib", static_only=True)
    after = {p.name for p in d.iterdir()}
    # only the .zlib remains; no decompressed binary was ever written
    assert before == after == {f"{sha}.zlib"}
    assert r.sorel_original_sha256 == sha
    assert r.disarm_ok is True


def test_analyze_file_refuses_repo_dir(iso_dir):
    (iso_dir / ".git").mkdir()
    d = iso_dir / "compressed"
    d.mkdir()
    (d / ("f" * 64 + ".zlib")).write_bytes(zlib.compress(DISARMED))
    with pytest.raises(UnsafeOutputPathError, match="repository tree"):
        analyze_file(d / ("f" * 64 + ".zlib"), static_only=True)


def test_analyze_dir_missing_and_ok(iso_dir):
    d = iso_dir / "sorel-private" / "compressed"
    d.mkdir(parents=True)
    present = "a" * 64
    absent = "b" * 64
    (d / f"{present}.zlib").write_bytes(zlib.compress(DISARMED))
    results = analyze_dir(d, [present, absent], static_only=True)
    by = {r.sorel_original_sha256: r for r in results}
    assert by[present].disarm_ok is True
    assert by[absent].exclusion_reason.startswith("missing")
