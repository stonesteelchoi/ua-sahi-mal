"""Parser/analyzer disagreement ledger for the SOREL cohort (amendment §7 E1).

When PEAtlas and an independent parser (pefile) disagree, the disagreement must be
*explained and categorised*, not silently dropped. This module rebuilds both
parsers' structural views for a disagreeing file (in memory, static-only) and
classifies the cause. Only structural header fields are recorded — no code bytes,
no execution. The per-file ledger (which carries the SHA) lives in the isolated
path; console summaries are SHA-free.

Categories:
  * ``section_count:null_headers`` — the declared section table entries are all
    zero bytes; PEAtlas keeps them as raw-less sections, pefile stops at the first
    null header. Mapping-relevant view agrees (no raw data either way).
  * ``section_count:pefile_truncated`` — pefile reported fewer sections for another
    reason (see its warnings), e.g. a header beyond the file.
  * ``section_fields`` — same count, but rva/raw_offset/raw_size differ.
  * ``pefile_error`` / ``peatlas_error`` — one parser raised.
  * ``unknown`` — none of the above.
"""

from __future__ import annotations

import zlib
from dataclasses import asdict, dataclass, field

from .static_stage import StaticOnlyNotAcknowledgedError, locate_pe_fields, verify_disarmed


@dataclass
class LedgerEntry:
    case_id: str                      # SHA-free label used on the console ("case-01", ...)
    sorel_original_sha256: str        # private; only in the isolated ledger file
    strict_status: str
    category: str
    raw_agreement: bool | None
    peatlas: dict[str, object] = field(default_factory=dict)
    pefile: dict[str, object] = field(default_factory=dict)
    section_table_hex: str = ""       # declared section headers (40*N bytes) — structural only
    note: str = ""

    def public_summary(self) -> str:
        """One SHA-free line for the console."""
        n_ours = self.peatlas.get("n_sections", "?")
        n_pe = self.pefile.get("n_sections", "?")
        return (f"{self.case_id}: {self.category}  peatlas_sections={n_ours} pefile_sections={n_pe} "
                f"raw_agreement={self.raw_agreement}")


def _u16(b: bytes, o: int) -> int:
    return int.from_bytes(b[o:o + 2], "little")


def _u32(b: bytes, o: int) -> int:
    return int.from_bytes(b[o:o + 4], "little")


def _declared_section_table(data: bytes) -> tuple[int, int, bytes]:
    """Return (num_sections, table_offset, raw_table_bytes) from the COFF header."""
    e_lfanew = _u32(data, 0x3C)
    coff = e_lfanew + 4
    num = _u16(data, coff + 2)
    size_opt = _u16(data, coff + 16)
    table = coff + 20 + size_opt
    raw = data[table:table + 40 * num]
    return num, table, raw


def build_ledger_entry(compressed: bytes, *, sha256: str, case_id: str,
                       strict_status: str, static_only: bool) -> LedgerEntry:
    """Rebuild both parser views for one disagreeing artefact (in memory only)."""
    if not static_only:
        raise StaticOnlyNotAcknowledgedError("ledger rebuild decompresses; static_only=True required")
    data = zlib.decompress(compressed)
    entry = LedgerEntry(case_id=case_id, sorel_original_sha256=sha256,
                        strict_status=strict_status, category="unknown", raw_agreement=None)
    try:
        machine, subsystem = locate_pe_fields(data)
        entry.peatlas["disarmed"] = verify_disarmed(data)
        entry.peatlas["machine"] = machine
        entry.peatlas["subsystem"] = subsystem
    except ValueError as exc:
        entry.note = f"not a PE: {exc}"
        return entry

    num, table, raw_table = _declared_section_table(data)
    entry.peatlas["declared_sections"] = num
    entry.peatlas["section_table_offset"] = table
    entry.section_table_hex = raw_table.hex()
    null_headers = all(b == 0 for b in raw_table) if raw_table else False
    entry.peatlas["section_table_all_null"] = null_headers

    # PEAtlas view
    try:
        from ua_sahi_mal.peatlas.atlas import parse_pe
        layout = parse_pe(data)
        entry.peatlas["n_sections"] = len(layout.sections)
        entry.peatlas["sections"] = [
            {"name": s.name, "rva": s.rva, "virtual_size": s.virtual_size,
             "raw_offset": s.raw_offset, "raw_size": s.raw_size, "has_raw": s.has_raw}
            for s in layout.sections
        ]
        entry.peatlas["overlay_offset"] = layout.overlay_offset
        entry.peatlas["warnings"] = list(layout.warnings)
        raw_ours = {(s.raw_offset, s.raw_size) for s in layout.sections if s.has_raw}
    except Exception as exc:  # noqa: BLE001
        entry.peatlas["error"] = f"{type(exc).__name__}: {exc}"
        entry.category = "peatlas_error"
        return entry

    # pefile view
    try:
        import pefile  # type: ignore
        pe = pefile.PE(data=data, fast_load=True)
        try:
            entry.pefile["n_sections"] = len(pe.sections)
            entry.pefile["NumberOfSections"] = int(pe.FILE_HEADER.NumberOfSections)
            entry.pefile["SizeOfOptionalHeader"] = int(pe.FILE_HEADER.SizeOfOptionalHeader)
            entry.pefile["sections"] = [
                {"name": s.Name.rstrip(b"\x00").decode("latin-1", "replace"),
                 "rva": int(s.VirtualAddress), "virtual_size": int(s.Misc_VirtualSize),
                 "raw_offset": int(s.PointerToRawData), "raw_size": int(s.SizeOfRawData)}
                for s in pe.sections
            ]
            entry.pefile["warnings"] = list(pe.get_warnings())
            raw_pe = {(int(s.PointerToRawData), int(s.SizeOfRawData)) for s in pe.sections
                      if int(s.SizeOfRawData) > 0 and int(s.PointerToRawData) > 0}
        finally:
            pe.close()
    except ImportError:
        entry.pefile["error"] = "pefile unavailable"
        entry.category = "pefile_unavailable"
        return entry
    except Exception as exc:  # noqa: BLE001
        entry.pefile["error"] = f"{type(exc).__name__}: {exc}"
        entry.category = "pefile_error"
        return entry

    entry.raw_agreement = raw_ours == raw_pe
    n_ours = entry.peatlas["n_sections"]
    n_pe = entry.pefile["n_sections"]
    if n_ours != n_pe:
        if null_headers and n_pe == 0:
            entry.category = "section_count:null_headers"
            entry.note = ("declared section headers are all zero bytes; PEAtlas keeps them as "
                          "raw-less sections, pefile stops at the first null header")
        else:
            entry.category = "section_count:pefile_truncated"
            entry.note = "see pefile warnings for why it reported fewer sections"
    else:
        entry.category = "section_fields"
    return entry


def entry_to_dict(entry: LedgerEntry) -> dict[str, object]:
    return asdict(entry)
