"""E2 silver-evidence extraction (frozen: ``E2_prereg_v1``).

Silver evidence is the weak, tool-attributed localization target E2 measures
selectors against (gold DeepReflect/Binary Ninja labels are excluded in v3).
Two sources, unioned per file:

* ``embedded_artifact`` (byte scope): embedded PE images found by scanning the
  raw bytes. Works inside the RVA-less overlay that dominates ~40% of the
  cohort (E1), where function-scope analysis sees nothing. Pure; no execution.
* ``capa`` (function scope): capability rule matches -> the enclosing function's
  RVA extent -> file offsets via the E1-verified :meth:`PeAtlas.map_component`.
  The capa run itself (static disassembly + vivisect abstract emulation, no OS
  execution) is the only version-sensitive part and is isolated in
  :func:`_default_capa_runner`; the RVA->offset mapping reuses PEAtlas.

Entropy is deliberately NOT a silver source (it is a *selector* feature) to keep
the retrieval comparison free of circularity.

Per-file records carry the SHA only in the isolated ledger; everything here is
structural (offsets, counts, rule names) and SHA-free.
"""

from __future__ import annotations

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
    (capped at ``cap`` and end-of-file); else ``None``.

    Only the header region is claimed as the silver interval: it is exactly
    computable, whereas the embedded body has no reliable end marker.
    """
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
    """Deterministic scan for embedded PE images after offset 0.

    Returns ``[start, end)`` header-region intervals, sorted, non-overlapping by
    construction (the scan advances past each accepted header).
    """
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
# capa silver (function scope) -- pure mapping + injectable runner
# --------------------------------------------------------------------------


class CapaUnavailable(RuntimeError):
    """capa/vivisect is not installed or the run failed. The pipeline degrades to
    embedded-artifact silver and records the reason (never crashes)."""


@dataclass(frozen=True)
class CapaMatch:
    """One capa capability match, resolved to its enclosing function's RVA extent."""

    rule: str
    fn_start_rva: int
    fn_end_rva: int  # half-open


def capa_matches_to_intervals(
    matches: list[CapaMatch], atlas: PeAtlas, *, version: str = ""
) -> tuple[IntervalSet, dict[str, object]]:
    """Map capa function-scope matches to canonical file offsets via PEAtlas.

    Pure and deterministic given ``matches`` + ``atlas``; this is the E2 unit
    that the E1-verified coordinate mapping guarantees.
    """
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
        identifier="capa",
        kind="function",
        rva_intervals=rva_set,
        provenance=Provenance("capa", version, {"rules": sorted(rules)}),
    )
    mapped = atlas.map_component(component)
    meta = {
        "rules": sorted(rules),
        "functions": len(functions),
        "mapped_bytes": mapped.file_offsets.total_length,
    }
    return mapped.file_offsets, meta


def _default_capa_runner(
    data: bytes, *, timeout: int, image_base: int, rules_path: str | None = None
) -> list[CapaMatch]:
    """Best-effort in-memory capa run (static disassembly + vivisect abstract
    emulation; the sample is never written to disk).

    Version-sensitive; validated on the cau venv where capa is installed. Any
    failure raises :class:`CapaUnavailable` so the pipeline falls back to
    embedded-artifact silver rather than crashing. ``timeout`` is enforced by the
    caller (per-file worker), not here.
    """
    try:  # pragma: no cover - exercised only where capa is installed (cau)
        import capa.capabilities.common as capa_caps
        import capa.rules
        import viv_utils
        from capa.features.address import AbsoluteVirtualAddress
        from capa.features.common import OS_WINDOWS
        from capa.features.extractors.viv.extractor import VivisectFeatureExtractor
    except ImportError as exc:  # pragma: no cover
        raise CapaUnavailable(f"capa/vivisect not installed: {exc}") from exc

    try:  # pragma: no cover - cau-only path
        workspace = viv_utils.getWorkspaceFromBytes(data, analyze=True)
        extractor = VivisectFeatureExtractor(workspace, path="", os_=OS_WINDOWS)
        if rules_path:
            rules = capa.rules.get_rules([rules_path])
        else:
            from capa.rules import RuleSet

            rules = RuleSet([])  # replaced on cau by the configured rules directory
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
    except Exception as exc:  # pragma: no cover - cau-only path  # noqa: BLE001
        raise CapaUnavailable(f"capa run failed: {type(exc).__name__}: {exc}") from exc


def _capabilities_matches(capabilities: object) -> dict[str, list[object]]:  # pragma: no cover - cau-only
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
    capa_intervals: list[tuple[int, int]] = field(default_factory=list)
    union_intervals: list[tuple[int, int]] = field(default_factory=list)
    capa_status: str = "disabled"          # disabled | ok | unavailable:<reason>
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
    enable_capa: bool,
    capa_timeout: int = 300,
    header_span_cap: int = 65_536,
    capa_version: str = "",
    capa_runner=None,
) -> SilverResult:
    """Union embedded-artifact and (optionally) capa silver into one map."""
    embedded = find_embedded_pes(data, header_span_cap=header_span_cap)
    result = SilverResult(embedded_intervals=embedded, embedded_count=len(embedded))

    if enable_capa:
        runner = capa_runner or _default_capa_runner
        try:
            matches = runner(data, timeout=capa_timeout, image_base=image_base)
            capa_set, meta = capa_matches_to_intervals(matches, atlas, version=capa_version)
            result.capa_intervals = [(iv.start, iv.end) for iv in capa_set]
            result.capa_status = "ok"
            result.capa_meta = meta
        except CapaUnavailable as exc:
            result.capa_status = f"unavailable:{exc}"

    union = IntervalSet.empty()
    for start, end in [*embedded, *result.capa_intervals]:
        union = union.union(IntervalSet.single(start, end))
    result.union_intervals = [(iv.start, iv.end) for iv in union]
    return result
