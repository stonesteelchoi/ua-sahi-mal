"""E2 per-file pipeline: static-only guards, stratum, silver, eval (E2_prereg_v1)."""

from __future__ import annotations

import zlib

import pytest

from ua_sahi_mal.peatlas import SectionSpec, build_pe
from ua_sahi_mal.sorel.e2_pipeline import process_compressed, process_dir
from ua_sahi_mal.sorel.e2_silver import CapaMatch
from ua_sahi_mal.sorel.paths import UnsafeOutputPathError
from ua_sahi_mal.sorel.static_stage import StaticOnlyNotAcknowledgedError

_SHA = "a" * 64


def _overlay_dominant_sample() -> bytes:
    embedded = build_pe(sections=[SectionSpec(".x", rva=0x1000, virtual_size=0x200,
                                              raw_offset=0x200, raw_size=0x200)], disarm=True)
    return build_pe(
        sections=[SectionSpec(".text", rva=0x1000, virtual_size=0x400, raw_offset=0x400, raw_size=0x400)],
        overlay=embedded + b"\x00" * 8192, disarm=True,
    )


def test_process_compressed_capa_disabled():
    comp = zlib.compress(_overlay_dominant_sample())
    res = process_compressed(comp, sha256=_SHA, static_only=True, enable_capa=False)
    assert res.ok
    assert res.stratum == "overlay_dominant" and res.overlay_share > 0.5
    assert res.silver["embedded_count"] >= 1 and res.silver["capa_status"] == "disabled"
    assert res.evaluation["has_silver"]


def test_process_compressed_capa_injected():
    comp = zlib.compress(_overlay_dominant_sample())

    def runner(data, *, timeout, image_base, work_dir=None):
        return [CapaMatch(rule="inject", fn_start_rva=0x1000, fn_end_rva=0x1080)]

    res = process_compressed(comp, sha256=_SHA, static_only=True, enable_capa=True, capa_runner=runner)
    assert res.silver["capa_status"] == "ok" and res.silver["capa_intervals"]


def test_process_compressed_yara_injected():
    comp = zlib.compress(_overlay_dominant_sample())

    def matcher(data):
        off = data.find(b"MZ", 1)          # the embedded PE's MZ, in the overlay
        return [(off, 4, "mz_magic")] if off != -1 else []

    res = process_compressed(comp, sha256=_SHA, static_only=True, enable_yara=True, yara_matcher=matcher)
    assert res.silver["yara_status"] == "ok" and res.silver["yara_intervals"]
    assert res.silver["capa_status"] == "disabled"


def test_armed_sample_refused():
    armed = build_pe(sections=[SectionSpec(".text", rva=0x1000, virtual_size=0x400,
                                           raw_offset=0x400, raw_size=0x400)], disarm=False)
    res = process_compressed(zlib.compress(armed), sha256=_SHA, static_only=True, enable_capa=False)
    assert not res.ok and res.exclusion_reason == "armed:refused"


def test_static_only_guard():
    comp = zlib.compress(_overlay_dominant_sample())
    with pytest.raises(StaticOnlyNotAcknowledgedError):
        process_compressed(comp, sha256=_SHA, static_only=False, enable_capa=False)


def test_decompress_error():
    res = process_compressed(b"not-zlib", sha256=_SHA, static_only=True, enable_capa=False)
    assert not res.ok and res.exclusion_reason.startswith("decompress_error")


def test_process_dir_isolated_and_missing(iso_dir):
    (iso_dir / f"{_SHA}.zlib").write_bytes(zlib.compress(_overlay_dominant_sample()))
    results = process_dir(iso_dir, [_SHA, "b" * 64], static_only=True, enable_capa=False)
    assert len(results) == 2
    assert results[0].ok
    assert results[1].exclusion_reason == "missing:zlib_not_found"


def test_process_dir_refuses_non_isolated_path(tmp_path_factory):
    # the repo tree (where this test lives) must be rejected by the isolated-dir guard
    from pathlib import Path

    repo_dir = Path(__file__).resolve().parent
    with pytest.raises(UnsafeOutputPathError):
        process_dir(repo_dir, [_SHA], static_only=True, enable_capa=False)
