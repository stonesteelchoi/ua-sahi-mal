"""E2 silver-evidence extraction (frozen: ``E2_prereg_v1`` / ``E2_prereg_v2``).

Silver evidence is the weak, tool-attributed localization target E2 measures
selectors against (gold DeepReflect/Binary Ninja labels are excluded in v3).
Sources, unioned per file:

* ``embedded_artifact`` (byte scope): embedded PE images found by scanning the
  raw bytes. Overlay-safe. Pure, in memory, no execution.
* ``yara`` (byte scope): YARA rule string matches, scanned IN MEMORY
  (``rules.match(data=...)``) — no disk write, no disassembly, so it does not
  trip resident AV. The v2 in-memory substitute for capa on the AV-monitored
  operator machine.
* ``capa`` (function scope): capability matches -> enclosing function RVA extent
  -> file offsets via the E1-verified :meth:`PeAtlas.map_component`.

  SAFETY: capa's vivisect backend (``viv_utils.getWorkspaceFromBytes``) WRITES
  the decompressed sample to a temp file to build the workspace. That persists a
  (disarmed but signature-intact) malware sample to disk, which (a) violates the
  ``no_persist_decompressed`` property and (b) trips resident AV. Therefore the
  capa runner REFUSES to run unless an explicit isolated ``work_dir`` is given,
  and even then it must be run only in a dedicated isolated environment WITHOUT
  resident AV (see ``docs/sorel20m_e2_protocol.md``). It is never used on cau.

Entropy is NOT a silver source (it is a selector feature) — no circularity.
Per-file records carry the SHA only in the isolated ledger; everything here is
structural (offsets, counts, rule names) and SHA-free.
"""

from __future__ import annotations

import contextlib
import os
import tempfile
from dataclasses import dataclass, field

from ua_sahi_mal.peatlas import CoordinateComponent, IntervalSet, PeAtlas, Provenance

# --------------------------------------------------------------------------
# little-endian header readers (bounds-checked)
# --------------------------------------------------------------------------


def _u16(data: bytes, off: int) -> int | None:
    return int.from_bytes(data[off:off + 2], "little") if off + 2 <= len(data) else None


def _u32(data: bytes, off: int) -> int | None:
    return int.from_bytes(data[off:off + 4], "little") if off + 4 <= len(data) else None


# --------------------------------------------------------------------------
# embedded-artifact silver (byte scope, overlay-safe)
# --------------------------------------------------------------------------

_OPTIONAL_MAGICS = (0x10B, 0x20B)  # PE32, PE32+
_MAX_SECTIONS = 96                 # Windows loader ceiling


def _embedded_pe_span(data: bytes, off: int, cap: int) -> int | None:
    """If a valid PE header begins at ``off``, return the header-region span
    (capped at ``cap`` and end-of-file); else ``None``. Only the exactly
    computable header region is claimed as silver."""
    n = len(data)
    if off + 0x40 > n or data[off:off + 2] != b"MZ":
        return None
    e_lfanew = _u32(data, off + 0x3C)
    if e_lfanew is None or e_lfanew <= 0 or off + e_lfanew + 24 > n:
        return None
    if data[off + e_lfanew:off + e_lfanew + 4] != b"PE\x00\x00":
        return None
    n_sections = _u16(data, off + e_lfanew + 6)
    size_opt = _u16(data, off + e_lfanew + 20)
    magic = _u16(data, off + e_lfanew + 24)
    if n_sections is None or size_opt is None or magic is None:
        return None
    if not (1 <= n_sections <= _MAX_SECTIONS) or magic not in _OPTIONAL_MAGICS:
        return None
    header_span = e_lfanew + 24 + size_opt + 40 * n_sections
    return max(1, min(header_span, cap, n - off))


def find_embedded_pes(data: bytes, *, header_span_cap: int = 65_536) -> list[tuple[int, int]]:
    """Deterministic scan for embedded PE images after offset 0."""
    out: list[tuple[int, int]] = []
    n = len(data)
    i = data.find(b"MZ", 1)  # offset 0 is the primary image, not "embedded"
    while i != -1 and i < n:
        span = _embedded_pe_span(data, i, header_span_cap)
        if span is not None:
            out.append((i, i + span))
            i = data.find(b"MZ", i + span)
        else:
            i = data.find(b"MZ", i + 2)
    return out


# --------------------------------------------------------------------------
# YARA silver (byte scope, in memory -- AV-safe, no disk, no disassembly)
# --------------------------------------------------------------------------


class YaraUnavailable(RuntimeError):
    """yara-python is not installed or rules failed to load/scan. The pipeline
    degrades and records the reason (never crashes)."""


def _default_yara_matcher(*, rules_path: str | None = None, compiled_rules=None):  # pragma: no cover - needs yara
    """Return a callable ``data -> [(offset, length, rule_name)]`` backed by
    yara-python, scanning the in-memory buffer only (no file is written)."""
    try:
        import yara
    except ImportError as exc:
        raise YaraUnavailable(f"yara-python not installed: {exc}") from exc
    rules = compiled_rules
    if rules is None:
        if not rules_path:
            raise YaraUnavailable("no YARA rules: pass --yara-rules <compiled .yac or rules dir/file>")
        try:
            if os.path.isdir(rules_path):
                filepaths = {}
                for root, _dirs, files in os.walk(rules_path):
                    for name in files:
                        if name.endswith((".yar", ".yara")):
                            full = os.path.join(root, name)
                            filepaths[os.path.relpath(full, rules_path)] = full
                rules = yara.compile(filepaths=filepaths)
            else:
                rules = yara.compile(filepath=rules_path)
        except Exception as exc:  # noqa: BLE001
            raise YaraUnavailable(f"YARA rule compile failed: {type(exc).__name__}: {exc}") from exc

    def match(data: bytes) -> list[tuple[int, int, str]]:
        out: list[tuple[int, int, str]] = []
        for m in rules.match(data=data):
            for s in getattr(m, "strings", []):
                instances = getattr(s, "instances", None)
                if instances is not None:  # yara-python >= 4.3
                    for inst in instances:
                        out.append((int(inst.offset), int(inst.matched_length), str(m.rule)))
                elif isinstance(s, tuple) and len(s) >= 3:  # older API: (offset, identifier, data)
                    out.append((int(s[0]), len(s[2]), str(m.rule)))
        return out

    return match


def yara_silver_intervals(
    data: bytes, *, rules_path: str | None = None, compiled_rules=None, matcher=None
) -> tuple[list[tuple[int, int]], dict[str, object]]:
    """In-memory YARA match spans as merged file-offset intervals.

    ``matcher`` (``data -> [(offset, length, rule)]``) is injectable for tests so
    the pure interval logic runs without yara-python installed.
    """
    if matcher is None:
        matcher = _default_yara_matcher(rules_path=rules_path, compiled_rules=compiled_rules)
    hits = matcher(data)
    intervals = IntervalSet.empty()
    rules: set[str] = set()
    n = len(data)
    for offset, length, rule in hits:
        if length > 0 and 0 <= offset and offset + length <= n:
            intervals = intervals.union(IntervalSet.single(offset, offset + length))
            rules.add(rule)
    return [(iv.start, iv.end) for iv in intervals], {"rules": sorted(rules), "n_strings": len(hits)}


# --------------------------------------------------------------------------
# capa silver (function scope) -- pure mapping + injectable runner
# --------------------------------------------------------------------------


class CapaUnavailable(RuntimeError):
    """capa/vivisect is unavailable, refused, or the run failed. The pipeline
    degrades to the other silver sources and records the reason."""


@dataclass(frozen=True)
class CapaMatch:
    """One capa capability match, resolved to its enclosing function's RVA extent."""

    rule: str
    fn_start_rva: int
    fn_end_rva: int  # half-open


def capa_matches_to_intervals(
    matches: list[CapaMatch], atlas: PeAtlas, *, version: str = ""
) -> tuple[IntervalSet, dict[str, object]]:
    """Map capa function-scope matches to canonical file offsets via PEAtlas
    (pure; guaranteed by the E1-verified coordinate mapping)."""
    rva_set = IntervalSet.empty()
    rules: set[str] = set()
    functions: set[tuple[int, int]] = set()
    for m in matches:
        rules.add(m.rule)
        if m.fn_end_rva > m.fn_start_rva:
            rva_set = rva_set.union(IntervalSet.single(m.fn_start_rva, m.fn_end_rva))
            functions.add((m.fn_start_rva, m.fn_end_rva))
    if rva_set.is_empty():
        return IntervalSet.empty(), {"rules": sorted(rules), "functions": 0, "mapped_bytes": 0}
    component = CoordinateComponent(
        identifier="capa", kind="function", rva_intervals=rva_set,
        provenance=Provenance("capa", version, {"rules": sorted(rules)}),
    )
    mapped = atlas.map_component(component)
    meta = {"rules": sorted(rules), "functions": len(functions), "mapped_bytes": mapped.file_offsets.total_length}
    return mapped.file_offsets, meta


@contextlib.contextmanager
def _temp_confined_to(work_dir: str):  # pragma: no cover - exercised only where capa runs (isolated VM)
    """Force Python/vivisect temp files into ``work_dir`` (an isolated path),
    never the user's AppData temp. Restores the previous state afterwards."""
    os.makedirs(work_dir, exist_ok=True)
    old_tempdir = tempfile.tempdir
    old_env = {k: os.environ.get(k) for k in ("TMP", "TEMP", "TMPDIR")}
    tempfile.tempdir = work_dir
    for k in ("TMP", "TEMP", "TMPDIR"):
        os.environ[k] = work_dir
    try:
        yield
    finally:
        tempfile.tempdir = old_tempdir
        for k, v in old_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _default_capa_runner(
    data: bytes, *, timeout: int, image_base: int, rules_path: str | None = None, work_dir: str | None = None
) -> list[CapaMatch]:
    """capa run via the vivisect backend.

    SAFETY: this WRITES the decompressed sample to a temp file (viv_utils builds
    the workspace from a file). It therefore REFUSES unless an isolated
    ``work_dir`` is supplied, and confines the temp write to it. Run only in a
    dedicated isolated environment without resident AV — never on cau.

    Version-sensitive; validated in the isolated env where capa is installed. Any
    failure raises :class:`CapaUnavailable` so the pipeline degrades.
    """
    if not work_dir:
        raise CapaUnavailable(
            "refused: capa's vivisect backend writes the decompressed sample to disk; "
            "pass an isolated work_dir and run only in an AV-free isolated environment"
        )
    try:  # pragma: no cover - exercised only where capa is installed (isolated VM)
        import capa.capabilities.common as capa_caps
        import capa.rules
        import viv_utils
        from capa.features.address import AbsoluteVirtualAddress
        from capa.features.common import OS_WINDOWS
        from capa.features.extractors.viv.extractor import VivisectFeatureExtractor
    except ImportError as exc:  # pragma: no cover
        raise CapaUnavailable(f"capa/vivisect not installed: {exc}") from exc

    try:  # pragma: no cover - isolated-env-only path
        with _temp_confined_to(work_dir):
            workspace = viv_utils.getWorkspaceFromBytes(data, analyze=True)
        extractor = VivisectFeatureExtractor(workspace, path="", os_=OS_WINDOWS)
        if not rules_path:
            raise CapaUnavailable("no capa rules: pass --capa-rules <rules dir>")
        rules = capa.rules.get_rules([rules_path])
        capabilities = capa_caps.find_capabilities(rules, extractor, disable_progress=True)
        matches_map = _capabilities_matches(capabilities)

        out: list[CapaMatch] = []
        for rule_name, addresses in matches_map.items():
            for addr in addresses:
                if not isinstance(addr, AbsoluteVirtualAddress):
                    continue
                va = int(addr)
                fva = workspace.getFunction(va)
                if fva is None:
                    continue
                size = workspace.getFunctionMeta(fva, "Size") or 0
                start_rva = fva - image_base
                if start_rva < 0 or size <= 0:
                    continue
                out.append(CapaMatch(rule=rule_name, fn_start_rva=start_rva, fn_end_rva=start_rva + int(size)))
        return out
    except CapaUnavailable:
        raise
    except Exception as exc:  # pragma: no cover - isolated-env-only path  # noqa: BLE001
        raise CapaUnavailable(f"capa run failed: {type(exc).__name__}: {exc}") from exc


def _capabilities_matches(capabilities: object) -> dict[str, list[object]]:  # pragma: no cover - isolated-env-only
    """Extract ``{rule_name: [addresses]}`` across capa result-object shapes."""
    matches = getattr(capabilities, "matches", None)
    if matches is None and isinstance(capabilities, tuple) and capabilities:
        matches = getattr(capabilities[0], "matches", None)
    if matches is None:
        return {}
    out: dict[str, list[object]] = {}
    for rule_name, results in dict(matches).items():
        addresses = [addr for addr, _ in results]
        if addresses:
            out[str(rule_name)] = addresses
    return out


# --------------------------------------------------------------------------
# combined silver
# --------------------------------------------------------------------------


@dataclass
class SilverResult:
    """SHA-free per-file silver map."""

    embedded_intervals: list[tuple[int, int]] = field(default_factory=list)
    yara_intervals: list[tuple[int, int]] = field(default_factory=list)
    capa_intervals: list[tuple[int, int]] = field(default_factory=list)
    union_intervals: list[tuple[int, int]] = field(default_factory=list)
    yara_status: str = "disabled"          # disabled | ok | unavailable:<reason>
    capa_status: str = "disabled"          # disabled | ok | unavailable:<reason>
    yara_meta: dict[str, object] = field(default_factory=dict)
    capa_meta: dict[str, object] = field(default_factory=dict)
    embedded_count: int = 0

    @property
    def silver_bytes(self) -> int:
        return sum(e - s for s, e in self.union_intervals)

    @property
    def has_silver(self) -> bool:
        return bool(self.union_intervals)


def build_silver(
    data: bytes,
    atlas: PeAtlas,
    *,
    image_base: int,
    enable_capa: bool = False,
    enable_yara: bool = False,
    capa_timeout: int = 300,
    capa_work_dir: str | None = None,
    header_span_cap: int = 65_536,
    capa_version: str = "",
    capa_runner=None,
    yara_rules_path: str | None = None,
    yara_matcher=None,
    yara_compiled=None,
) -> SilverResult:
    """Union embedded-artifact, YARA, and (optionally) capa silver into one map."""
    embedded = find_embedded_pes(data, header_span_cap=header_span_cap)
    result = SilverResult(embedded_intervals=embedded, embedded_count=len(embedded))

    if enable_yara:
        try:
            yara_ivs, ymeta = yara_silver_intervals(
                data, rules_path=yara_rules_path, compiled_rules=yara_compiled, matcher=yara_matcher
            )
            result.yara_intervals = yara_ivs
            result.yara_status = "ok"
            result.yara_meta = ymeta
        except YaraUnavailable as exc:
            result.yara_status = f"unavailable:{exc}"

    if enable_capa:
        runner = capa_runner or _default_capa_runner
        try:
            matches = runner(data, timeout=capa_timeout, image_base=image_base, work_dir=capa_work_dir)
            capa_set, meta = capa_matches_to_intervals(matches, atlas, version=capa_version)
            result.capa_intervals = [(iv.start, iv.end) for iv in capa_set]
            result.capa_status = "ok"
            result.capa_meta = meta
        except CapaUnavailable as exc:
            result.capa_status = f"unavailable:{exc}"

    union = IntervalSet.empty()
    for start, end in [*embedded, *result.yara_intervals, *result.capa_intervals]:
        union = union.union(IntervalSet.single(start, end))
    result.union_intervals = [(iv.start, iv.end) for iv in union]
    return result
