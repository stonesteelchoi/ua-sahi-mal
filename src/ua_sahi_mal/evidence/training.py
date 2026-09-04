"""Training the three family classifiers on a stratified BIG2015 subset.

Everything runs on CPU.  The models are small on purpose: the study measures
*where a classifier looks*, and a stronger backbone would not change that
question, while a slower one would put the exhaustive occlusion sweep out of
reach.  What does matter, and is enforced here, is that A and B are trained
independently -- different architecture, different seed, different
representation -- because the whole cross-model argument collapses if they share
a spine.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from ua_sahi_mal.evidence import classifiers, corpus, features

DEFAULT_EPOCHS = 12
DEFAULT_BATCH = 8


@dataclass
class TrainingConfig:
    """Frozen before the first run; recorded next to every checkpoint."""

    epochs: int = DEFAULT_EPOCHS
    batch_size: int = DEFAULT_BATCH
    learning_rate: float = 1e-3
    weight_decay: float = 1e-4
    seed: int = 0
    max_tiles: int = 4
    thumbnail_size: int = features.DEFAULT_THUMBNAIL
    width: int = features.DEFAULT_WIDTH
    tile_rows: int = features.DEFAULT_TILE_ROWS

    def to_dict(self) -> dict[str, Any]:
        return {
            "epochs": self.epochs,
            "batch_size": self.batch_size,
            "learning_rate": self.learning_rate,
            "weight_decay": self.weight_decay,
            "seed": self.seed,
            "max_tiles": self.max_tiles,
            "thumbnail_size": self.thumbnail_size,
            "width": self.width,
            "tile_rows": self.tile_rows,
            "augmentation": "none -- horizontal flip and rotation destroy byte order",
        }


@dataclass
class TrainingReport:
    model: str
    epochs: list[dict[str, float]] = field(default_factory=list)
    validation: dict[str, float] = field(default_factory=dict)
    seconds: float = 0.0
    config: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "epochs": self.epochs,
            "validation": self.validation,
            "seconds": round(self.seconds, 2),
            "config": self.config,
        }


class SampleStore:
    """Reads sample bytes from the raster directory, with a small LRU-ish cache.

    Decoding a 1.4 MB PNG costs about 20 ms; over twelve epochs that is the
    dominant cost of training these small networks, so recently used samples are
    kept.  The cache is bounded by byte count, not sample count, because sample
    sizes span two orders of magnitude.
    """

    def __init__(self, raster_directory: str | Path, *, cache_bytes: int = 512 * 1024 * 1024) -> None:
        self.directory = Path(raster_directory)
        self.cache_bytes = cache_bytes
        self._cache: dict[str, np.ndarray] = {}
        self._order: list[str] = []
        self._held = 0

    def get(self, entry: corpus.CorpusEntry) -> np.ndarray:
        cached = self._cache.get(entry.sample_id)
        if cached is not None:
            return cached
        data, _ = corpus.load_entry_bytes(entry, self.directory)
        self._cache[entry.sample_id] = data
        self._order.append(entry.sample_id)
        self._held += data.nbytes
        while self._held > self.cache_bytes and len(self._order) > 1:
            evicted = self._order.pop(0)
            self._held -= self._cache.pop(evicted).nbytes
        return data


def _batches(count: int, batch_size: int, rng: np.random.Generator) -> list[np.ndarray]:
    order = rng.permutation(count)
    return [order[start : start + batch_size] for start in range(0, count, batch_size)]


def train_text_classifier(
    entries: Sequence[corpus.CorpusEntry],
    store: SampleStore,
    *,
    class_count: int,
    config: TrainingConfig,
    validation: Sequence[corpus.CorpusEntry] = (),
) -> tuple[classifiers.TextClassifier, TrainingReport]:
    """Fit C_text on histogram + hashed-bigram features."""
    started = time.time()
    matrix = np.stack([features.text_features(store.get(entry)) for entry in entries])
    labels = np.asarray([entry.label for entry in entries], dtype=np.int64)
    model = classifiers.TextClassifier(class_count=class_count).fit(
        matrix, labels, seed=config.seed + 3, weight_decay=config.weight_decay
    )

    report = TrainingReport(model=classifiers.MODEL_TEXT, config=config.to_dict())
    report.seconds = time.time() - started
    if validation:
        rows = [model.log_probabilities(store.get(entry)) for entry in validation]
        truth = [entry.label for entry in validation]
        report.validation = {
            "accuracy": classifiers.accuracy(rows, truth),
            "macro_f1": classifiers.macro_f1(rows, truth, class_count),
            "mean_nll": float(np.mean([-row[label] for row, label in zip(rows, truth, strict=False)])),
            "n": len(truth),
        }
    report.epochs = [{"loss": model.training.get("final_loss", float("nan"))}]
    return model, report


def train_thumbnail_classifier(
    entries: Sequence[corpus.CorpusEntry],
    store: SampleStore,
    *,
    class_count: int,
    config: TrainingConfig,
    validation: Sequence[corpus.CorpusEntry] = (),
) -> tuple[classifiers.ThumbnailClassifier, TrainingReport]:
    """Train B on whole-file thumbnails."""
    torch = classifiers._require_torch()
    from torch import nn

    started = time.time()
    model = classifiers.ThumbnailClassifier(
        class_count=class_count, seed=config.seed + 1, size=config.thumbnail_size, width=config.width
    )
    module = model.module
    optimizer = torch.optim.AdamW(
        module.parameters(), lr=config.learning_rate, weight_decay=config.weight_decay
    )
    weights = _class_weights([entry.label for entry in entries], class_count)
    criterion = nn.CrossEntropyLoss(weight=torch.tensor(weights, dtype=torch.float32))
    rng = np.random.default_rng(config.seed + 1)

    images = np.stack(
        [features.thumbnail(store.get(entry), width=config.width, size=config.thumbnail_size) for entry in entries]
    )
    labels = np.asarray([entry.label for entry in entries], dtype=np.int64)

    report = TrainingReport(model=classifiers.MODEL_THUMBNAIL, config=config.to_dict())
    module.train()
    for epoch in range(config.epochs):
        total, seen = 0.0, 0
        for indices in _batches(len(entries), max(config.batch_size * 4, 16), rng):
            batch = torch.from_numpy(images[indices]).unsqueeze(1)
            target = torch.from_numpy(labels[indices])
            optimizer.zero_grad()
            loss = criterion(module(batch), target)
            loss.backward()
            optimizer.step()
            total += float(loss.item()) * len(indices)
            seen += len(indices)
        report.epochs.append({"epoch": epoch, "loss": total / max(seen, 1)})
        print(f"  [{report.model}] epoch {epoch} loss {total / max(seen, 1):.4f}", flush=True)
    module.eval()

    report.seconds = time.time() - started
    if validation:
        rows = [model.log_probabilities(store.get(entry)) for entry in validation]
        truth = [entry.label for entry in validation]
        report.validation = {
            "accuracy": classifiers.accuracy(rows, truth),
            "macro_f1": classifiers.macro_f1(rows, truth, class_count),
            "mean_nll": float(np.mean([-row[label] for row, label in zip(rows, truth, strict=False)])),
            "n": len(truth),
        }
    model.training = report.to_dict()
    return model, report


def train_tiled_classifier(
    entries: Sequence[corpus.CorpusEntry],
    store: SampleStore,
    *,
    class_count: int,
    config: TrainingConfig,
    validation: Sequence[corpus.CorpusEntry] = (),
) -> tuple[classifiers.TiledClassifier, TrainingReport]:
    """Train A on native-resolution tiles, pooling over each sample's tiles.

    One optimizer step per sample rather than per fixed-size batch, because tile
    counts differ between samples and padding them to a common count would feed
    the pooling layer tiles that are not there.
    """
    torch = classifiers._require_torch()
    from torch import nn

    started = time.time()
    model = classifiers.TiledClassifier(
        class_count=class_count,
        seed=config.seed,
        tile_rows=config.tile_rows,
        width=config.width,
        max_tiles=config.max_tiles,
    )
    module = model.module
    optimizer = torch.optim.AdamW(
        module.parameters(), lr=config.learning_rate, weight_decay=config.weight_decay
    )
    weights = _class_weights([entry.label for entry in entries], class_count)
    # Model A contributes one sample per forward pass.  With the default mean
    # reduction PyTorch divides a one-element batch by that sample's class
    # weight, cancelling the weighting.  Sum reduction preserves the intended
    # inverse-frequency multiplier while gradients are accumulated below.
    criterion = nn.CrossEntropyLoss(
        weight=torch.tensor(weights, dtype=torch.float32), reduction="sum"
    )
    rng = np.random.default_rng(config.seed)

    report = TrainingReport(model=classifiers.MODEL_TILED, config=config.to_dict())
    module.train()
    for epoch in range(config.epochs):
        total, seen = 0.0, 0
        optimizer.zero_grad()
        for step, index in enumerate(rng.permutation(len(entries)), start=1):
            entry = entries[int(index)]
            tiles, _ = model._select_tiles(store.get(entry))
            batch = torch.from_numpy(tiles.astype(np.float32) / 255.0).unsqueeze(1)
            logits = module(batch).unsqueeze(0)
            loss = criterion(logits, torch.tensor([entry.label], dtype=torch.long))
            (loss / config.batch_size).backward()
            total += float(loss.item())
            seen += 1
            if step % config.batch_size == 0:
                # Clipping is not decoration here: one sample can contribute a
                # very large gradient when its tiles disagree, and a single such
                # step is enough to put the pooled head into a bad basin.
                torch.nn.utils.clip_grad_norm_(module.parameters(), 1.0)
                optimizer.step()
                optimizer.zero_grad()
        optimizer.step()
        optimizer.zero_grad()
        report.epochs.append({"epoch": epoch, "loss": total / max(seen, 1)})
        print(f"  [{report.model}] epoch {epoch} loss {total / max(seen, 1):.4f}", flush=True)
    module.eval()

    report.seconds = time.time() - started
    if validation:
        rows = [model.log_probabilities(store.get(entry)) for entry in validation]
        truth = [entry.label for entry in validation]
        report.validation = {
            "accuracy": classifiers.accuracy(rows, truth),
            "macro_f1": classifiers.macro_f1(rows, truth, class_count),
            "mean_nll": float(np.mean([-row[label] for row, label in zip(rows, truth, strict=False)])),
            "n": len(truth),
        }
    model.training = report.to_dict()
    return model, report


def _class_weights(labels: Sequence[int], class_count: int) -> np.ndarray:
    """Inverse-frequency weights so the 42-sample family is not simply ignored."""
    counts = np.bincount(np.asarray(labels, dtype=np.int64), minlength=class_count).astype(np.float64)
    total = counts.sum()
    with np.errstate(divide="ignore", invalid="ignore"):
        weights = np.where(counts > 0, total / (class_count * np.maximum(counts, 1)), 0.0)
    return weights.astype(np.float32)


def train_all(
    manifest_path: str | Path,
    raster_directory: str | Path,
    output_directory: str | Path,
    *,
    class_count: int = 9,
    config: TrainingConfig | None = None,
    skip_torch: bool = False,
) -> dict[str, Any]:
    """Train whichever of A, B, C_text this environment can, and record all of it."""
    config = config or TrainingConfig()
    entries, _ = corpus.read_manifest(manifest_path)
    train = corpus.split_entries(entries, corpus.SPLIT_TRAIN)
    validation = corpus.split_entries(entries, corpus.SPLIT_VALIDATION)
    if not train:
        raise ValueError(f"{manifest_path}: the train split is empty")

    output_directory = Path(output_directory)
    output_directory.mkdir(parents=True, exist_ok=True)
    store = SampleStore(raster_directory)

    reports: dict[str, Any] = {}
    text_model, text_report = train_text_classifier(
        train, store, class_count=class_count, config=config, validation=validation
    )
    text_model.save(output_directory / "classifier_text.npz")
    reports[classifiers.MODEL_TEXT] = text_report.to_dict()

    if not skip_torch:
        try:
            classifiers._require_torch()
        except classifiers.TorchUnavailable as exc:
            reports["torch"] = {"available": False, "reason": str(exc)}
        else:
            tiled_model, tiled_report = train_tiled_classifier(
                train, store, class_count=class_count, config=config, validation=validation
            )
            tiled_model.save(output_directory / "classifier_tiled.pt")
            reports[classifiers.MODEL_TILED] = tiled_report.to_dict()

            thumbnail_model, thumbnail_report = train_thumbnail_classifier(
                train, store, class_count=class_count, config=config, validation=validation
            )
            thumbnail_model.save(output_directory / "classifier_thumbnail.pt")
            reports[classifiers.MODEL_THUMBNAIL] = thumbnail_report.to_dict()

    summary = {
        "format": "evidence-training-1",
        "manifest": str(manifest_path),
        "class_count": class_count,
        "train_samples": len(train),
        "validation_samples": len(validation),
        "family_counts_train": {str(k): v for k, v in corpus.family_counts(train).items()},
        "config": config.to_dict(),
        "models": reports,
    }
    (output_directory / "training_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return summary
