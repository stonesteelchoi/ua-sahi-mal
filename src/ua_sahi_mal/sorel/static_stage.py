"""Static-only analysis of acquired SOREL-20M artefacts (amendment §6/§7).

This stage is the ONLY place a downloaded artefact is decompressed, and it does so
transiently, in memory, for static analysis alone. Hard invariants:

  * ``static_only=True`` is required. Without it, decompression is refused.
  * Decompressed bytes are NEVER written to disk. Only derived, non-executable
    analysis (hashes, coverage numbers, MapStatus histograms) is persisted.
  * The disarming is verified, never undone: the PE ``Machine`` and ``Subsystem``
    fields must still be zero. A non-zero (armed) file is refused and flagged; this
    module never re-arms.
  * Nothing is executed or disassembled. Parsing is pure structural mapping.

The PEAtlas coverage analysis is an OPTIONAL import: on a tree without the
``peatlas`` package (e.g. ``codex/sorel-tooling`` off ``main``), the safety checks,
decompression, and hashing still run; the coverage fields are marked
``skipped:peatlas_unavailable``. The independent-parser cross-check (pefile) is
likewise optional.
"""

from __future__ import annotations

import hashlib
import struct
import zlib
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from .paths import assert_isolated_binary_dir


class StaticOnlyNotAcknowledgedError(RuntimeError):
    """Raised when analysis is attempted without the static-only acknowledgement."""


class NotDisarmedError(RuntimeError):
    """Raised when an artefact's Machine/Subsystem are not both zero (armed)."""


@dataclass
class StaticResult:
    sorel_original_sha256: str
    disarmed_local_sha256: str = ""
    decompressed_size: int = 0
    disarm_ok: bool = False
    peatlas_status: str = ""
    independent_parser_status: str = ""
    coverage_ok_fraction: float | None = None
    status_histogram: dict[str, int] = field(default_factory=dict)
    # post-download strata (amendment §6.3): filled when peatlas parses the file
    is_pe32_plus: bool | None = None
    n_sections: int | None = None
    overlay_bytes: int | None = None
    # E1 primary gate (amendment §7): offset->RVA->offset and offset->VA->offset round
    # trips at sampled points of every successfully mapped segment. Errors must be 0.
    roundtrip_points: int = 0
    roundtrip_errors: int = 0
    # offset<->pixel round trips for the two supported projections (raw-rgb, word16-rgb)
    pixel_roundtrip_points: int = 0
    pixel_roundtrip_errors: int = 0
    # cross-parser agreement on the MAPPING-relevant view: the set of (raw_offset, raw_size)
    # of sections that carry raw data. None when either parser is unavailable/errored.
    independent_raw_agreement: bool | None = None
    exclusion_reason: str = ""


# --------------------------------------------------------------------------- #
# Disarm verification (pure stdlib; no peatlas needed)
# --------------------------------------------------------------------------- #
def _u16(b: bytes, off: int) -> int:
    return struct.unpack_from("<H", b, off)[0]


def _u32(b: bytes, off: int) -> int:
    return struct.unpack_from("<I", b, off)[0]


def locate_pe_fields(data: bytes) -> tuple[int, int]:
    """Return (machine, subsystem) reading the PE headers. Raises on malformed PE.

    Machine  = COFF header offset 0        -> e_lfanew + 4
    Subsystem = optional header offset 68   -> e_lfanew + 24 + 68  (same for PE32/PE32+)
    """
    if len(data) < 0x40 or data[0:2] != b"MZ":
        raise ValueError("not a PE (missing MZ / too small)")
    e_lfanew = _u32(data, 0x3C)
    if e_lfanew + 24 + 70 > len(data):
        raise ValueError("PE header points past end of file")
    if data[e_lfanew:e_lfanew + 4] != b"PE\x00\x00":
        raise ValueError("missing PE signature")
    machine = _u16(data, e_lfanew + 4)
    subsystem = _u16(data, e_lfanew + 24 + 68)
    return machine, subsystem


def verify_disarmed(data: bytes) -> bool:
    """True iff Machine == 0 and Subsystem == 0 (SOREL disarming intact)."""
    machine, subsystem = locate_pe_fields(data)
    return machine == 0 and subsystem == 0


# --------------------------------------------------------------------------- #
# Optional analyzers
# --------------------------------------------------------------------------- #
def _peatlas_coverage(data: bytes) -> tuple[str, float | None, dict[str, int], dict[str, object]]:
    """Return (status, ok_fraction, histogram, layout_facts). status 'skipped:...' if unavailable.

    ``layout_facts`` carries post-download strata (PE32/PE32+, section count, overlay size)
    when parsing succeeds; empty otherwise.
    """
    try:
        from ua_sahi_mal.peatlas.atlas import PeAtlas, parse_pe
    except ImportError:
        return "skipped:peatlas_unavailable", None, {}, {}
    try:
        layout = parse_pe(data)
        atlas = PeAtlas.from_bytes(data)
    except Exception as exc:  # noqa: BLE001 - recorded as a status
        name = type(exc).__name__
        return f"error:{name}: {exc}", None, {}, {}
    facts: dict[str, object] = {
        "is_pe32_plus": bool(layout.is_pe32_plus),
        "n_sections": len(layout.sections),
        "overlay_bytes": max(0, len(data) - int(layout.overlay_offset)),
    }
    _mapped, segments = atlas.map_offset_interval(0, len(data))
    hist: dict[str, int] = {}
    ok_len = 0
    total = 0
    for seg in segments:
        length = seg.source.length
        total += length
        hist[seg.status.value] = hist.get(seg.status.value, 0) + length
        if seg.status.is_ok:
            ok_len += length
    frac = (ok_len / total) if total else None
    rt_points, rt_errors = _roundtrip_check(atlas, segments)
    facts["roundtrip_points"] = rt_points
    facts["roundtrip_errors"] = rt_errors
    px_points, px_errors = _pixel_roundtrip_check(len(data), segments)
    facts["pixel_roundtrip_points"] = px_points
    facts["pixel_roundtrip_errors"] = px_errors
    return "ok", frac, hist, facts


def _sample_points(start: int, end: int) -> list[int]:
    """Boundary-aware sample points of a half-open segment: start, middle, end-1."""
    if end <= start:
        return []
    pts = {start, start + (end - start) // 2, end - 1}
    return sorted(pts)


def _roundtrip_check(atlas, segments) -> tuple[int, int]:  # type: ignore[no-untyped-def]
    """E1 primary gate: every sampled offset in an OK/HEADERS segment must round-trip
    offset->RVA->offset and offset->VA->offset exactly. Returns (points, errors)."""
    points = errors = 0
    for seg in segments:
        if not seg.status.is_ok:
            continue  # explicit failure states are not round-trippable by contract
        for off in _sample_points(seg.source.start, seg.source.end):
            points += 1
            try:
                r = atlas.offset_to_rva(off)
                back = atlas.rva_to_offset(r.value) if r.ok else None
                v = atlas.offset_to_va(off)
                vback = atlas.va_to_offset(v.value) if v.ok else None
                good = (r.ok and back is not None and back.ok and back.value == off
                        and v.ok and vback is not None and vback.ok and vback.value == off)
            except Exception:  # noqa: BLE001 - counted as a round-trip error
                good = False
            if not good:
                errors += 1
    return points, errors


def _pixel_roundtrip_check(file_size: int, segments, *, width: int = 256) -> tuple[int, int]:  # type: ignore[no-untyped-def]
    """offset<->pixel round trips for raw-rgb (stride 3) and word16-rgb (stride 2).

    For sampled offsets (same points as the coordinate round trip, plus file start/end),
    byte_to_pixel_channel then pixel_to_byte_span must contain the offset, and the
    pixels_to_bytes projection of that single pixel must contain it too.
    """
    try:
        from ua_sahi_mal.peatlas.intervals import Interval, IntervalSet
        from ua_sahi_mal.peatlas.projection import PixelProjection
    except ImportError:
        return 0, 0
    import math
    offsets: set[int] = set()
    for seg in segments:
        offsets.update(_sample_points(seg.source.start, seg.source.end))
    if file_size > 0:
        offsets.update({0, file_size - 1})
    points = errors = 0
    for mode, stride in (("raw-rgb", 3), ("word16-rgb", 2)):
        pixel_count = math.ceil(file_size / stride) if file_size else 0
        height = math.ceil(pixel_count / width) if pixel_count else 0
        proj = PixelProjection(mode=mode, width=width, height=height, channels=3, stride=stride,
                               source_byte_count=file_size, pixel_count=pixel_count,
                               padded_pixel_count=max(0, width * height - pixel_count))
        for off in sorted(offsets):
            points += 1
            try:
                pix, _ch = proj.byte_to_pixel_channel(off)
                span = proj.pixel_to_byte_span(pix)
                back = proj.pixels_to_bytes(IntervalSet([Interval(pix, pix + 1)]))
                good = (span is not None and span.start <= off < span.end
                        and any(iv.start <= off < iv.end for iv in back))
            except Exception:  # noqa: BLE001
                good = False
            if not good:
                errors += 1
    return points, errors


def _pefile_crosscheck(data: bytes) -> tuple[str, bool | None]:
    """Compare section fields against PEAtlas (both optional).

    Returns (strict_status, raw_agreement). ``strict_status`` compares the full section
    lists (count + rva/raw_offset/raw_size); ``raw_agreement`` compares only the set of
    (raw_offset, raw_size) for sections that carry raw data — the view that actually
    determines offset<->RVA mapping. Parsers can legitimately differ on how many
    null/degenerate section headers they *report* while agreeing on every mapped byte.
    """
    try:
        import pefile  # type: ignore
    except ImportError:
        return "skipped:pefile_unavailable", None
    try:
        from ua_sahi_mal.peatlas.atlas import parse_pe
    except ImportError:
        return "skipped:peatlas_unavailable", None
    try:
        layout = parse_pe(data)
        pe = pefile.PE(data=data, fast_load=True)
    except Exception as exc:  # noqa: BLE001
        return f"error:{type(exc).__name__}: {exc}", None
    try:
        pe_sections = [
            (s.Name.rstrip(b"\x00").decode("latin-1", "replace"),
             int(s.VirtualAddress), int(s.PointerToRawData), int(s.SizeOfRawData))
            for s in pe.sections
        ]
    finally:
        pe.close()
    ours = [(s.name, s.rva, s.raw_offset, s.raw_size) for s in layout.sections]
    raw_ours = {(s.raw_offset, s.raw_size) for s in layout.sections if s.has_raw}
    raw_pe = {(off, size) for (_n, _rva, off, size) in pe_sections if size > 0 and off > 0}
    raw_agreement = raw_ours == raw_pe
    if len(ours) != len(pe_sections):
        return f"mismatch:section_count ours={len(ours)} pefile={len(pe_sections)}", raw_agreement
    for i, (a, b) in enumerate(zip(ours, pe_sections, strict=True)):
        if a[1:] != b[1:]:  # compare rva/raw_offset/raw_size (names may pad differently)
            return f"mismatch:section[{i}] ours={a} pefile={b}", raw_agreement
    return "ok", raw_agreement


# --------------------------------------------------------------------------- #
# Per-artefact processing
# --------------------------------------------------------------------------- #
def analyze_bytes(compressed: bytes, *, sha256: str, static_only: bool,
                  run_peatlas: bool = True, run_pefile: bool = True) -> StaticResult:
    """Decompress in memory and run static-only checks. No disk writes here."""
    if not static_only:
        raise StaticOnlyNotAcknowledgedError(
            "refusing to decompress without static_only=True; run only in an "
            "approved static-only isolated environment."
        )
    res = StaticResult(sorel_original_sha256=sha256)
    try:
        data = zlib.decompress(compressed)
    except zlib.error as exc:
        res.exclusion_reason = f"decompress_error:{exc}"
        return res
    res.decompressed_size = len(data)
    res.disarmed_local_sha256 = hashlib.sha256(data).hexdigest()

    try:
        disarmed = verify_disarmed(data)
    except ValueError as exc:
        res.exclusion_reason = f"not_pe:{exc}"
        return res
    res.disarm_ok = disarmed
    if not disarmed:
        # never re-arm, never analyze an armed artefact through this path
        res.exclusion_reason = "not_disarmed:Machine/Subsystem nonzero"
        return res

    if run_peatlas:
        status, frac, hist, facts = _peatlas_coverage(data)
        res.peatlas_status = status
        res.coverage_ok_fraction = frac
        res.status_histogram = hist
        if facts:
            res.is_pe32_plus = facts["is_pe32_plus"]  # type: ignore[assignment]
            res.n_sections = facts["n_sections"]  # type: ignore[assignment]
            res.overlay_bytes = facts["overlay_bytes"]  # type: ignore[assignment]
            res.roundtrip_points = int(facts.get("roundtrip_points", 0))  # type: ignore[arg-type]
            res.roundtrip_errors = int(facts.get("roundtrip_errors", 0))  # type: ignore[arg-type]
            res.pixel_roundtrip_points = int(facts.get("pixel_roundtrip_points", 0))  # type: ignore[arg-type]
            res.pixel_roundtrip_errors = int(facts.get("pixel_roundtrip_errors", 0))  # type: ignore[arg-type]
    if run_pefile:
        res.independent_parser_status, res.independent_raw_agreement = _pefile_crosscheck(data)
    # explicit scrub of the decompressed buffer reference
    del data
    return res


def analyze_file(zlib_path: str | Path, *, static_only: bool,
                 run_peatlas: bool = True, run_pefile: bool = True) -> StaticResult:
    """Analyze one ``<sha>.zlib`` file. The directory must be an isolated path."""
    p = Path(zlib_path)
    assert_isolated_binary_dir(p.parent)
    sha = p.stem  # "<sha>" from "<sha>.zlib"
    compressed = p.read_bytes()
    return analyze_bytes(compressed, sha256=sha, static_only=static_only,
                         run_peatlas=run_peatlas, run_pefile=run_pefile)


def analyze_dir(compressed_dir: str | Path, shas: Iterable[str], *, static_only: bool,
                run_peatlas: bool = True, run_pefile: bool = True) -> list[StaticResult]:
    """Analyze the ``<sha>.zlib`` files for ``shas`` under an isolated directory."""
    root = assert_isolated_binary_dir(compressed_dir)
    results: list[StaticResult] = []
    for sha in shas:
        path = root / f"{sha}.zlib"
        if not path.exists():
            r = StaticResult(sorel_original_sha256=sha, exclusion_reason="missing:zlib_not_found")
            results.append(r)
            continue
        results.append(analyze_file(path, static_only=static_only,
                                    run_peatlas=run_peatlas, run_pefile=run_pefile))
    return results
