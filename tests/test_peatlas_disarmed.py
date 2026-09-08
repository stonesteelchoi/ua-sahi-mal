"""Robustness of PEAtlas coordinates to SOREL-style disarming.

SOREL-20M zeroes ``FileHeader.Machine`` and ``OptionalHeader.Subsystem`` to
prevent accidental execution, so a downloaded disarmed sample re-hashes to a
different SHA than its S3 key (the original SHA). These fields are not part of the
coordinate contract, so disarming must not change any file-offset/RVA/VA mapping.
This is the real-PE-shaped evidence for E1 / G1 in the SOREL amendment.

No malware is used or executed; fixtures are synthetic inert PEs.
"""

from __future__ import annotations

import hashlib
import warnings

import pytest

from ua_sahi_mal.peatlas import PeAtlas, parse_pe
from ua_sahi_mal.peatlas.pebuild import SectionSpec, build_pe

# COFF Machine is at 0x44; OptionalHeader.Subsystem at 0x9C for this builder layout.
_MACHINE_OFF = 0x44
_SUBSYSTEM_OFF = 0x9C


def _two_section(**kw) -> bytes:
    sections = [
        SectionSpec(".text", rva=0x1000, virtual_size=0x180, raw_offset=0x200, raw_size=0x200),
        SectionSpec(".data", rva=0x2000, virtual_size=0x400, raw_offset=0x400, raw_size=0x200),
    ]
    return build_pe(sections=sections, overlay=b"OVERLAY_BYTES!!!", **kw)


def test_disarming_does_not_change_the_layout_or_mappings():
    armed = _two_section()
    disarmed = _two_section(disarm=True)
    # PeLayout has no Machine/Subsystem field -> the parsed layouts are identical.
    assert parse_pe(armed) == parse_pe(disarmed)

    a, d = PeAtlas.from_bytes(armed), PeAtlas.from_bytes(disarmed)
    for off in (0x0, 0x10, 0x200, 0x37F, 0x380, 0x400, 0x5FF, 0x600, 0x60F):
        assert a.offset_to_rva(off).status == d.offset_to_rva(off).status
        assert a.offset_to_rva(off).value == d.offset_to_rva(off).value
        assert a.offset_to_va(off).value == d.offset_to_va(off).value
    for rva in (0x10, 0x1000, 0x117F, 0x1180, 0x2000, 0x2200, 0x2400):
        assert a.rva_to_offset(rva).status == d.rva_to_offset(rva).status
        assert a.rva_to_offset(rva).value == d.rva_to_offset(rva).value


def test_disarming_changes_only_machine_and_subsystem_bytes_and_the_hash():
    armed = _two_section()
    disarmed = _two_section(disarm=True)
    assert len(armed) == len(disarmed)
    assert hashlib.sha256(armed).hexdigest() != hashlib.sha256(disarmed).hexdigest()
    # exactly the two disarmed fields differ; everything else is byte-identical
    differing = {i for i in range(len(armed)) if armed[i] != disarmed[i]}
    assert differing <= {_MACHINE_OFF, _MACHINE_OFF + 1, _SUBSYSTEM_OFF, _SUBSYSTEM_OFF + 1}
    assert armed[_MACHINE_OFF:_MACHINE_OFF + 2] != disarmed[_MACHINE_OFF:_MACHINE_OFF + 2]
    assert disarmed[_MACHINE_OFF:_MACHINE_OFF + 2] == b"\x00\x00"
    assert disarmed[_SUBSYSTEM_OFF:_SUBSYSTEM_OFF + 2] == b"\x00\x00"


def test_disarmed_file_still_maps_coordinates():
    atlas = PeAtlas.from_bytes(_two_section(disarm=True))
    assert atlas.offset_to_rva(0x200).value == 0x1000  # first .text byte
    assert atlas.rva_to_offset(0x2000).value == 0x400  # first .data byte


def test_disarmed_cross_parser_agreement_pefile():
    pefile = pytest.importorskip("pefile")
    disarmed = _two_section(disarm=True)
    atlas = PeAtlas.from_bytes(disarmed)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        pe = pefile.PE(data=disarmed, fast_load=True)

    # pefile still reads the section table despite Machine=0/Subsystem=0
    assert pe.OPTIONAL_HEADER.ImageBase == atlas.layout.image_base
    assert pe.OPTIONAL_HEADER.SizeOfHeaders == atlas.layout.size_of_headers
    assert len(pe.sections) == len(atlas.layout.sections)
    for sec, ref in zip(atlas.layout.sections, pe.sections, strict=True):
        assert sec.rva == ref.VirtualAddress
        assert sec.raw_offset == ref.PointerToRawData
        assert sec.raw_size == ref.SizeOfRawData
    # sampled conversions agree between PEAtlas and the independent parser
    for rva in (0x1000, 0x1040, 0x2000, 0x21FF):
        res = atlas.rva_to_offset(rva)
        if res.ok:
            assert pe.get_offset_from_rva(rva) == res.value
