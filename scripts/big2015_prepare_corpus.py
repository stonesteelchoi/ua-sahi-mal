"""Extract a family-stratified BIG2015 subset from ``train.7z`` and rasterize it.

The archive is 18.8 GB compressed and 198 GB expanded, which is more disk than
this study has.  Two facts make it tractable:

* ``.bytes`` files live only in solid folders 69-93 (about 54 GB expanded).  The
  ``.asm`` disassembly -- the other 144 GB -- is not needed: masking byte ranges
  requires no disassembly.
* Work proceeds one solid folder at a time.  Each folder is expanded into scratch
  space, the selected samples are converted to PNG rasters, and the expanded
  ``.bytes`` are deleted before the next folder starts.  Peak extra disk is one
  folder, not the corpus.

The run is resumable: completed samples are recorded, so re-running picks up
where it stopped.  That matters because each invocation here has a wall-clock
limit well under the total extraction time.

Nothing in this script disassembles, imports, loads, or executes a sample.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ua_sahi_mal.evidence import corpus, raster  # noqa: E402

STATE_FORMAT = "big2015-prepare-1"


def load_state(path: Path) -> dict:
    if path.exists():
        state = json.loads(path.read_text(encoding="utf-8"))
        if state.get("format") == STATE_FORMAT:
            return state
    return {
        "format": STATE_FORMAT,
        "done_folders": [],
        "converted": [],
        "duplicates": [],
        "failures": [],
        "hashes": {},
    }


def save_state(state: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def folder_assignment(archive) -> dict[str, int]:
    """Which solid folder each archive entry lives in."""
    streams = archive.header.main_streams
    counts = streams.substreamsinfo.num_unpackstreams_folders
    names = [item.filename for item in archive.files]
    assignment: dict[str, int] = {}
    index = 0
    for folder_index, count in enumerate(counts):
        for name in names[index : index + count]:
            assignment[name] = folder_index
        index += count
    return assignment


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True)
    parser.add_argument("--labels", required=True)
    parser.add_argument("--rasters", required=True, help="where the PNG rasters go (kept)")
    parser.add_argument("--scratch", required=True, help="fast local scratch (deleted as it goes)")
    parser.add_argument("--state", required=True)
    parser.add_argument("--per-family", type=int, default=200)
    parser.add_argument("--width", type=int, default=raster.DEFAULT_WIDTH)
    parser.add_argument("--min-bytes", type=int, default=64 * 1024)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--max-folders", type=int, default=2, help="solid folders per invocation")
    parser.add_argument("--manifest", help="write the manifest when every folder is done")
    args = parser.parse_args()

    import py7zr

    labels = corpus.read_labels(args.labels)
    selection = corpus.stratified_selection(labels, per_family=args.per_family, seed=args.seed)

    state = load_state(Path(args.state))
    done = set(state["done_folders"])
    rasters = Path(args.rasters)
    rasters.mkdir(parents=True, exist_ok=True)
    scratch = Path(args.scratch)

    started = time.time()
    archive = py7zr.SevenZipFile(args.archive, "r")
    assignment = folder_assignment(archive)

    wanted: dict[int, list[str]] = {}
    for name, folder in assignment.items():
        if not name.endswith(".bytes"):
            continue
        identifier = Path(name).stem
        if identifier in selection:
            wanted.setdefault(folder, []).append(name)

    pending = [folder for folder in sorted(wanted) if folder not in done]
    print(
        f"{len(selection)} selected, {sum(len(v) for v in wanted.values())} present in archive, "
        f"{len(pending)} of {len(wanted)} folders left",
        flush=True,
    )
    if not pending:
        print("nothing left to extract", flush=True)
    archive.close()

    for folder in pending[: args.max_folders]:
        targets = wanted[folder]
        stage = scratch / f"folder{folder}"
        if stage.exists():
            shutil.rmtree(stage)
        stage.mkdir(parents=True, exist_ok=True)

        mark = time.time()
        with py7zr.SevenZipFile(args.archive, "r") as handle:
            handle.extract(path=stage, targets=targets)
        extracted = sorted(stage.rglob("*.bytes"))
        elapsed = time.time() - mark
        print(f"folder {folder}: extracted {len(extracted)} files in {elapsed:.0f}s", flush=True)

        report = corpus.convert_dumps(
            extracted,
            selection,
            rasters,
            width=args.width,
            seen_hashes=state["hashes"],
            min_bytes=args.min_bytes,
        )
        for entry in report.converted:
            state["converted"].append(entry.to_dict())
            state["hashes"][entry.content_sha256] = entry.sample_id
        state["duplicates"].extend(report.duplicates)
        state["failures"].extend(report.failures)
        state["done_folders"].append(folder)
        save_state(state, Path(args.state))
        shutil.rmtree(stage, ignore_errors=True)
        print(
            f"  converted {len(report.converted)}  duplicates {len(report.duplicates)}  "
            f"failures {len(report.failures)}  total {len(state['converted'])}",
            flush=True,
        )

    remaining = [folder for folder in sorted(wanted) if folder not in set(state["done_folders"])]
    print(f"done in {time.time() - started:.0f}s; {len(remaining)} folders remain", flush=True)

    if not remaining and args.manifest:
        entries = [corpus.CorpusEntry(**row) for row in state["converted"]]
        report = corpus.ConversionReport(
            converted=entries, duplicates=state["duplicates"], failures=state["failures"]
        )
        path = corpus.write_manifest(
            report,
            args.manifest,
            width=args.width,
            per_family=args.per_family,
            seed=args.seed,
            extra={"archive": str(args.archive), "source": "BIG2015 train.7z"},
        )
        print(f"manifest -> {path}", flush=True)
        print(json.dumps(corpus.family_counts(entries), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
