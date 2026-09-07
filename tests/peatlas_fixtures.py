"""Minimal synthetic PE builder for PEAtlas Tier 0 tests.

This is a *test fixture helper*, not a Tier 1 dataset generator: it emits the
smallest well-formed (or deliberately malformed) PE header bytes needed to
exercise coordinate mapping. It never contains executable payloads or malware;
section bodies are inert filler bytes.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

DOS_STUB_SIZE = 0x40  # e_lfanew lives at 0x3C; PE headers start right after


@dataclass
class SecSpec:
    name: str
    rva: int
    virtual_size: int
    raw_offset: int
    raw_size: int
    characteristics: int = 0x40000040  # readable initialized data (arbitrary, inert)
    fill: int = 0xAA  # inert filler byte for the raw body


def build_pe(
    *,
    sections: list[SecSpec],
    image_base: int = 0x00400000,
    section_alignment: int = 0x1000,
    file_alignment: int = 0x200,
    size_of_headers: int = 0x200,
    pe32_plus: bool = False,
    certificate: tuple[int, int] | None = None,  # (file_offset, size)
    overlay: bytes = b"",
    truncate_to: int | None = None,
) -> bytes:
    """Assemble a synthetic PE image.

    The caller supplies raw section fields directly, so malformed layouts
    (overlaps, raw data past EOF via ``truncate_to``, raw>virtual padding) can be
    constructed on purpose. Returns the file bytes.
    """
    num_dirs = 16
    if pe32_plus:
        opt_size = 112 + num_dirs * 8
    else:
        opt_size = 96 + num_dirs * 8

    pe_off = DOS_STUB_SIZE
    coff_off = pe_off + 4
    opt_off = coff_off + 20
    sec_table_off = opt_off + opt_size

    # Determine total size from the furthest of: headers, section raw ends, cert, overlay.
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

    # DOS header
    buf[0:2] = b"MZ"
    struct.pack_into("<I", buf, 0x3C, pe_off)

    # PE signature + COFF header
    buf[pe_off:pe_off + 4] = b"PE\x00\x00"
    machine = 0x8664 if pe32_plus else 0x014C
    struct.pack_into("<H", buf, coff_off + 0, machine)
    struct.pack_into("<H", buf, coff_off + 2, len(sections))
    struct.pack_into("<H", buf, coff_off + 16, opt_size)

    # Optional header
    magic = 0x20B if pe32_plus else 0x10B
    struct.pack_into("<H", buf, opt_off + 0, magic)
    if pe32_plus:
        struct.pack_into("<Q", buf, opt_off + 24, image_base)
        num_dirs_off = opt_off + 108
        dirs_off = opt_off + 112
    else:
        struct.pack_into("<I", buf, opt_off + 28, image_base)
        num_dirs_off = opt_off + 92
        dirs_off = opt_off + 96
    struct.pack_into("<I", buf, opt_off + 32, section_alignment)
    struct.pack_into("<I", buf, opt_off + 36, file_alignment)
    struct.pack_into("<I", buf, opt_off + 60, size_of_headers)
    struct.pack_into("<I", buf, num_dirs_off, num_dirs)
    if certificate is not None:
        struct.pack_into("<I", buf, dirs_off + 4 * 8, certificate[0])
        struct.pack_into("<I", buf, dirs_off + 4 * 8 + 4, certificate[1])

    # Section table + raw bodies
    for i, s in enumerate(sections):
        base = sec_table_off + i * 40
        name = s.name.encode("latin-1")[:8].ljust(8, b"\x00")
        buf[base:base + 8] = name
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
    if truncate_to is not None:
        out = out[:truncate_to]
    return out


def simple_two_section() -> bytes:
    """A canonical, well-formed 2-section PE used across mapping tests.

    - headers: [0, 0x200)
    - .text : rva 0x1000, vsize 0x180, raw [0x200, 0x400)  (raw>virtual: padding tail)
    - .data : rva 0x2000, vsize 0x400, raw [0x400, 0x600)  (virtual>raw: virtual-only tail)
    - overlay: 16 bytes after 0x600
    """
    sections = [
        SecSpec(".text", rva=0x1000, virtual_size=0x180, raw_offset=0x200, raw_size=0x200),
        SecSpec(".data", rva=0x2000, virtual_size=0x400, raw_offset=0x400, raw_size=0x200),
    ]
    return build_pe(sections=sections, overlay=b"OVERLAY_BYTES!!!")
