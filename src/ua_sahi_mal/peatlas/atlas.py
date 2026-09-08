"""PEAtlas: authoritative coordinate mapping for static Windows PE files.

Scope of this module (Tier 0 / P1 first slice):

- parse the on-disk PE layout (DOS/COFF/optional headers, section table,
  certificate directory, overlay) without executing or disassembling anything;
- convert between **file offset**, **RVA** (relative virtual address) and **VA**
  (virtual address = image base + RVA), per section;
- return an **explicit failure status** for coordinates that have no honest
  mapping (virtual-only bytes, alignment padding, overlay, certificate,
  truncated, unmapped, ambiguous/overlapping sections) instead of fabricating an
  offset;
- map a half-open coordinate *interval* across section boundaries, splitting it
  into homogeneous segments (this is the boundary-crossing behaviour the plan's
  Tier 0 requires);
- expose a stable interface for attaching analyzer function/basic-block results
  (RVA ranges + provenance) and mapping them into the canonical file-offset
  interval union.

Explicitly OUT of scope here (left for the next task, and noted in
``docs/PEATLAS_CONTRACT.md``):

- pixel <-> byte projection (already implemented in ``ua_sahi_mal.encoding``;
  PEAtlas will delegate to it, not re-implement it);
- running a real disassembler / analyzer (Binary Ninja, capa, DeepReflect);
- any training or Tier 1 synthetic *data generator*.

The canonical coordinate is the original file's half-open interval union; every
other view is a projection of it.
"""

from __future__ import annotations

import struct
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import Enum

from .intervals import Interval, IntervalSet


class PeFormatError(ValueError):
    """Raised when the header region cannot be parsed as a PE at all.

    Body-level problems (a section whose raw data runs past end-of-file,
    overlapping sections) are NOT format errors: they are recorded on the layout
    and surface as per-coordinate failure states, because a real corrupted
    sample must still be describable rather than crash the pipeline.
    """


class MapStatus(str, Enum):
    """Outcome of a mapping. ``OK`` and ``HEADERS`` carry valid values."""

    OK = "ok"
    HEADERS = "headers"          # inside the header region (mapped 1:1)
    VIRTUAL_ONLY = "virtual_only"  # RVA backed by no on-disk bytes (e.g. .bss tail)
    PADDING = "padding"         # file-alignment padding / inter-region gap, not loaded
    OVERLAY = "overlay"         # bytes after the mapped image; no RVA
    CERTIFICATE = "certificate"  # attribute certificate table; file offset, no RVA
    TRUNCATED = "truncated"     # claimed by the layout but past actual end-of-file
    UNMAPPED = "unmapped"       # outside every known region
    OVERLAPPING = "overlapping"  # >1 section claims this coordinate; ambiguous

    @property
    def is_ok(self) -> bool:
        return self is MapStatus.OK or self is MapStatus.HEADERS


@dataclass(frozen=True)
class MapResult:
    """A point mapping result: ``value`` is set only when ``status.is_ok``."""

    status: MapStatus
    value: int | None = None
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.status.is_ok and self.value is not None


@dataclass(frozen=True)
class Section:
    """One PE section header, as parsed (all sizes/offsets are raw fields)."""

    index: int
    name: str
    rva: int              # VirtualAddress
    virtual_size: int     # VirtualSize
    raw_offset: int       # PointerToRawData
    raw_size: int         # SizeOfRawData
    characteristics: int

    @property
    def has_raw(self) -> bool:
        return self.raw_size > 0 and self.raw_offset > 0

    @property
    def mapped_raw_size(self) -> int:
        """Bytes that exist both on disk and in the virtual image."""
        return max(0, min(self.raw_size, self.virtual_size)) if self.has_raw else 0


@dataclass(frozen=True)
class Provenance:
    """Where a mapped component's coordinates came from.

    ``source`` mirrors the DATA_CONTRACT annotation sources / the DeepReflect
    adapter schema (e.g. ``binaryninja``, ``capa``, ``deepreflect``, ``synthetic``,
    ``human_verified``). ``extra`` carries source-specific fields (threshold,
    score, environment revision, ...) without this module needing to know them.
    """

    source: str
    version: str = ""
    extra: dict = field(default_factory=dict)


@dataclass(frozen=True)
class CoordinateComponent:
    """An analyzer result expressed in RVA space, before mapping to file offsets.

    This is the stable hand-off point for function / basic-block results from
    external analyzers; ``kind`` is free-form ("function", "basic_block", ...).
    """

    identifier: str
    kind: str
    rva_intervals: IntervalSet
    provenance: Provenance


@dataclass(frozen=True)
class Segment:
    """A homogeneous slice of an interval mapping."""

    source: Interval          # the sub-interval in the input coordinate space
    status: MapStatus
    mapped: Interval | None   # the mapped sub-interval, when status.is_ok


@dataclass(frozen=True)
class MappedComponent:
    """Result of mapping an RVA component to canonical file-offset space."""

    identifier: str
    kind: str
    file_offsets: IntervalSet          # union of OK offset segments (canonical)
    segments: tuple[Segment, ...]      # every segment incl. failures, in order
    provenance: Provenance

    @property
    def fully_mapped(self) -> bool:
        return bool(self.segments) and all(s.status.is_ok for s in self.segments)

    @property
    def unmapped_length(self) -> int:
        return sum(s.source.length for s in self.segments if not s.status.is_ok)


@dataclass(frozen=True)
class PeLayout:
    """Parsed, immutable description of a PE file's on-disk layout."""

    file_size: int
    is_pe32_plus: bool
    image_base: int
    section_alignment: int
    file_alignment: int
    size_of_headers: int
    sections: tuple[Section, ...]
    overlay_offset: int              # first byte after the last raw section
    certificate: Interval | None     # attribute cert table (file-offset range)
    warnings: tuple[str, ...] = ()


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------
_PE32_MAGIC = 0x10B
_PE32PLUS_MAGIC = 0x20B
_WINDOWS_SECTION_LIMIT = 96


def parse_pe(data: bytes) -> PeLayout:
    """Parse ``data`` into a :class:`PeLayout`.

    Raises :class:`PeFormatError` only when the *headers* cannot be read.
    Body-level anomalies are recorded in ``warnings`` and handled by the mapping
    methods as explicit statuses.
    """
    n = len(data)
    if n < 0x40:
        raise PeFormatError("file too small for a DOS header")
    if data[0:2] != b"MZ":
        raise PeFormatError("missing 'MZ' DOS signature")
    e_lfanew = _u32(data, 0x3C)
    if e_lfanew + 24 > n:
        raise PeFormatError("PE header offset (e_lfanew) points past end of file")
    if data[e_lfanew:e_lfanew + 4] != b"PE\x00\x00":
        raise PeFormatError("missing 'PE\\0\\0' signature")

    coff = e_lfanew + 4
    num_sections = _u16(data, coff + 2)
    if num_sections > _WINDOWS_SECTION_LIMIT:
        raise PeFormatError(
            f"section count {num_sections} exceeds the Windows loader limit {_WINDOWS_SECTION_LIMIT}"
        )
    size_opt = _u16(data, coff + 16)
    opt = coff + 20
    opt_end = opt + size_opt
    if size_opt < 2 or opt_end > n:
        raise PeFormatError("declared optional header missing or truncated")
    if opt + 2 > n:
        raise PeFormatError("optional header magic missing")
    magic = _u16(data, opt)
    if magic == _PE32_MAGIC:
        is_plus = False
        num_dirs_off = opt + 92
        dirs_off = opt + 96
    elif magic == _PE32PLUS_MAGIC:
        is_plus = True
        num_dirs_off = opt + 108
        dirs_off = opt + 112
    else:
        raise PeFormatError(f"unknown optional header magic 0x{magic:x}")

    if dirs_off > opt_end:
        raise PeFormatError("optional header too small for fixed fields")
    image_base = _u64(data, opt + 24) if is_plus else _u32(data, opt + 28)
    section_alignment = _u32(data, opt + 32)
    file_alignment = _u32(data, opt + 36)
    size_of_headers = _u32(data, opt + 60)

    warnings: list[str] = []

    certificate: Interval | None = None
    num_dirs = _u32(data, num_dirs_off)
    if dirs_off + num_dirs * 8 > opt_end:
        raise PeFormatError("data directories exceed declared optional header")
    if num_dirs > 4:
        # Attribute certificate table is data directory index 4; its
        # "VirtualAddress" field is a FILE OFFSET, not an RVA.
        cert_off = _u32(data, dirs_off + 4 * 8)
        cert_size = _u32(data, dirs_off + 4 * 8 + 4)
        if cert_off > 0 and cert_size > 0:
            certificate = Interval(cert_off, cert_off + cert_size)

    # Section table
    sec_table = opt + size_opt
    if sec_table + num_sections * 40 > n:
        raise PeFormatError("section table truncated")
    sections: list[Section] = []
    for i in range(num_sections):
        base = sec_table + i * 40
        raw_name = data[base:base + 8]
        name = raw_name.split(b"\x00", 1)[0].decode("latin-1", "replace")
        virtual_size = _u32(data, base + 8)
        rva = _u32(data, base + 12)
        raw_size = _u32(data, base + 16)
        raw_offset = _u32(data, base + 20)
        characteristics = _u32(data, base + 36)
        sec = Section(
            index=i, name=name, rva=rva, virtual_size=virtual_size,
            raw_offset=raw_offset, raw_size=raw_size, characteristics=characteristics,
        )
        sections.append(sec)
        if sec.has_raw and sec.raw_offset + sec.raw_size > n:
            warnings.append(
                f"section {i} ({name!r}) raw data [{sec.raw_offset}, "
                f"{sec.raw_offset + sec.raw_size}) runs past end-of-file {n} (truncated)"
            )

    _detect_overlaps(sections, warnings)

    # Overlay = first byte after the highest raw section end (clamped to file size).
    raw_end = size_of_headers
    for sec in sections:
        if sec.has_raw:
            raw_end = max(raw_end, min(sec.raw_offset + sec.raw_size, n))
    overlay_offset = min(raw_end, n)

    return PeLayout(
        file_size=n,
        is_pe32_plus=is_plus,
        image_base=image_base,
        section_alignment=section_alignment,
        file_alignment=file_alignment,
        size_of_headers=size_of_headers,
        sections=tuple(sections),
        overlay_offset=overlay_offset,
        certificate=certificate,
        warnings=tuple(warnings),
    )


def _detect_overlaps(sections: list[Section], warnings: list[str]) -> None:
    for a in range(len(sections)):
        for b in range(a + 1, len(sections)):
            sa, sb = sections[a], sections[b]
            if sa.has_raw and sb.has_raw:
                if sa.raw_offset < sb.raw_offset + sb.raw_size and sb.raw_offset < sa.raw_offset + sa.raw_size:
                    warnings.append(f"sections {sa.index} and {sb.index} overlap in raw space")
            if sa.virtual_size and sb.virtual_size:
                if sa.rva < sb.rva + sb.virtual_size and sb.rva < sa.rva + sa.virtual_size:
                    warnings.append(f"sections {sa.index} and {sb.index} overlap in virtual space")


# --------------------------------------------------------------------------
# Atlas
# --------------------------------------------------------------------------
class PeAtlas:
    """Coordinate authority built from a :class:`PeLayout`."""

    def __init__(self, layout: PeLayout) -> None:
        self.layout = layout

    @classmethod
    def from_bytes(cls, data: bytes) -> PeAtlas:
        return cls(parse_pe(data))

    # -- point: offset -> rva/va -----------------------------------------
    def offset_to_rva(self, offset: int) -> MapResult:
        _require_integer(offset)
        result = self._offset_candidate(offset)
        if result.ok:
            back = self._rva_candidate(result.value)
            if not back.ok or back.value != offset:
                return MapResult(MapStatus.OVERLAPPING, detail="target RVA has conflicting ownership")
        return result

    def _offset_candidate(self, offset: int) -> MapResult:
        lay = self.layout
        if offset < 0:
            raise ValueError("offset must be non-negative")

        owners = [s for s in lay.sections if s.has_raw and s.raw_offset <= offset < s.raw_offset + s.raw_size]
        header = offset < lay.size_of_headers
        certificate = lay.certificate is not None and lay.certificate.contains(offset)
        if len(owners) + int(header) + int(certificate) > 1:
            return MapResult(MapStatus.OVERLAPPING, detail="multiple regions claim this offset")
        if header:
            if offset >= lay.file_size:
                return MapResult(MapStatus.TRUNCATED, detail="header offset past end-of-file")
            return MapResult(MapStatus.HEADERS, offset, "header region maps 1:1 to rva")

        if owners:
            sec = owners[0]
            delta = offset - sec.raw_offset
            if offset >= lay.file_size:
                return MapResult(MapStatus.TRUNCATED, detail=f"section {sec.index} raw data past end-of-file")
            if delta < sec.mapped_raw_size:
                return MapResult(MapStatus.OK, sec.rva + delta, f"section {sec.index} ({sec.name})")
            # raw_size > virtual_size: this tail is file-alignment padding, not loaded.
            return MapResult(MapStatus.PADDING, detail=f"section {sec.index} raw padding beyond virtual size")

        if certificate:
            if offset >= lay.file_size:
                return MapResult(MapStatus.TRUNCATED, detail="certificate offset past end-of-file")
            return MapResult(MapStatus.CERTIFICATE, detail="attribute certificate table")
        if offset >= lay.overlay_offset:
            if offset >= lay.file_size:
                return MapResult(MapStatus.UNMAPPED, detail="offset past end-of-file")
            return MapResult(MapStatus.OVERLAY, detail="overlay bytes after mapped image")
        # Between header end and a section, or an inter-section gap.
        return MapResult(MapStatus.PADDING, detail="inter-region alignment padding")

    def offset_to_va(self, offset: int) -> MapResult:
        r = self.offset_to_rva(offset)
        if r.ok:
            return MapResult(r.status, self.layout.image_base + r.value, r.detail)
        return r

    # -- point: rva/va -> offset -----------------------------------------
    def rva_to_offset(self, rva: int) -> MapResult:
        _require_integer(rva)
        result = self._rva_candidate(rva)
        if result.ok:
            back = self._offset_candidate(result.value)
            if not back.ok or back.value != rva:
                return MapResult(MapStatus.OVERLAPPING, detail="target offset has conflicting ownership")
        return result

    def _rva_candidate(self, rva: int) -> MapResult:
        lay = self.layout
        if rva < 0:
            raise ValueError("rva must be non-negative")

        owners = [s for s in lay.sections if s.virtual_size and s.rva <= rva < s.rva + s.virtual_size]
        if len(owners) + int(rva < lay.size_of_headers) > 1:
            return MapResult(MapStatus.OVERLAPPING, detail="multiple regions claim this rva")
        if owners:
            sec = owners[0]
            delta = rva - sec.rva
            if delta < sec.mapped_raw_size:
                offset = sec.raw_offset + delta
                if offset >= lay.file_size:
                    return MapResult(MapStatus.TRUNCATED, detail=f"section {sec.index} raw data past end-of-file")
                return MapResult(MapStatus.OK, offset, f"section {sec.index} ({sec.name})")
            return MapResult(MapStatus.VIRTUAL_ONLY, detail=f"section {sec.index} virtual bytes not backed on disk")

        if rva < lay.size_of_headers:
            if rva >= lay.file_size:
                return MapResult(MapStatus.TRUNCATED, detail="header rva past end-of-file")
            return MapResult(MapStatus.HEADERS, rva, "header region maps 1:1 to offset")
        return MapResult(MapStatus.UNMAPPED, detail="rva outside every section")

    def va_to_offset(self, va: int) -> MapResult:
        _require_integer(va)
        if va < self.layout.image_base:
            return MapResult(MapStatus.UNMAPPED, detail="va below image base")
        return self.rva_to_offset(va - self.layout.image_base)

    # -- classification ---------------------------------------------------
    def classify_offset(self, offset: int) -> MapStatus:
        return self.offset_to_rva(offset).status

    # -- interval mapping (splits at section boundaries) -----------------
    def map_rva_interval(self, start: int, end: int) -> tuple[IntervalSet, tuple[Segment, ...]]:
        """Map a half-open RVA interval to file offsets, split at boundaries.

        Returns the canonical file-offset :class:`IntervalSet` (OK parts only)
        and the ordered per-segment breakdown including every failure segment.
        """
        return self._map_interval(start, end, self.rva_to_offset, self._rva_boundaries)

    def map_offset_interval(self, start: int, end: int) -> tuple[IntervalSet, tuple[Segment, ...]]:
        """Map a half-open file-offset interval to RVAs, split at boundaries."""
        return self._map_interval(start, end, self.offset_to_rva, self._offset_boundaries)

    def _map_interval(self, start, end, point_map, boundary_fn):  # type: ignore[no-untyped-def]
        _require_integer(start)
        _require_integer(end)
        if end <= start:
            raise ValueError("interval must be non-empty half-open [start, end)")
        cuts = sorted({start, end, *(b for b in boundary_fn() if start < b < end)})
        segments: list[Segment] = []
        ok_offsets: list[Interval] = []
        for lo, hi in zip(cuts, cuts[1:], strict=False):
            res = point_map(lo)
            src = Interval(lo, hi)
            if res.ok:
                mapped = Interval(res.value, res.value + (hi - lo))
                segments.append(Segment(src, res.status, mapped))
                ok_offsets.append(mapped)
            else:
                segments.append(Segment(src, res.status, None))
        return IntervalSet(ok_offsets), tuple(segments)

    def _rva_region_boundaries(self) -> Iterable[int]:
        lay = self.layout
        yield 0
        yield lay.size_of_headers
        yield lay.file_size  # headers may claim bytes past EOF
        for s in lay.sections:
            if s.virtual_size:
                yield s.rva
                yield s.rva + s.mapped_raw_size   # raw/virtual transition
                yield s.rva + s.virtual_size

    def _offset_region_boundaries(self) -> Iterable[int]:
        lay = self.layout
        yield 0
        yield lay.size_of_headers
        yield lay.overlay_offset
        yield lay.file_size
        if lay.certificate is not None:
            yield lay.certificate.start
            yield lay.certificate.end
        for s in lay.sections:
            if s.has_raw:
                yield s.raw_offset
                yield s.raw_offset + s.mapped_raw_size
                yield s.raw_offset + s.raw_size

    def _rva_boundaries(self) -> Iterable[int]:
        yield from self._rva_region_boundaries()
        # A target-space conflict or EOF can start inside a source section.
        for boundary in self._offset_region_boundaries():
            if 0 <= boundary <= self.layout.size_of_headers:
                yield boundary
            for section in self.layout.sections:
                delta = boundary - section.raw_offset
                if 0 <= delta <= section.mapped_raw_size:
                    yield section.rva + delta

    def _offset_boundaries(self) -> Iterable[int]:
        yield from self._offset_region_boundaries()
        for boundary in self._rva_region_boundaries():
            if 0 <= boundary <= self.layout.size_of_headers:
                yield boundary
            for section in self.layout.sections:
                delta = boundary - section.rva
                if 0 <= delta <= section.mapped_raw_size:
                    yield section.raw_offset + delta

    # -- analyzer component interface ------------------------------------
    def map_component(self, component: CoordinateComponent) -> MappedComponent:
        """Map an analyzer's RVA-space component into canonical file offsets.

        This is the connection point for function/basic-block results from an
        external analyzer (Binary Ninja / capa / DeepReflect). The analyzer's
        maliciousness label is *not* handled here; only coordinates and
        provenance are, per the plan's separation of location from label.
        """
        offsets = IntervalSet.empty()
        all_segments: list[Segment] = []
        for iv in component.rva_intervals:
            os_set, segs = self.map_rva_interval(iv.start, iv.end)
            offsets = offsets.union(os_set)
            all_segments.extend(segs)
        return MappedComponent(
            identifier=component.identifier,
            kind=component.kind,
            file_offsets=offsets,
            segments=tuple(all_segments),
            provenance=component.provenance,
        )


# --------------------------------------------------------------------------
# little-endian readers
# --------------------------------------------------------------------------
def _require_integer(value: int) -> None:
    if type(value) is not int:
        raise TypeError("coordinate must be int")


def _u16(data: bytes, off: int) -> int:
    return struct.unpack_from("<H", data, off)[0]


def _u32(data: bytes, off: int) -> int:
    return struct.unpack_from("<I", data, off)[0]


def _u64(data: bytes, off: int) -> int:
    return struct.unpack_from("<Q", data, off)[0]
