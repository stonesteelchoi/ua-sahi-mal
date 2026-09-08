"""Synthetic PE assembler for coordinate benchmarks (Tier 0 fixtures / Tier 1).

Assembles the smallest well-formed (or deliberately malformed) PE header bytes
needed to exercise coordinate mapping and to host a planted, inert benchmark
region. It is NOT a malware generator: section bodies are inert filler bytes,
nothing is executable-as-malware, and nothing is ever executed. Field values are
written directly so malformed layouts (overlaps, raw-past-EOF, raw>virtual) can
be constructed on purpose.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

DOS_STUB_SIZE = 0x40  # e_lfanew at 0x3C; PE headers start right after


@dataclass
class SectionSpec:
    name: str
    rva: int
    virtual_size: int
    raw_offset: int
    raw_size: int
    characteristics: int = 0x40000040  # readable initialized data (arbitrary, inert)
    fill: int = 0xAA  # inert filler for the raw body


def build_pe(
    *,
    sections: list[SectionSpec],
    image_base: int = 0x00400000,
    section_alignment: int = 0x1000,
    file_alignment: int = 0x200,
    size_of_headers: int = 0x200,
    pe32_plus: bool = False,
    certificate: tuple[int, int] | None = None,  # (file_offset, size)
    overlay: bytes = b"",
    truncate_to: int | None = None,
    machine: int | None = None,     # COFF Machine; None -> default for the magic
    subsystem: int = 2,             # OptionalHeader.Subsystem (2 = GUI); armed default
    disarm: bool = False,           # SOREL-style: zero Machine and Subsystem
) -> bytes:
    """Assemble a synthetic PE image and return its bytes.

    ``disarm=True`` reproduces SOREL-20M's accidental-execution guard by zeroing
    ``FileHeader.Machine`` and ``OptionalHeader.Subsystem`` (see the SOREL FAQ).
    These fields do not participate in PEAtlas coordinate mapping, so a disarmed
    image must map identically to its armed twin while hashing differently.
    """
    num_dirs = 16
    opt_size = (112 if pe32_plus else 96) + num_dirs * 8

    pe_off = DOS_STUB_SIZE
    coff_off = pe_off + 4
    opt_off = coff_off + 20
    sec_table_off = opt_off + opt_size

    end = size_of_headers
    for s in sections:
        if s.raw_size > 0 and s.raw_offset > 0:
            end = max(end, s.raw_offset + s.raw_size)
    if certificate is not None:
        end = max(end, certificate[0] + certificate[1])
    overlay_at = end
    end += len(overlay)
    end = max(end, sec_table_off + len(sections) * 40)

    buf = bytearray(end)
    buf[0:2] = b"MZ"
    struct.pack_into("<I", buf, 0x3C, pe_off)

    buf[pe_off:pe_off + 4] = b"PE\x00\x00"
    if machine is None:
        machine = 0x8664 if pe32_plus else 0x014C
    if disarm:
        machine = 0
        subsystem = 0
    struct.pack_into("<H", buf, coff_off + 0, machine)
    struct.pack_into("<H", buf, coff_off + 2, len(sections))
    struct.pack_into("<H", buf, coff_off + 16, opt_size)

    magic = 0x20B if pe32_plus else 0x10B
    struct.pack_into("<H", buf, opt_off + 0, magic)
    struct.pack_into("<H", buf, opt_off + 68, subsystem)  # OptionalHeader.Subsystem
    if pe32_plus:
        struct.pack_into("<Q", buf, opt_off + 24, image_base)
        num_dirs_off, dirs_off = opt_off + 108, opt_off + 112
    else:
        struct.pack_into("<I", buf, opt_off + 28, image_base)
        num_dirs_off, dirs_off = opt_off + 92, opt_off + 96
    struct.pack_into("<I", buf, opt_off + 32, section_alignment)
    struct.pack_into("<I", buf, opt_off + 36, file_alignment)
    struct.pack_into("<I", buf, opt_off + 60, size_of_headers)
    struct.pack_into("<I", buf, num_dirs_off, num_dirs)
    if certificate is not None:
        struct.pack_into("<I", buf, dirs_off + 4 * 8, certificate[0])
        struct.pack_into("<I", buf, dirs_off + 4 * 8 + 4, certificate[1])

    for i, s in enumerate(sections):
        base = sec_table_off + i * 40
        buf[base:base + 8] = s.name.encode("latin-1")[:8].ljust(8, b"\x00")
        struct.pack_into("<I", buf, base + 8, s.virtual_size)
        struct.pack_into("<I", buf, base + 12, s.rva)
        struct.pack_into("<I", buf, base + 16, s.raw_size)
        struct.pack_into("<I", buf, base + 20, s.raw_offset)
        struct.pack_into("<I", buf, base + 36, s.characteristics)
        if s.raw_size > 0 and s.raw_offset > 0:
            hi = min(s.raw_offset + s.raw_size, len(buf))
            for off in range(s.raw_offset, hi):
                buf[off] = s.fill

    if certificate is not None:
        c_off, c_size = certificate
        for off in range(c_off, min(c_off + c_size, len(buf))):
            buf[off] = 0xCC

    if overlay:
        buf[overlay_at:overlay_at + len(overlay)] = overlay

    out = bytes(buf)
    return out[:truncate_to] if truncate_to is not None else out
