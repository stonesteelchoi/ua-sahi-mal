"""Test fixtures for PEAtlas: thin wrapper over the package PE assembler.

The reusable assembler lives in ``ua_sahi_mal.peatlas.pebuild``; this module only
adds the canonical fixtures used across the tests. No malware, nothing executed.
"""

from __future__ import annotations

from ua_sahi_mal.peatlas.pebuild import SectionSpec as SecSpec
from ua_sahi_mal.peatlas.pebuild import build_pe

__all__ = ["SecSpec", "build_pe", "simple_two_section"]


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
