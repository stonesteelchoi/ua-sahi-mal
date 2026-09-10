"""E2 v3 training on SOREL tiles (torch, lazy) with the TiledNet recipe, GPU-capable.

Recipe (mirrors ``evidence.training.train_tiled_classifier`` so results are
comparable to the BIG2015 track, with the device handling that code lacked):
one sample per forward (tile counts vary; no padding of bag size), gradient
accumulation over ``accumulate`` samples, AdamW, inverse-frequency class weights
with ``reduction="sum"`` (so a one-sample batch is not divided by its own weight),
gradient clipping at 1.0, no augmentation (byte order is meaning).

SOREL specifics: tiles come from :class:`SorelTileStore` (in memory, never on
disk); a random subset of at most ``max_train_tiles`` tiles per sample per step
bounds VRAM on the 8 GB operator GPU — *uniformly random*, so no positional bias
enters training; padded regions of the ragged last tile stay zero.

Supervision is the dominant behavior tag; the silver evidence is never seen.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Sequence

import numpy as np

from ua_sahi_mal.evidence.classifiers import accuracy, macro_f1
from ua_sahi_mal.sorel.e2_dataset import LabeledSample, SorelTileStore
from ua_sahi_mal.sorel.e2_models import build_model, require_torch, resolve_device, tiles_to_tensor


@dataclass
class TrainConfig:
    """Frozen before training; recorded next to every checkpoint (SHA-free)."""

    pooling: str = "meanmax"           # meanmax | attention
    epochs: int = 8
    accumulate: int = 16               # samples per optimizer step
    learning_rate: float = 1e-3
    weight_decay: float = 1e-4
    max_train_tiles: int = 64          # random subset per sample per step (VRAM bound)
    seed: int = 20260909
    device: str = "auto"
    eval_chunk: int = 256              # tiles per forward at evaluation

    def to_dict(self) -> dict[str, object]:
        return {**asdict(self), "augmentation": "none -- byte order is meaning",
                "positional_input": False, "supervision": "dominant_behavior_tag"}


@dataclass
class TrainReport:
    pooling: str
    class_count: int
    epochs: list[dict[str, float]] = field(default_factory=list)
    validation: dict[str, float] = field(default_factory=dict)
    sanity: dict[str, object] = field(default_factory=dict)
    seconds: float = 0.0
    device: str = ""
    config: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def class_weights(labels: Sequence[int], class_count: int) -> np.ndarray:
    """Inverse-frequency weights (same formula as the BIG2015 track)."""
    counts = np.bincount(np.asarray(labels, dtype=np.int64), minlength=class_count).astype(np.float64)
    total = counts.sum()
    with np.errstate(divide="ignore", invalid="ignore"):
        weights = np.where(counts > 0, total / (class_count * np.maximum(counts, 1)), 0.0)
    return weights.astype(np.float32)


def _subsample_tiles(tiles: np.ndarray, limit: int, rng: np.random.Generator) -> np.ndarray:
    """Uniformly random tile subset (positionally unbiased); keeps original order."""
    n = tiles.shape[0]
    if limit <= 0 or n <= limit:
        return tiles
    keep = np.sort(rng.choice(n, size=limit, replace=False))
    return tiles[keep]


def train_model(samples: Sequence[LabeledSample], store: SorelTileStore, *, class_count: int,
                config: TrainConfig, validation: Sequence[LabeledSample] = (),
                log=print):
    """Train one model; returns ``(model, TrainReport)``. ``samples`` must all have labels."""
    torch = require_torch()
    from torch import nn

    if any(s.label is None for s in samples):
        raise ValueError("training samples must all be labelled (filter no-tag samples first)")
    device = resolve_device(config.device)
    started = time.time()
    model = build_model(class_count, pooling=config.pooling, seed=config.seed).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=config.learning_rate, weight_decay=config.weight_decay)
    weights = torch.tensor(class_weights([s.label for s in samples], class_count), dtype=torch.float32, device=device)
    criterion = nn.CrossEntropyLoss(weight=weights, reduction="sum")
    rng = np.random.default_rng(config.seed)

    report = TrainReport(pooling=config.pooling, class_count=class_count, config=config.to_dict(), device=str(device))
    missing: set[str] = set()
    model.train()
    for epoch in range(config.epochs):
        total, seen = 0.0, 0
        optimizer.zero_grad()
        for step, index in enumerate(rng.permutation(len(samples)), start=1):
            sample = samples[int(index)]
            try:
                bag = store.get(sample.sorel_original_sha256)
            except FileNotFoundError:
                missing.add(sample.sorel_original_sha256)   # never crash a run on one absent artefact
                continue
            tiles = _subsample_tiles(bag.tiles, config.max_train_tiles, rng)
            logits = model(tiles_to_tensor(tiles, device)).unsqueeze(0)
            target = torch.tensor([sample.label], dtype=torch.long, device=device)
            loss = criterion(logits, target)
            (loss / config.accumulate).backward()
            total += float(loss.item())
            seen += 1
            if step % config.accumulate == 0:
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                optimizer.step()
                optimizer.zero_grad()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()
        optimizer.zero_grad()
        mean_loss = total / max(seen, 1)
        report.epochs.append({"epoch": epoch, "loss": mean_loss, "samples": seen})
        log(f"  [{config.pooling}] epoch {epoch} loss {mean_loss:.4f} ({seen} samples)")
    model.eval()
    report.seconds = time.time() - started
    if missing:
        report.config["skipped_missing_artefacts"] = len(missing)   # count only, SHA-free
        log(f"  WARNING: {len(missing)} training artefact(s) missing on disk were skipped")

    if validation:
        report.validation = evaluate(model, validation, store, device=device, class_count=class_count,
                                     chunk=config.eval_chunk)
        report.sanity = sanity_gate(report.validation, [s.label for s in validation], class_count)
    return model, report


def log_probabilities(model, tiles: np.ndarray, device, *, chunk: int = 256) -> np.ndarray:
    """Log-probabilities for one file using ALL its tiles (chunked encode, no grad)."""
    torch = require_torch()
    from ua_sahi_mal.sorel.e2_models import encode_in_chunks

    with torch.no_grad():
        embeddings = encode_in_chunks(model, tiles, device, chunk=chunk)
        logits = model.classify_embeddings(embeddings)
        return torch.log_softmax(logits, dim=0).cpu().numpy().astype(np.float64)


def evaluate(model, samples: Sequence[LabeledSample], store: SorelTileStore, *, device, class_count: int,
             chunk: int = 256) -> dict[str, float]:
    rows, truth, missing = [], [], 0
    for s in samples:
        if s.label is None:
            continue
        try:
            bag = store.get(s.sorel_original_sha256)
        except FileNotFoundError:
            missing += 1
            continue
        rows.append(log_probabilities(model, bag.tiles, device, chunk=chunk))
        truth.append(int(s.label))
    if not rows:
        return {"n": 0, "skipped_missing": missing}
    return {
        "accuracy": accuracy(rows, truth),
        "macro_f1": macro_f1(rows, truth, class_count),
        "mean_nll": float(np.mean([-row[label] for row, label in zip(rows, truth, strict=True)])),
        "n": len(truth),
        "skipped_missing": missing,
    }


def majority_baseline(labels: Sequence[int], class_count: int) -> dict[str, float]:
    """Accuracy / macro-F1 of always predicting the most frequent class."""
    array = np.asarray(list(labels), dtype=np.int64)
    if array.size == 0:
        return {"accuracy": float("nan"), "macro_f1": float("nan"), "majority_class": -1}
    counts = np.bincount(array, minlength=class_count)
    majority = int(counts.argmax())
    rows = []
    for _ in array:
        row = np.full(class_count, -30.0)
        row[majority] = 0.0
        rows.append(row)
    return {"accuracy": accuracy(rows, array.tolist()), "macro_f1": macro_f1(rows, array.tolist(), class_count),
            "majority_class": majority}


def sanity_gate(validation: dict[str, float], val_labels: Sequence[int], class_count: int, *,
                accuracy_margin_pt: float = 10.0, f1_ratio: float = 1.5) -> dict[str, object]:
    """E2_prereg_v3 model sanity gate: val accuracy >= majority + margin AND
    macro-F1 >= ratio x majority macro-F1. Attribution is only evaluated if it passes."""
    base = majority_baseline([int(x) for x in val_labels], class_count)
    acc_ok = validation.get("accuracy", 0.0) >= base["accuracy"] + accuracy_margin_pt / 100.0
    f1_ok = validation.get("macro_f1", 0.0) >= f1_ratio * base["macro_f1"] if base["macro_f1"] > 0 else \
        validation.get("macro_f1", 0.0) > 0.0
    return {"pass": bool(acc_ok and f1_ok), "accuracy_ok": bool(acc_ok), "macro_f1_ok": bool(f1_ok),
            "majority_baseline": base, "thresholds": {"accuracy_margin_pt": accuracy_margin_pt, "f1_ratio": f1_ratio}}
