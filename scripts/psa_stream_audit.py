"""Stream the PSA PE Malware Machine Learning Dataset archive and emit a P0 manifest.

The archive is a *solid* 7z, so random access is expensive; this makes exactly one
sequential pass.  Sample bytes are decompressed into memory, measured, and dropped.

    **No sample byte is ever written to disk.**

That is deliberate: the archive holds 114,737 live malware binaries.  Nothing is
extracted, so on-access antivirus never fires and no exclusion is required.  Nothing
here executes, imports, or loads a sample -- pefile parses the bytes as data only.

Usage (Windows, from the repository root, inside the project venv):

    .\\.venv\\Scripts\\python.exe scripts\\psa_stream_audit.py ^
        --archive "C:\\research\\ua-sahi-mal\\datasets\\pe-machine-learning-dataset.7z" ^
        --out "D:\\secure-malware-data\\psa\\manifest_stage2.csv"

    # smoke test first (stops after N samples, ~seconds):
    ... --limit 200

Requires: py7zr, pefile.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import os
import sys
import time

import numpy as np
import pefile
import py7zr
from py7zr.io import Py7zIO, WriterFactory

PIXELS = 224 * 224  # interval-binned-v1 raster size; decides the projection policy
SAMPLE_PREFIX = "pe-machine-learning-dataset/samples/"

FIELDS = [
    "sample_id", "archive_size", "sha256", "magic_ok", "parser_status", "parser_error",
    "pe_kind", "machine", "timestamp", "subsystem", "dll_characteristics",
    "linker_major", "linker_minor", "section_count", "section_names",
    "size_of_headers", "size_of_image", "entry_point",
    "executable_section_bytes", "non_executable_section_bytes",
    "overlay_bytes", "certificate_bytes", "signed",
    "max_section_entropy", "nonstandard_section_names", "imphash",
    "file_entropy", "repr_policy",
]

STANDARD_SECTIONS = {
    ".text", ".data", ".rdata", ".idata", ".edata", ".pdata", ".rsrc", ".reloc",
    ".bss", ".tls", ".debug", ".didat", ".sdata", ".crt", ".gfids", ".00cfg",
}


def safe_name(raw: bytes) -> str:
    """Section names are attacker-controlled bytes; keep the manifest printable ASCII."""
    out = []
    for b in raw.rstrip(b"\x00"):
        out.append(chr(b) if 0x20 <= b <= 0x7E and chr(b) not in '"|,' else f"\\x{b:02x}")
    return "".join(out)


def shannon_entropy(data: bytes) -> float:
    """Byte-value Shannon entropy. numpy because the pure-Python Counter loop was
    the dominant cost of the whole pass (measured: 2.1 MiB/s -> decompression-bound)."""
    if not data:
        return 0.0
    counts = np.bincount(np.frombuffer(data, dtype=np.uint8), minlength=256)
    nz = counts[counts > 0].astype(np.float64)
    pr = nz / nz.sum()
    return float(-(pr * np.log2(pr)).sum())


def describe(data: bytes) -> dict:
    """Parse one PE image from bytes. Never executes or loads it."""
    row = {k: "" for k in FIELDS}
    row["magic_ok"] = "1" if data[:2] == b"MZ" else "0"
    row["file_entropy"] = f"{shannon_entropy(data):.6f}"
    row["repr_policy"] = "mean_pool" if len(data) >= PIXELS else "nearest_repetition"
    if data[:2] != b"MZ":
        row["parser_status"] = "not_mz"
        return row
    try:
        pe = pefile.PE(data=data, fast_load=True)
    except Exception as exc:  # pefile raises PEFormatError and others
        row["parser_status"] = "parse_failed"
        row["parser_error"] = type(exc).__name__
        return row
    try:
        magic = pe.OPTIONAL_HEADER.Magic
        row["pe_kind"] = {0x10B: "PE32", 0x20B: "PE32+"}.get(magic, f"magic_{magic:#x}")
        row["machine"] = f"{pe.FILE_HEADER.Machine:#06x}"
        row["timestamp"] = str(pe.FILE_HEADER.TimeDateStamp)
        row["subsystem"] = str(pe.OPTIONAL_HEADER.Subsystem)
        row["dll_characteristics"] = str(pe.OPTIONAL_HEADER.DllCharacteristics)
        row["linker_major"] = str(pe.OPTIONAL_HEADER.MajorLinkerVersion)
        row["linker_minor"] = str(pe.OPTIONAL_HEADER.MinorLinkerVersion)
        row["size_of_headers"] = str(pe.OPTIONAL_HEADER.SizeOfHeaders)
        row["size_of_image"] = str(pe.OPTIONAL_HEADER.SizeOfImage)
        row["entry_point"] = str(pe.OPTIONAL_HEADER.AddressOfEntryPoint)

        sections = list(pe.sections)
        row["section_count"] = str(len(sections))
        names, execb, nonexecb, ents, odd = [], 0, 0, [], 0
        for s in sections:
            name = safe_name(s.Name)
            names.append(name)
            if name.lower() not in STANDARD_SECTIONS:
                odd += 1
            raw = int(s.SizeOfRawData)
            if s.Characteristics & 0x20000000:  # IMAGE_SCN_MEM_EXECUTE
                execb += raw
            else:
                nonexecb += raw
            try:
                sd = s.get_data()
                if sd:
                    ents.append(shannon_entropy(sd))
            except Exception:
                pass
        row["section_names"] = "|".join(names)
        row["executable_section_bytes"] = str(execb)
        row["non_executable_section_bytes"] = str(nonexecb)
        row["nonstandard_section_names"] = str(odd)
        row["max_section_entropy"] = f"{max(ents):.6f}" if ents else ""

        sec_dir = pe.OPTIONAL_HEADER.DATA_DIRECTORY[4]  # IMAGE_DIRECTORY_ENTRY_SECURITY
        cert = int(sec_dir.Size)
        row["certificate_bytes"] = str(cert)
        row["signed"] = "1" if cert > 0 else "0"

        try:
            start = pe.get_overlay_data_start_offset()
            row["overlay_bytes"] = str(len(data) - start) if start is not None else "0"
        except Exception:
            row["overlay_bytes"] = ""

        try:
            pe.parse_data_directories(
                directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"]]
            )
            row["imphash"] = pe.get_imphash()
        except Exception:
            row["imphash"] = ""

        row["parser_status"] = "ok"
    except Exception as exc:
        row["parser_status"] = "partial"
        row["parser_error"] = type(exc).__name__
    finally:
        try:
            pe.close()
        except Exception:
            pass
    return row


class SampleIO(Py7zIO):
    """Collects one member in memory, hands it to `sink`, then releases it."""

    def __init__(self, filename: str, sink, max_bytes: int):
        self.filename = filename
        self._sink = sink
        self._max = max_bytes
        self._buf = bytearray()
        self._sha = hashlib.sha256()
        self._size = 0
        self._over = False

    def write(self, s):
        self._size += len(s)
        self._sha.update(s)
        if not self._over:
            if self._size > self._max:
                self._over = True
                self._buf = bytearray()
            else:
                self._buf += s
        return len(s)

    def read(self, size=None):
        return bytes(self._buf)

    def seek(self, offset, whence=0):
        return 0

    def flush(self):
        return None

    def size(self):
        return self._size

    def close(self):
        self._sink(self.filename, bytes(self._buf), self._sha.hexdigest(), self._size, self._over)
        self._buf = bytearray()
        return None


class AuditFactory(WriterFactory):
    def __init__(self, sink, max_bytes):
        self._sink = sink
        self._max = max_bytes

    def create(self, filename: str) -> Py7zIO:
        return SampleIO(filename, self._sink, self._max)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--archive", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--password", default="infected")
    ap.add_argument("--limit", type=int, default=0, help="stop after N samples (smoke test)")
    ap.add_argument("--analysis", choices=("full", "hash-only"), default="full",
                    help="hash-only measures the decompression ceiling (no PE parsing)")
    ap.add_argument("--max-bytes", type=int, default=512 * 1024 * 1024,
                    help="skip in-memory analysis above this size (still hashed)")
    args = ap.parse_args()

    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
    fh = open(args.out, "w", newline="", encoding="utf-8")
    writer = csv.DictWriter(fh, fieldnames=FIELDS, quoting=csv.QUOTE_MINIMAL,
                            escapechar="\\", lineterminator="\n")
    writer.writeheader()

    state = {"n": 0, "t0": time.time(), "bytes": 0, "stop": False}

    def sink(name, data, sha, size, oversized):
        if not name.startswith(SAMPLE_PREFIX):
            return
        state["n"] += 1
        state["bytes"] += size
        if oversized:
            row = {k: "" for k in FIELDS}
            row["parser_status"] = "skipped_oversized"
            row["repr_policy"] = "mean_pool"
        elif args.analysis == "hash-only":
            row = {k: "" for k in FIELDS}
            row["parser_status"] = "hash_only"
            row["magic_ok"] = "1" if data[:2] == b"MZ" else "0"
            row["repr_policy"] = "mean_pool" if size >= PIXELS else "nearest_repetition"
        else:
            row = describe(data)
        row["sample_id"] = name[len(SAMPLE_PREFIX):]
        row["archive_size"] = str(size)
        row["sha256"] = sha
        for k, v in row.items():
            if isinstance(v, str) and any(ord(c) < 0x20 or ord(c) == 0x7F for c in v):
                row[k] = "".join(c if 0x20 <= ord(c) < 0x7F else f"\\x{ord(c):02x}" for c in v)
        writer.writerow(row)
        n = state["n"]
        if n % 2000 == 0:
            el = time.time() - state["t0"]
            gb = state["bytes"] / 2**30
            print(f"  {n:,} samples  {gb:.1f} GiB  {el/60:.1f} min  "
                  f"{gb*1024/max(el,1):.0f} MiB/s", flush=True)
            fh.flush()
        if args.limit and n >= args.limit:
            state["stop"] = True
            raise KeyboardInterrupt("limit reached")

    print(f"streaming {args.archive}", flush=True)
    try:
        with py7zr.SevenZipFile(args.archive, mode="r", password=args.password) as z:
            z.extractall(factory=AuditFactory(sink, args.max_bytes))
    except KeyboardInterrupt:
        if not state["stop"]:
            raise
        print("stopped at --limit", flush=True)
    finally:
        fh.close()

    el = time.time() - state["t0"]
    print(f"done: {state['n']:,} samples, {state['bytes']/2**30:.1f} GiB read, "
          f"{el/60:.1f} min -> {args.out}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
