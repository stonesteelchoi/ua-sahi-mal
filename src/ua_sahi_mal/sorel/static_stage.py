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
def _peatlas_coverage(data: bytes) -> tuple[str, float | None, dict[str, int]]:
    """Return (status, ok_fraction, histogram). status 'skipped:...' if unavailable."""
    try:
        from ua_sahi_mal.peatlas.atlas import PeAtlas, parse_pe
    except ImportError:
        return "skipped:peatlas_unavailable", None, {}
    try:
        layout = parse_pe(data)
        atlas = PeAtlas.from_bytes(data)
    except Exception as exc:  # noqa: BLE001 - recorded as a status
        name = type(exc).__name__
        return f"error:{name}: {exc}", None, {}
    _ = layout  # parse succeeded; layout kept for clarity
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
    return "ok", frac, hist


def _pefile_crosscheck(data: bytes) -> str:
    """Compare section fields against PEAtlas (both optional). status string."""
    try:
        import pefile  # type: ignore
    except ImportError:
        return "skipped:pefile_unavailable"
    try:
        from ua_sahi_mal.peatlas.atlas import parse_pe
    except ImportError:
        return "skipped:peatlas_unavailable"
    try:
        layout = parse_pe(data)
        pe = pefile.PE(data=data, fast_load=True)
    except Exception as exc:  # noqa: BLE001
        return f"error:{type(exc).__name__}: {exc}"
    try:
        pe_sections = [
            (s.Name.rstrip(b"\x00").decode("latin-1", "replace"),
             int(s.VirtualAddress), int(s.PointerToRawData), int(s.SizeOfRawData))
            for s in pe.sections
        ]
    finally:
        pe.close()
    ours = [(s.name, s.rva, s.raw_offset, s.raw_size) for s in layout.sections]
    if len(ours) != len(pe_sections):
        return f"mismatch:section_count ours={len(ours)} pefile={len(pe_sections)}"
    for i, (a, b) in enumerate(zip(ours, pe_sections, strict=True)):
        if a[1:] != b[1:]:  # compare rva/raw_offset/raw_size (names may pad differently)
            return f"mismatch:section[{i}] ours={a} pefile={b}"
    return "ok"


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
        status, frac, hist = _peatlas_coverage(data)
        res.peatlas_status = status
        res.coverage_ok_fraction = frac
        res.status_histogram = hist
    if run_pefile:
        res.independent_parser_status = _pefile_crosscheck(data)
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
