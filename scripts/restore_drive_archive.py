"""Verify and concatenate the Drive backup parts without extracting the archive."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


def restore(manifest_path: Path, parts_dir: Path, output: Path) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    original = manifest["original_archive"]
    parts = original["parts"]
    if original["status"] != "complete" or not parts:
        raise ValueError("The manifest does not describe a complete archive")
    if Path(original["filename"]).name != original["filename"]:
        raise ValueError("Invalid archive filename")
    if sum(part["size_bytes"] for part in parts) != original["size_bytes"]:
        raise ValueError("Part sizes do not add up to the original archive size")
    for number, part in enumerate(parts, start=1):
        expected = f"{original['filename']}.part{number:03}"
        if part["filename"] != expected or part["number"] != number:
            raise ValueError(f"Missing or out-of-order part: {expected}")
        source = parts_dir / expected
        if source.stat().st_size != part["size_bytes"]:
            raise ValueError(f"Unexpected file size: {source}")
    if not output.parent.is_dir():
        raise ValueError("Create the output directory first")
    if shutil.disk_usage(output.parent).free < original["size_bytes"]:
        raise ValueError("Insufficient free space for the reconstructed archive")
    archive_hash = hashlib.sha256()
    # Exclusive creation guarantees that an existing file is never overwritten.
    stream = output.open("xb")
    try:
        with stream:
            for part in parts:
                part_hash = hashlib.sha256()
                read_size = 0
                with (parts_dir / part["filename"]).open("rb") as source:
                    while block := source.read(8 * 1024 * 1024):
                        stream.write(block)
                        part_hash.update(block)
                        archive_hash.update(block)
                        read_size += len(block)
                if read_size != part["size_bytes"] or part_hash.hexdigest() != part["sha256"]:
                    raise ValueError(f"Integrity check failed: {part['filename']}")
                print(f"Verified {part['number']}/{len(parts)}", flush=True)
            if archive_hash.hexdigest() != original["sha256"]:
                raise ValueError("Reconstructed archive SHA-256 does not match")
    except BaseException:
        # This invocation created the output exclusively; discard only that partial file.
        output.unlink(missing_ok=True)
        raise
    print(f"Restored {output}: {original['size_bytes']} bytes; SHA-256 verified")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("docs/artifacts/manifest.json"))
    parser.add_argument("--parts-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    restore(args.manifest, args.parts_dir, args.output)


if __name__ == "__main__":
    main()
