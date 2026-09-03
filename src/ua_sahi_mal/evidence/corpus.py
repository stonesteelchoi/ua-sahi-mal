"""Selecting, splitting, and converting the BIG2015 corpus.

The corpus is family-imbalanced by a factor of 70 (42 samples in the smallest
family, 2,942 in the largest), and the full ``train.7z`` needs disk this study
does not have.  Both are handled the same way: a family-stratified subset, with
a cap per family, drawn deterministically from a seed so the selection is a
property of the manifest rather than of the run.

Splits are by content hash, not by filename, so a duplicate that appears under
two identifiers cannot land on both sides.
"""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np

from ua_sahi_mal.evidence import raster

SPLIT_TRAIN = "train"
SPLIT_VALIDATION = "validation"
SPLIT_TEST = "test"
SPLITS = (SPLIT_TRAIN, SPLIT_VALIDATION, SPLIT_TEST)

DEFAULT_SPLIT_FRACTIONS = (0.70, 0.15, 0.15)
MANIFEST_FORMAT = "evidence-corpus-1"


@dataclass(frozen=True)
class CorpusEntry:
    """One sample: where it came from, what family it is, and where it landed."""

    sample_id: str
    label: int
    split: str
    byte_count: int
    valid_fraction: float
    content_sha256: str
    raster_path: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def read_labels(path: str | Path) -> dict[str, int]:
    """Read ``trainLabels.csv``.  BIG2015 classes are 1-9; they become 0-8 here."""
    labels: dict[str, int] = {}
    with Path(path).open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or "Id" not in reader.fieldnames or "Class" not in reader.fieldnames:
            raise ValueError(f"{path}: expected columns Id and Class, found {reader.fieldnames}")
        for row in reader:
            identifier = row["Id"].strip().strip('"')
            family = int(row["Class"])
            if not 1 <= family <= 9:
                raise ValueError(f"{identifier}: class {family} outside the documented range 1-9")
            labels[identifier] = family - 1
    if not labels:
        raise ValueError(f"{path}: no rows")
    return labels


def stratified_selection(
    labels: dict[str, int], *, per_family: int, seed: int = 0
) -> dict[str, int]:
    """At most ``per_family`` samples from each family, chosen deterministically.

    Families smaller than the cap are taken whole, which is the point: the
    42-sample family survives at full strength instead of being sampled down to
    match a ratio it cannot support.
    """
    if per_family <= 0:
        raise ValueError(f"per_family must be positive, got {per_family}")
    rng = np.random.default_rng(seed)
    grouped: dict[int, list[str]] = {}
    for identifier, label in labels.items():
        grouped.setdefault(label, []).append(identifier)

    selection: dict[str, int] = {}
    for label in sorted(grouped):
        members = sorted(grouped[label])  # sort first so the seed fully determines the draw
        if len(members) > per_family:
            picked = rng.choice(len(members), size=per_family, replace=False)
            members = [members[int(index)] for index in sorted(picked)]
        for identifier in members:
            selection[identifier] = label
    return selection


def assign_split(
    content_hash: str, *, fractions: Sequence[float] = DEFAULT_SPLIT_FRACTIONS, salt: str = "v2"
) -> str:
    """Deterministic split from the content hash.

    Hashing the content rather than the name means the same bytes always land in
    the same split, whatever they are called -- the cheapest available guard
    against a duplicate straddling train and test.
    """
    if len(fractions) != 3 or abs(sum(fractions) - 1.0) > 1e-9:
        raise ValueError(f"fractions must be three values summing to 1, got {fractions}")
    digest = hashlib.sha256(f"{salt}|{content_hash}".encode()).hexdigest()
    position = int(digest[:16], 16) / float(1 << 64)
    if position < fractions[0]:
        return SPLIT_TRAIN
    if position < fractions[0] + fractions[1]:
        return SPLIT_VALIDATION
    return SPLIT_TEST


def content_hash(data: np.ndarray) -> str:
    return hashlib.sha256(data.tobytes()).hexdigest()


@dataclass
class ConversionReport:
    """What a conversion pass produced and what it skipped."""

    converted: list[CorpusEntry]
    duplicates: list[dict[str, str]]
    failures: list[dict[str, str]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "converted": [entry.to_dict() for entry in self.converted],
            "duplicates": self.duplicates,
            "failures": self.failures,
        }


def convert_dumps(
    dump_paths: Iterable[Path],
    labels: dict[str, int],
    output_directory: str | Path,
    *,
    width: int = raster.DEFAULT_WIDTH,
    fractions: Sequence[float] = DEFAULT_SPLIT_FRACTIONS,
    seen_hashes: dict[str, str] | None = None,
    min_bytes: int = 64 * 1024,
) -> ConversionReport:
    """Parse ``.bytes`` dumps into rasters, dropping duplicates and short samples.

    Short samples are dropped because a file smaller than a few tiles cannot
    support a 4 KB block search with a meaningful budget; keeping them would put
    samples in the corpus whose "1/16 budget" is one or two blocks.
    """
    output_directory = Path(output_directory)
    output_directory.mkdir(parents=True, exist_ok=True)
    registry = dict(seen_hashes or {})

    converted: list[CorpusEntry] = []
    duplicates: list[dict[str, str]] = []
    failures: list[dict[str, str]] = []

    for path in dump_paths:
        identifier = Path(path).stem
        label = labels.get(identifier)
        if label is None:
            failures.append({"sample_id": identifier, "reason": "no label"})
            continue
        try:
            dump = raster.parse_bytes_dump(path)
        except Exception as exc:  # noqa: BLE001 - the reason is recorded, not swallowed
            failures.append({"sample_id": identifier, "reason": f"{type(exc).__name__}: {exc}"})
            continue
        if dump.size < min_bytes:
            failures.append({"sample_id": identifier, "reason": f"only {dump.size} bytes"})
            continue

        digest = content_hash(dump.data)
        if digest in registry:
            duplicates.append({"sample_id": identifier, "duplicate_of": registry[digest]})
            continue
        registry[digest] = identifier

        image = raster.rasterize(dump, width=width)
        destination = output_directory / f"{identifier}.png"
        raster.save_raster(image, destination)
        converted.append(
            CorpusEntry(
                sample_id=identifier,
                label=int(label),
                split=assign_split(digest, fractions=fractions),
                byte_count=int(dump.size),
                valid_fraction=round(dump.valid_fraction, 6),
                content_sha256=digest,
                raster_path=destination.name,
            )
        )

    return ConversionReport(converted=converted, duplicates=duplicates, failures=failures)


def write_manifest(
    report: ConversionReport,
    path: str | Path,
    *,
    width: int = raster.DEFAULT_WIDTH,
    per_family: int | None = None,
    seed: int | None = None,
    extra: dict[str, Any] | None = None,
) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    entries = report.converted
    counts: dict[str, dict[str, int]] = {}
    for entry in entries:
        bucket = counts.setdefault(str(entry.label), {split: 0 for split in SPLITS})
        bucket[entry.split] += 1
    document = {
        "format": MANIFEST_FORMAT,
        "width": width,
        "per_family_cap": per_family,
        "selection_seed": seed,
        "sample_count": len(entries),
        "family_split_counts": counts,
        "duplicates_dropped": len(report.duplicates),
        "failures": report.failures,
        "duplicates": report.duplicates,
        "samples": [entry.to_dict() for entry in entries],
        **(extra or {}),
    }
    path.write_text(json.dumps(document, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def read_manifest(path: str | Path) -> tuple[list[CorpusEntry], dict[str, Any]]:
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    if document.get("format") != MANIFEST_FORMAT:
        raise ValueError(f"{path}: expected format {MANIFEST_FORMAT}, found {document.get('format')!r}")
    entries = [CorpusEntry(**row) for row in document["samples"]]
    return entries, document


def load_entry_bytes(entry: CorpusEntry, raster_directory: str | Path) -> tuple[np.ndarray, np.ndarray]:
    """Byte array and validity mask for one manifest entry."""
    image = raster.load_raster(Path(raster_directory) / entry.raster_path)
    return image.flat_bytes(), image.flat_valid()


def split_entries(entries: Sequence[CorpusEntry], split: str) -> list[CorpusEntry]:
    if split not in SPLITS:
        raise ValueError(f"unknown split {split!r}; expected one of {list(SPLITS)}")
    return [entry for entry in entries if entry.split == split]


def family_counts(entries: Sequence[CorpusEntry]) -> dict[int, int]:
    counts: dict[int, int] = {}
    for entry in entries:
        counts[entry.label] = counts.get(entry.label, 0) + 1
    return dict(sorted(counts.items()))


def stratified_subset(
    entries: Sequence[CorpusEntry], *, per_family: int, seed: int = 0
) -> list[CorpusEntry]:
    """A smaller, still-stratified draw -- used for the exhaustive-search subset."""
    rng = np.random.default_rng(seed)
    grouped: dict[int, list[CorpusEntry]] = {}
    for entry in entries:
        grouped.setdefault(entry.label, []).append(entry)
    picked: list[CorpusEntry] = []
    for label in sorted(grouped):
        members = sorted(grouped[label], key=lambda item: item.sample_id)
        if len(members) > per_family:
            indices = rng.choice(len(members), size=per_family, replace=False)
            members = [members[int(index)] for index in sorted(indices)]
        picked.extend(members)
    return picked
