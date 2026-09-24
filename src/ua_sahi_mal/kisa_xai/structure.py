"""Static PE structure partition and independent pefile field comparison.

Draft mapping rules (not a scientific pass-rate threshold): PeAtlas decides coordinate
ownership; padding, ambiguous and unbacked coordinates are unknown. Executable flags
take precedence over resource-directory membership. A non-executable section owning
resource directory bytes is resource-like, independent of its name. Certificates are
file-offset ranges, excluded from overlay by PeAtlas ownership. No payload is executed.
"""

from __future__ import annotations

import struct
from dataclasses import asdict, dataclass

import numpy as np

from ..peatlas.atlas import MapStatus, PeAtlas, PeFormatError
from .representation import IntervalBinnedMap

REGIONS = (
    "dos_and_pe_headers", "executable_sections", "non_executable_sections",
    "resource_like_sections", "certificate_table", "overlay", "unknown",
)
STRUCTURE_VERSION = "psa-structure-draft-v1"
UNKNOWN_FALLBACK_POLICY = "conservative_unknown_v1"
P2_SECTION_DISAGREEMENT_POLICY = "P2-SECTION-DISAGREEMENT-V1"
P2_SECTION_DISAGREEMENT_FIELDS = {"section_count", "raw_section_overlay_boundary"}
P2_MALFORMED_HEADER_REASONS = {
    "data directories exceed declared optional header": "directory_count_exceeds_optional_header_capacity",
    "declared optional header missing or truncated": "declared_optional_header_missing_or_truncated",
    "optional header too small for fixed fields": "declared_optional_header_missing_or_truncated",
}
EXECUTE = 0x20000000


@dataclass(frozen=True)
class RegionSpan:
    start: int
    end: int
    region: str


@dataclass(frozen=True)
class StructureMap:
    file_size: int
    spans: tuple[RegionSpan, ...]
    warnings: tuple[str, ...]

    def validate(self):
        cursor = 0
        for span in self.spans:
            if span.start != cursor or span.end <= span.start or span.region not in REGIONS:
                raise ValueError("invalid structure partition")
            cursor = span.end
        if cursor != self.file_size or self.file_size <= 0:
            raise ValueError("structure map does not cover file")

    def to_dict(self):
        return {"version": STRUCTURE_VERSION, "file_size": self.file_size,
                "spans": [asdict(s) for s in self.spans], "warnings": list(self.warnings),
                "region_bytes": {r: sum(s.end - s.start for s in self.spans if s.region == r) for r in REGIONS}}


def data_directory(data: bytes, index: int):
    """Read raw directory fields after PeAtlas has validated fixed headers."""
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    opt = pe + 24
    plus = struct.unpack_from("<H", data, opt)[0] == 0x20B
    count_offset, start = (108, 112) if plus else (92, 96)
    count = struct.unpack_from("<I", data, opt + count_offset)[0]
    if count <= index:
        return (0, 0)
    return struct.unpack_from("<II", data, opt + start + 8 * index)


def build_structure_map(data: bytes) -> StructureMap:
    atlas = PeAtlas.from_bytes(data)
    layout = atlas.layout
    resource_rva, resource_size = data_directory(data, 2)
    warnings = list(layout.warnings)
    resource_sections = set()
    if resource_rva and resource_size:
        _, segments = atlas.map_rva_interval(resource_rva, resource_rva + resource_size)
        if not all(s.status == MapStatus.OK for s in segments):
            warnings.append("resource_directory_not_fully_section_backed")
        for section in layout.sections:
            if (section.mapped_raw_size > 0 and section.rva < resource_rva + resource_size
                    and resource_rva < section.rva + section.mapped_raw_size):
                resource_sections.add(section.index)
    spans = []
    _, segments = atlas.map_offset_interval(0, len(data))
    for segment in segments:
        start, end = segment.source.start, segment.source.end
        status = segment.status
        region = "unknown"
        if status == MapStatus.HEADERS:
            region = "dos_and_pe_headers"
        elif status == MapStatus.CERTIFICATE:
            region = "certificate_table"
        elif status == MapStatus.OVERLAY:
            region = "overlay"
        elif status == MapStatus.OK:
            owners = [s for s in layout.sections
                      if s.has_raw and s.raw_offset <= start < s.raw_offset + s.mapped_raw_size]
            if len(owners) != 1:
                raise ValueError("PeAtlas OK segment lacks unique owner")
            owner = owners[0]
            region = ("executable_sections" if owner.characteristics & EXECUTE else
                      "resource_like_sections" if owner.index in resource_sections else "non_executable_sections")
        if spans and spans[-1].region == region and spans[-1].end == start:
            spans[-1] = RegionSpan(spans[-1].start, end, region)
        else:
            spans.append(RegionSpan(start, end, region))
    result = StructureMap(len(data), tuple(spans), tuple(warnings))
    result.validate()
    return result


def build_unknown_structure_map(data: bytes, reason: str) -> StructureMap:
    """Conservative PSA fallback for pre-declared malformed structure cases.

    This is deliberately outside PeAtlas parsing: it preserves the sample in the
    experiment while refusing to fabricate header/section/overlay labels when the
    independent P2 adjudication says those labels are not trustworthy.
    """
    if not data:
        raise ValueError("cannot build a structure map for an empty file")
    result = StructureMap(
        len(data),
        (RegionSpan(0, len(data), "unknown"),),
        (f"{UNKNOWN_FALLBACK_POLICY}:{reason}",),
    )
    result.validate()
    return result


def p2_malformed_header_reason(error: Exception) -> str | None:
    """Classify only the PeAtlas failures covered by P2-MALFORMED-HEADER-V1."""
    if not isinstance(error, PeFormatError):
        return None
    return P2_MALFORMED_HEADER_REASONS.get(str(error))


def p2_section_disagreement_reason(comparison: dict) -> str | None:
    """Fallback only for isolated section count or normalized boundary differences."""
    fields = {m["field"] for m in comparison["mismatches"]}
    if not fields or not fields <= P2_SECTION_DISAGREEMENT_FIELDS:
        return None
    if "section_count" in fields:
        return "section_count_disagreement"
    return "raw_section_boundary_disagreement"


def build_p2_structure_map(data: bytes) -> StructureMap:
    """Apply the versioned malformed-header and section-disagreement policies."""
    try:
        structure = build_structure_map(data)
    except PeFormatError as error:
        reason = p2_malformed_header_reason(error)
        if reason is None:
            raise
        return build_unknown_structure_map(data, reason)
    reason = p2_section_disagreement_reason(compare_pefile(data))
    return build_unknown_structure_map(data, reason) if reason else structure


def compare_pefile(data: bytes):
    """Exact raw-field comparison, with native overlay semantics separately reported.

Any discrepancy is recorded, including null sections and field reordering. A missing
parser or parse error raises to the audit runner; neither counts as agreement.
"""
    import pefile

    layout = PeAtlas.from_bytes(data).layout
    pe = pefile.PE(data=data, fast_load=True)
    try:
        fields = {
            "magic": (0x20B if layout.is_pe32_plus else 0x10B, int(pe.OPTIONAL_HEADER.Magic)),
            "image_base": (layout.image_base, int(pe.OPTIONAL_HEADER.ImageBase)),
            "section_alignment": (layout.section_alignment, int(pe.OPTIONAL_HEADER.SectionAlignment)),
            "file_alignment": (layout.file_alignment, int(pe.OPTIONAL_HEADER.FileAlignment)),
            "size_of_headers": (layout.size_of_headers, int(pe.OPTIONAL_HEADER.SizeOfHeaders)),
            "section_count": (len(layout.sections), len(pe.sections)),
        }
        for index, name in ((2, "resource_directory"), (4, "certificate_directory")):
            directory = pe.OPTIONAL_HEADER.DATA_DIRECTORY
            theirs = ((int(directory[index].VirtualAddress), int(directory[index].Size))
                      if len(directory) > index else (0, 0))
            fields[name] = (data_directory(data, index), theirs)
        # pefile can reorder sections by RVA; compare in physical section-header order.
        sections = sorted(pe.sections, key=lambda s: s.get_file_offset())
        for i, (ours, other) in enumerate(zip(layout.sections, sections, strict=False)):
            for attr, key in (("rva", "VirtualAddress"), ("virtual_size", "Misc_VirtualSize"),
                              ("raw_offset", "PointerToRawData"), ("raw_size", "SizeOfRawData"),
                              ("characteristics", "Characteristics")):
                fields[f"section[{i}].{attr}"] = (getattr(ours, attr), int(getattr(other, key)))
        normalized_end = min(len(data), max([int(pe.OPTIONAL_HEADER.SizeOfHeaders)] + [
            min(int(s.PointerToRawData) + int(s.SizeOfRawData), len(data))
            for s in sections if int(s.PointerToRawData) > 0 and int(s.SizeOfRawData) > 0]))
        fields["raw_section_overlay_boundary"] = (layout.overlay_offset, normalized_end)
        native_overlay = pe.get_overlay_data_start_offset()
        native_overlay = len(data) if native_overlay is None else int(native_overlay)
        mismatches = [{"field": field, "peatlas": ours, "pefile": other}
                      for field, (ours, other) in fields.items() if ours != other]
        return {"raw_fields_agree": not mismatches, "mismatches": mismatches,
                "fields_compared": len(fields), "pefile_version": pefile.__version__,
                "native_overlay": {"peatlas": layout.overlay_offset, "pefile": native_overlay,
                                   "agrees": layout.overlay_offset == native_overlay},
                "pefile_warnings": pe.get_warnings()}
    finally:
        pe.close()


def structure_cam_mass(scores, imap: IntervalBinnedMap, structure: StructureMap):
    """Allocate each pixel's positive mass by source-byte overlap, without double counting."""
    structure.validate()
    if imap.file_size != structure.file_size:
        raise ValueError("file sizes differ")
    flat = np.asarray(scores, dtype=np.float64).reshape(-1)
    if len(flat) != imap.pixel_count or not np.isfinite(flat).all() or (flat < 0).any():
        raise ValueError("CAM must have finite nonnegative scores matching the raster")
    masses = dict.fromkeys(REGIONS, 0.0)
    for span in structure.spans:
        first = int(np.searchsorted(imap.ends, span.start, side="right"))
        last = int(np.searchsorted(imap.starts, span.end, side="left"))
        starts, ends = imap.starts[first:last], imap.ends[first:last]
        overlap = np.maximum(0, np.minimum(ends, span.end) - np.maximum(starts, span.start))
        masses[span.region] += float(np.sum(flat[first:last] * overlap / (ends - starts)))
    if not np.isclose(sum(masses.values()), float(flat.sum()), rtol=1e-10, atol=1e-10):
        raise ValueError("CAM mass conservation failed")
    return masses
