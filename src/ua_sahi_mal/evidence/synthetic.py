"""A control set whose answer is known, used to calibrate the protocol (D1).

On real samples there is no annotation to check the found ranges against.  So
the protocol is first pointed at a set where the answer was planted: a host
sample from family X carrying a range grafted from a *different* family Y at a
recorded offset.  Asked for the evidence of family Y, the protocol should return
that range and nothing else.  Byte-IoU against the planted range is criterion
D1, and a protocol that cannot clear it on a known answer says nothing about an
unknown one.

The matched hard negative is what keeps that from being trivial.  For every
positive there is a sample with the *same host, same offset, same length*, but
the graft taken from the host's own family.  Both have a seam; only one has
foreign content.  A protocol that scores the seam rather than the content puts
both at the same rank, and the specificity number will say so.  The seam is
constrained further: donors whose entropy at the join differs from the host's by
more than 0.3 bit are rejected outright, so the two sides do not advertise
themselves.

Safety
------
Everything here happens on byte arrays that came from BIG2015 ``.bytes`` dumps,
which the dataset ships with the PE header stripped and are not executable.  No
function in this module produces, or can produce, a runnable file: there is no
header synthesis, no relocation fixing, no entry point.  The output is data for
a classifier, and it is written as PNG rasters and NPZ arrays only.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np

from ua_sahi_mal.evidence import occlusion, raster

DEFAULT_BLOCK_BYTES = 4096
MAX_SEAM_ENTROPY_DELTA = 0.3
"""Bits per byte.  Above this, the join itself is a detectable feature."""

SEAM_WINDOW = 2048
"""Bytes on each side of a join used to compare entropy."""

POSITIVE = "cross-family"
NEGATIVE = "same-family"


class DonorRejected(ValueError):
    """No donor met the seam constraint, so no sample was built."""


@dataclass(frozen=True)
class SyntheticSample:
    """A host with a planted range, and the record of what was planted."""

    sample_id: str
    data: np.ndarray
    host_id: str
    host_label: int
    donor_id: str
    donor_label: int
    query_label: int
    injection: tuple[int, int]
    kind: str
    seam_entropy_delta: float

    @property
    def is_positive(self) -> bool:
        return self.kind == POSITIVE

    def truth_ranges(self) -> np.ndarray:
        return np.asarray([self.injection], dtype=np.int64)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_id": self.sample_id,
            "host_id": self.host_id,
            "host_label": self.host_label,
            "donor_id": self.donor_id,
            "donor_label": self.donor_label,
            "query_label": self.query_label,
            "injection_start": int(self.injection[0]),
            "injection_end": int(self.injection[1]),
            "injection_bytes": int(self.injection[1] - self.injection[0]),
            "kind": self.kind,
            "is_positive": self.is_positive,
            "seam_entropy_delta": self.seam_entropy_delta,
            "byte_count": int(self.data.size),
        }


def _window_entropy(data: np.ndarray, start: int, end: int) -> float:
    segment = data[max(start, 0) : min(end, data.size)]
    if segment.size == 0:
        return 0.0
    counts = np.bincount(segment, minlength=256).astype(np.float64)
    probabilities = counts / segment.size
    nonzero = probabilities[probabilities > 0]
    return float(-(nonzero * np.log2(nonzero)).sum())


def seam_entropy_delta(host: np.ndarray, graft: np.ndarray, start: int) -> float:
    """Largest entropy mismatch across the two joins the graft creates."""
    end = start + graft.size
    before = _window_entropy(host, start - SEAM_WINDOW, start)
    after = _window_entropy(host, end, end + SEAM_WINDOW)
    graft_head = _window_entropy(graft, 0, SEAM_WINDOW)
    graft_tail = _window_entropy(graft, max(graft.size - SEAM_WINDOW, 0), graft.size)
    deltas = []
    if start > 0:
        deltas.append(abs(before - graft_head))
    if end < host.size:
        deltas.append(abs(after - graft_tail))
    return max(deltas) if deltas else 0.0


def _identifier(host_id: str, donor_id: str, start: int, length: int, kind: str) -> str:
    digest = hashlib.sha256(f"{host_id}|{donor_id}|{start}|{length}|{kind}".encode()).hexdigest()
    return f"syn_{kind[:4]}_{digest[:12]}"


def graft(
    host: np.ndarray,
    donor: np.ndarray,
    *,
    start: int,
    length: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Replace ``host[start:start+length]`` with ``length`` bytes taken from ``donor``.

    Replacement, not insertion: the host keeps its length, so a positive and its
    matched negative are byte-for-byte the same size and the same shape.  Only
    the content of one range differs.
    """
    if length <= 0:
        raise ValueError(f"length must be positive, got {length}")
    if start < 0 or start + length > host.size:
        raise ValueError(f"graft [{start}, {start + length}) does not fit in {host.size} bytes")
    if donor.size < length:
        raise ValueError(f"donor has {donor.size} bytes, need {length}")
    donor_offset = (donor.size - length) // 2
    piece = donor[donor_offset : donor_offset + length].copy()
    out = host.copy()
    out[start : start + length] = piece
    return out, piece


def build_sample(
    *,
    host: np.ndarray,
    host_id: str,
    host_label: int,
    donor: np.ndarray,
    donor_id: str,
    donor_label: int,
    start: int,
    length: int,
    kind: str,
    query_label: int,
    max_seam_delta: float = MAX_SEAM_ENTROPY_DELTA,
) -> SyntheticSample:
    """Graft one range and refuse the result if the seam gives it away."""
    _, piece = graft(host, donor, start=start, length=length)
    delta = seam_entropy_delta(host, piece, start)
    if delta > max_seam_delta:
        raise DonorRejected(
            f"seam entropy delta {delta:.3f} bit exceeds {max_seam_delta} bit "
            f"(host={host_id}, donor={donor_id})"
        )
    data, _ = graft(host, donor, start=start, length=length)
    return SyntheticSample(
        sample_id=_identifier(host_id, donor_id, start, length, kind),
        data=data,
        host_id=host_id,
        host_label=host_label,
        donor_id=donor_id,
        donor_label=donor_label,
        query_label=query_label,
        injection=(int(start), int(start + length)),
        kind=kind,
        seam_entropy_delta=delta,
    )


@dataclass
class DonorPool:
    """Byte arrays available as grafts, indexed by family."""

    by_label: dict[int, list[tuple[str, np.ndarray]]]

    @classmethod
    def from_items(cls, items: Iterable[tuple[str, int, np.ndarray]]) -> DonorPool:
        pool: dict[int, list[tuple[str, np.ndarray]]] = {}
        for identifier, label, data in items:
            pool.setdefault(int(label), []).append((identifier, data))
        return cls(by_label=pool)

    def labels(self) -> list[int]:
        return sorted(self.by_label)

    def candidates(self, label: int, minimum_bytes: int) -> list[tuple[str, np.ndarray]]:
        return [item for item in self.by_label.get(label, []) if item[1].size >= minimum_bytes]


def build_pair(
    *,
    host: np.ndarray,
    host_id: str,
    host_label: int,
    pool: DonorPool,
    rng: np.random.Generator,
    block_bytes: int = DEFAULT_BLOCK_BYTES,
    blocks: int = 4,
    align_to_block: bool = True,
    max_attempts: int = 32,
    max_seam_delta: float = MAX_SEAM_ENTROPY_DELTA,
) -> tuple[SyntheticSample, SyntheticSample]:
    """One cross-family positive and its same-host, same-geometry hard negative.

    Both are built before either is returned, so a run never contains a positive
    whose negative was rejected -- an unmatched pair would bias specificity.
    """
    length = block_bytes * blocks
    if host.size < length * 3:
        raise DonorRejected(f"host {host_id} is too short ({host.size} bytes) for a {length}-byte graft")

    foreign_labels = [label for label in pool.labels() if label != host_label]
    if not foreign_labels:
        raise DonorRejected("donor pool has no family other than the host's")

    limit = host.size - length
    for _ in range(max_attempts):
        start = int(rng.integers(0, limit + 1))
        if align_to_block:
            start = (start // block_bytes) * block_bytes
            start = min(start, (limit // block_bytes) * block_bytes)

        donor_label = int(rng.choice(foreign_labels))
        foreign = pool.candidates(donor_label, length)
        native = [item for item in pool.candidates(host_label, length) if item[0] != host_id]
        if not foreign or not native:
            continue

        foreign_id, foreign_data = foreign[int(rng.integers(0, len(foreign)))]
        native_id, native_data = native[int(rng.integers(0, len(native)))]

        try:
            positive = build_sample(
                host=host,
                host_id=host_id,
                host_label=host_label,
                donor=foreign_data,
                donor_id=foreign_id,
                donor_label=donor_label,
                start=start,
                length=length,
                kind=POSITIVE,
                query_label=donor_label,
                max_seam_delta=max_seam_delta,
            )
            negative = build_sample(
                host=host,
                host_id=host_id,
                host_label=host_label,
                donor=native_data,
                donor_id=native_id,
                donor_label=host_label,
                start=start,
                length=length,
                kind=NEGATIVE,
                query_label=donor_label,
                max_seam_delta=max_seam_delta,
            )
        except DonorRejected:
            continue
        return positive, negative

    raise DonorRejected(
        f"no donor pair for host {host_id} met the {max_seam_delta} bit seam constraint "
        f"in {max_attempts} attempts"
    )


def build_control_set(
    hosts: Sequence[tuple[str, int, np.ndarray]],
    pool: DonorPool,
    *,
    seed: int = 0,
    block_bytes: int = DEFAULT_BLOCK_BYTES,
    blocks: int = 4,
    align_to_block: bool = True,
    max_pairs: int | None = None,
) -> tuple[list[SyntheticSample], list[dict[str, Any]]]:
    """Build as many matched pairs as the hosts and seam constraint allow.

    Returns the samples and a rejection log.  The log is part of the result, not
    debug output: a control set whose hosts were silently filtered is a biased
    control set, and the reader needs to see how many were dropped and why.
    """
    rng = np.random.default_rng(seed)
    samples: list[SyntheticSample] = []
    rejections: list[dict[str, Any]] = []
    for host_id, host_label, host_data in hosts:
        if max_pairs is not None and len(samples) >= 2 * max_pairs:
            break
        try:
            positive, negative = build_pair(
                host=host_data,
                host_id=host_id,
                host_label=int(host_label),
                pool=pool,
                rng=rng,
                block_bytes=block_bytes,
                blocks=blocks,
                align_to_block=align_to_block,
            )
        except DonorRejected as exc:
            rejections.append({"host_id": host_id, "reason": str(exc)})
            continue
        samples.extend([positive, negative])
    return samples, rejections


def save_control_set(
    samples: Sequence[SyntheticSample],
    rejections: Sequence[dict[str, Any]],
    directory: str | Path,
    *,
    width: int = raster.DEFAULT_WIDTH,
    save_rasters: bool = True,
) -> Path:
    """Write the control set: one NPZ of bytes per sample, plus a manifest."""
    directory = Path(directory)
    (directory / "samples").mkdir(parents=True, exist_ok=True)
    manifest: list[dict[str, Any]] = []
    for sample in samples:
        payload = directory / "samples" / f"{sample.sample_id}.npz"
        np.savez_compressed(payload, data=sample.data)
        entry = sample.to_dict()
        entry["path"] = str(payload.relative_to(directory))
        if save_rasters:
            image = raster.rasterize(
                raster.ByteDump(
                    data=sample.data,
                    valid=np.ones(sample.data.size, dtype=bool),
                    base_address=0,
                    source_name=sample.sample_id,
                ),
                width=width,
            )
            png = directory / "samples" / f"{sample.sample_id}.png"
            raster.save_raster(image, png)
            entry["raster"] = str(png.relative_to(directory))
        manifest.append(entry)

    document = {
        "format": "evidence-synthetic-1",
        "count": len(manifest),
        "positives": sum(1 for entry in manifest if entry["is_positive"]),
        "negatives": sum(1 for entry in manifest if not entry["is_positive"]),
        "max_seam_entropy_delta": MAX_SEAM_ENTROPY_DELTA,
        "seam_window_bytes": SEAM_WINDOW,
        "rejections": list(rejections),
        "samples": manifest,
        "safety": (
            "Byte arrays only. Sources are BIG2015 .bytes dumps, which ship with the PE "
            "header removed and are not executable; nothing here synthesizes a header, "
            "fixes relocations, or produces a runnable file."
        ),
    }
    path = directory / "manifest.json"
    path.write_text(json.dumps(document, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def load_control_set(directory: str | Path) -> tuple[list[SyntheticSample], dict[str, Any]]:
    directory = Path(directory)
    document = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    samples: list[SyntheticSample] = []
    for entry in document["samples"]:
        with np.load(directory / entry["path"]) as archive:
            data = archive["data"]
        samples.append(
            SyntheticSample(
                sample_id=entry["sample_id"],
                data=data,
                host_id=entry["host_id"],
                host_label=int(entry["host_label"]),
                donor_id=entry["donor_id"],
                donor_label=int(entry["donor_label"]),
                query_label=int(entry["query_label"]),
                injection=(int(entry["injection_start"]), int(entry["injection_end"])),
                kind=entry["kind"],
                seam_entropy_delta=float(entry["seam_entropy_delta"]),
            )
        )
    return samples, document


def verify_fill_choice(
    samples: Sequence[SyntheticSample], *, seed: int = 0, block_bytes: int = DEFAULT_BLOCK_BYTES
) -> list[dict[str, Any]]:
    """Re-run the fill-value entropy check on this data instead of trusting a stored number."""
    rng = np.random.default_rng(seed)
    report: list[dict[str, Any]] = []
    for sample in samples:
        for name in occlusion.ROBUSTNESS_FILLS:
            plan = occlusion.make_fill_plan(name, sample.data)
            row = occlusion.fill_is_in_distribution(sample.data, plan, rng, block_bytes=block_bytes)
            row["sample_id"] = sample.sample_id
            report.append(row)
    return report
