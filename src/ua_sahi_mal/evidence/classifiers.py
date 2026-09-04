"""The three family classifiers the evidence protocol needs.

Why three, and why they must not share a spine (research plan v2 §2): a range
found with one model and scored with the same model measures how well the
protocol imitates that model, not what the data contains.  So the reported
necessity comes from a model that never took part in the search.

============  ==========================  ==================================
model         representation              role
============  ==========================  ==================================
A  ``tiled``  512x512 byte tiles          search -- finds candidate ranges
B  ``thumb``  256x256 whole-file image    primary metric (cross-model)
C  ``text``   histogram + hashed bigrams  cross-representation, sees no image
============  ==========================  ==================================

A and B need PyTorch.  C needs only NumPy, so a repository check-out with no
deep-learning stack can still run the cross-representation half of the
protocol.  Import failures are raised where the model is constructed, not at
module import, so ``import ua_sahi_mal.evidence`` never requires torch.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, Sequence

import numpy as np

from ua_sahi_mal.evidence import features

MODEL_TILED = "tiled"
MODEL_THUMBNAIL = "thumbnail"
MODEL_TEXT = "text"

_EPSILON = 1e-12


class TorchUnavailable(RuntimeError):
    """Raised when a torch-backed model is constructed without torch installed."""


def _require_torch():  # pragma: no cover - exercised only where torch is absent
    try:
        import torch
    except ImportError as exc:
        raise TorchUnavailable(
            "PyTorch is required for the tiled and thumbnail classifiers. "
            "Install it (see docker/Dockerfile) or use the text classifier alone."
        ) from exc
    return torch


class FamilyClassifier(Protocol):
    """Anything that can name a family and say how sure it is."""

    name: str
    class_count: int

    def log_probabilities(self, data: np.ndarray, valid: np.ndarray | None = None) -> np.ndarray:
        """Natural-log class probabilities, shape ``(class_count,)``."""

    def negative_log_likelihood(
        self, data: np.ndarray, label: int, valid: np.ndarray | None = None
    ) -> float:
        """``-log p(label | data)``, the quantity every occlusion moves."""


def _nll_from_log_probabilities(log_probabilities: np.ndarray, label: int) -> float:
    if not 0 <= label < log_probabilities.size:
        raise IndexError(f"label {label} out of range for {log_probabilities.size} classes")
    return float(-log_probabilities[label])


# ---------------------------------------------------------------------------
# C_text -- NumPy only
# ---------------------------------------------------------------------------


@dataclass
class TextClassifier:
    """Multinomial logistic regression on histogram + hashed-bigram features.

    Trained with plain gradient descent so the whole model is a pair of NumPy
    arrays: no framework, no nondeterminism, and it round-trips through JSON.
    """

    class_count: int
    weights: np.ndarray | None = None  # (feature_dim, class_count)
    bias: np.ndarray | None = None  # (class_count,)
    feature_dim: int = features.TEXT_FEATURE_DIM
    name: str = MODEL_TEXT
    training: dict[str, Any] = field(default_factory=dict)

    def fit(
        self,
        feature_matrix: np.ndarray,
        labels: np.ndarray,
        *,
        epochs: int = 400,
        learning_rate: float = 2.0,
        weight_decay: float = 1e-4,
        seed: int = 0,
    ) -> TextClassifier:
        matrix = np.asarray(feature_matrix, dtype=np.float64)
        target = np.asarray(labels, dtype=np.int64)
        if matrix.ndim != 2:
            raise ValueError(f"feature_matrix must be 2-D, got shape {matrix.shape}")
        if matrix.shape[0] != target.size:
            raise ValueError(f"{matrix.shape[0]} feature rows but {target.size} labels")
        if target.size == 0:
            raise ValueError("cannot fit on an empty training set")

        rng = np.random.default_rng(seed)
        self.feature_dim = matrix.shape[1]
        weights = rng.normal(0.0, 0.01, size=(self.feature_dim, self.class_count))
        bias = np.zeros(self.class_count)
        one_hot = np.zeros((target.size, self.class_count))
        one_hot[np.arange(target.size), target] = 1.0

        # Class weights keep the 42-sample family from vanishing under the
        # 2,942-sample one (research plan v2 R4).
        counts = np.bincount(target, minlength=self.class_count).astype(np.float64)
        weight_per_class = np.where(counts > 0, target.size / (self.class_count * np.maximum(counts, 1)), 0.0)
        sample_weight = weight_per_class[target][:, None]

        losses: list[float] = []
        for _ in range(epochs):
            logits = matrix @ weights + bias
            logits -= logits.max(axis=1, keepdims=True)
            exponentials = np.exp(logits)
            probabilities = exponentials / exponentials.sum(axis=1, keepdims=True)
            error = (probabilities - one_hot) * sample_weight
            gradient_w = matrix.T @ error / target.size + weight_decay * weights
            gradient_b = error.mean(axis=0)
            weights -= learning_rate * gradient_w
            bias -= learning_rate * gradient_b
            losses.append(
                float(-(one_hot * np.log(probabilities + _EPSILON) * sample_weight).sum() / target.size)
            )

        self.weights = weights
        self.bias = bias
        self.training = {
            "epochs": epochs,
            "learning_rate": learning_rate,
            "weight_decay": weight_decay,
            "seed": seed,
            "samples": int(target.size),
            "final_loss": losses[-1],
            "loss_curve_tail": [round(value, 6) for value in losses[-5:]],
        }
        return self

    def log_probabilities_from_features(self, feature_vector: np.ndarray) -> np.ndarray:
        if self.weights is None or self.bias is None:
            raise RuntimeError("TextClassifier is not fitted")
        logits = np.asarray(feature_vector, dtype=np.float64) @ self.weights + self.bias
        logits -= logits.max()
        return logits - np.log(np.exp(logits).sum())

    def log_probabilities(self, data: np.ndarray, valid: np.ndarray | None = None) -> np.ndarray:
        return self.log_probabilities_from_features(features.text_features(data, valid))

    def negative_log_likelihood(
        self, data: np.ndarray, label: int, valid: np.ndarray | None = None
    ) -> float:
        return _nll_from_log_probabilities(self.log_probabilities(data, valid), label)

    def save(self, path: str | Path) -> Path:
        if self.weights is None or self.bias is None:
            raise RuntimeError("TextClassifier is not fitted")
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(
            path,
            weights=self.weights,
            bias=self.bias,
            class_count=np.int64(self.class_count),
            training=np.array(json.dumps(self.training)),
        )
        return path

    @classmethod
    def load(cls, path: str | Path) -> TextClassifier:
        with np.load(Path(path), allow_pickle=False) as archive:
            model = cls(class_count=int(archive["class_count"]))
            model.weights = archive["weights"]
            model.bias = archive["bias"]
            model.feature_dim = model.weights.shape[0]
            model.training = json.loads(str(archive["training"]))
        return model


# ---------------------------------------------------------------------------
# A and B -- torch
# ---------------------------------------------------------------------------


def _build_tiled_module(class_count: int, seed: int):
    torch = _require_torch()
    from torch import nn

    torch.manual_seed(seed)

    class TiledNet(nn.Module):
        """Per-tile encoder, then mean+max pooling over a sample's tiles.

        The first convolution has stride 4, so a 4 KB occlusion (8 rows) still
        spans two positions in the first feature map: the search signal is not
        averaged away before the network sees it.

        Normalization is GroupNorm, not BatchNorm.  A sample contributes at most
        four tiles, so a batch-statistics layer estimates mean and variance from
        four samples during training and then uses different statistics at
        inference.  Measured on this corpus, that diverges outright: validation
        accuracy 0.149 against a 0.111 chance level, NLL 10.0.  GroupNorm's
        statistics do not depend on the batch, so a tile scores the same whether
        it arrives alone or with three others -- which is exactly what an
        occlusion search re-scoring one tile at a time requires.
        """

        def __init__(self) -> None:
            super().__init__()
            self.encoder = nn.Sequential(
                nn.Conv2d(1, 16, kernel_size=7, stride=4, padding=3),
                nn.GroupNorm(4, 16),
                nn.ReLU(inplace=True),
                nn.Conv2d(16, 32, kernel_size=3, stride=2, padding=1),
                nn.GroupNorm(8, 32),
                nn.ReLU(inplace=True),
                nn.Conv2d(32, 64, kernel_size=3, stride=2, padding=1),
                nn.GroupNorm(8, 64),
                nn.ReLU(inplace=True),
                nn.Conv2d(64, 64, kernel_size=3, stride=2, padding=1),
                nn.GroupNorm(8, 64),
                nn.ReLU(inplace=True),
                nn.AdaptiveAvgPool2d(1),
                nn.Flatten(),
            )
            self.head = nn.Sequential(nn.Linear(128, 128), nn.ReLU(inplace=True), nn.Linear(128, class_count))

        def encode_tiles(self, tiles):  # (n_tiles, 1, H, W) -> (n_tiles, 64)
            return self.encoder(tiles)

        def classify_embeddings(self, embeddings):  # (n_tiles, 64) -> (class_count,)
            pooled = torch.cat([embeddings.mean(dim=0), embeddings.max(dim=0).values], dim=0)
            return self.head(pooled)

        def forward(self, tiles):
            return self.classify_embeddings(self.encode_tiles(tiles))

    return TiledNet()


def _build_thumbnail_module(class_count: int, seed: int):
    torch = _require_torch()
    from torch import nn

    torch.manual_seed(seed + 9973)  # a different stream from A, not a shifted copy

    return nn.Sequential(
        nn.Conv2d(1, 24, kernel_size=3, stride=1, padding=1),
        nn.BatchNorm2d(24),
        nn.ReLU(inplace=True),
        nn.MaxPool2d(2),
        nn.Conv2d(24, 48, kernel_size=3, stride=1, padding=1),
        nn.BatchNorm2d(48),
        nn.ReLU(inplace=True),
        nn.MaxPool2d(2),
        nn.Conv2d(48, 96, kernel_size=3, stride=1, padding=1),
        nn.BatchNorm2d(96),
        nn.ReLU(inplace=True),
        nn.MaxPool2d(2),
        nn.Conv2d(96, 96, kernel_size=3, stride=1, padding=1),
        nn.BatchNorm2d(96),
        nn.ReLU(inplace=True),
        nn.AdaptiveAvgPool2d(1),
        nn.Flatten(),
        nn.Dropout(0.1),
        nn.Linear(96, class_count),
    )


@dataclass
class TiledClassifier:
    """Classifier A: reads native-resolution tiles, and caches tile embeddings.

    The cache is what makes exhaustive occlusion affordable.  Masking one 4 KB
    block touches one tile, so re-scoring costs a single tile forward pass plus
    a pooling step, not a pass over the whole sample.
    """

    class_count: int
    seed: int = 0
    tile_rows: int = features.DEFAULT_TILE_ROWS
    width: int = features.DEFAULT_WIDTH
    max_tiles: int = 8
    name: str = MODEL_TILED
    module: Any = None
    training: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.module is None:
            self.module = _build_tiled_module(self.class_count, self.seed)
        self.module.eval()

    # -- tiling ------------------------------------------------------------

    def _select_tiles(self, data: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Return ``(tiles, tile_indices)``, subsampling evenly for huge files."""
        tiles = features.to_tiles(data, tile_rows=self.tile_rows, width=self.width)
        indices = np.arange(tiles.shape[0], dtype=np.int64)
        if tiles.shape[0] > self.max_tiles:
            indices = np.unique(np.linspace(0, tiles.shape[0] - 1, self.max_tiles).astype(np.int64))
            tiles = tiles[indices]
        return tiles, indices

    def _tensor(self, tiles: np.ndarray):
        torch = _require_torch()
        return torch.from_numpy(tiles.astype(np.float32) / 255.0).unsqueeze(1)

    # -- inference ---------------------------------------------------------

    def embed(self, data: np.ndarray) -> tuple[Any, np.ndarray]:
        """Tile embeddings and the tile indices they correspond to."""
        torch = _require_torch()
        tiles, indices = self._select_tiles(data)
        with torch.no_grad():
            embeddings = self.module.encode_tiles(self._tensor(tiles))
        return embeddings, indices

    def log_probabilities(self, data: np.ndarray, valid: np.ndarray | None = None) -> np.ndarray:
        torch = _require_torch()
        embeddings, _ = self.embed(data)
        with torch.no_grad():
            logits = self.module.classify_embeddings(embeddings)
            return torch.log_softmax(logits, dim=0).numpy().astype(np.float64)

    def log_probabilities_with_cache(
        self, cache: TileCache, replacement_tiles: dict[int, np.ndarray]
    ) -> np.ndarray:
        """Re-score a sample where only ``replacement_tiles`` changed."""
        torch = _require_torch()
        embeddings = cache.embeddings.clone()
        if replacement_tiles:
            positions = sorted(replacement_tiles)
            stacked = np.stack([replacement_tiles[position] for position in positions])
            with torch.no_grad():
                updated = self.module.encode_tiles(self._tensor(stacked))
            for row, position in enumerate(positions):
                slot = cache.slot_of(position)
                if slot is not None:
                    embeddings[slot] = updated[row]
        with torch.no_grad():
            logits = self.module.classify_embeddings(embeddings)
            return torch.log_softmax(logits, dim=0).numpy().astype(np.float64)

    def negative_log_likelihood(
        self, data: np.ndarray, label: int, valid: np.ndarray | None = None
    ) -> float:
        return _nll_from_log_probabilities(self.log_probabilities(data, valid), label)

    def build_cache(self, data: np.ndarray) -> TileCache:
        embeddings, indices = self.embed(data)
        return TileCache(embeddings=embeddings, tile_indices=indices)

    # -- persistence -------------------------------------------------------

    def save(self, path: str | Path) -> Path:
        torch = _require_torch()
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        torch.save(
            {
                "state_dict": self.module.state_dict(),
                "class_count": self.class_count,
                "seed": self.seed,
                "tile_rows": self.tile_rows,
                "width": self.width,
                "max_tiles": self.max_tiles,
                "training": self.training,
            },
            path,
        )
        return path

    @classmethod
    def load(cls, path: str | Path) -> TiledClassifier:
        torch = _require_torch()
        # These paths are supplied by the CLI.  The checkpoint only contains
        # tensors and primitive metadata, so allowing Python pickle objects is
        # unnecessary and would make an untrusted checkpoint executable.
        payload = torch.load(Path(path), map_location="cpu", weights_only=True)
        model = cls(
            class_count=int(payload["class_count"]),
            seed=int(payload["seed"]),
            tile_rows=int(payload["tile_rows"]),
            width=int(payload["width"]),
            max_tiles=int(payload["max_tiles"]),
        )
        model.module.load_state_dict(payload["state_dict"])
        model.module.eval()
        model.training = dict(payload.get("training", {}))
        return model


@dataclass
class TileCache:
    """Tile embeddings for one unmasked sample, reused across occlusions."""

    embeddings: Any  # torch.Tensor (n_selected, 64)
    tile_indices: np.ndarray

    def slot_of(self, tile_index: int) -> int | None:
        matches = np.flatnonzero(self.tile_indices == tile_index)
        return int(matches[0]) if matches.size else None


@dataclass
class ThumbnailClassifier:
    """Classifier B: the standard whole-file image model, trained independently."""

    class_count: int
    seed: int = 1
    size: int = features.DEFAULT_THUMBNAIL
    width: int = features.DEFAULT_WIDTH
    name: str = MODEL_THUMBNAIL
    module: Any = None
    training: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.module is None:
            self.module = _build_thumbnail_module(self.class_count, self.seed)
        self.module.eval()

    def _tensor(self, images: np.ndarray):
        torch = _require_torch()
        return torch.from_numpy(images).unsqueeze(1)

    def log_probabilities(self, data: np.ndarray, valid: np.ndarray | None = None) -> np.ndarray:
        torch = _require_torch()
        image = features.thumbnail(data, width=self.width, size=self.size)
        with torch.no_grad():
            logits = self.module(self._tensor(image[None, ...]))[0]
            return torch.log_softmax(logits, dim=0).numpy().astype(np.float64)

    def log_probabilities_batch(self, images: np.ndarray) -> np.ndarray:
        torch = _require_torch()
        with torch.no_grad():
            logits = self.module(self._tensor(np.asarray(images, dtype=np.float32)))
            return torch.log_softmax(logits, dim=1).numpy().astype(np.float64)

    def negative_log_likelihood(
        self, data: np.ndarray, label: int, valid: np.ndarray | None = None
    ) -> float:
        return _nll_from_log_probabilities(self.log_probabilities(data, valid), label)

    def save(self, path: str | Path) -> Path:
        torch = _require_torch()
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        torch.save(
            {
                "state_dict": self.module.state_dict(),
                "class_count": self.class_count,
                "seed": self.seed,
                "size": self.size,
                "width": self.width,
                "training": self.training,
            },
            path,
        )
        return path

    @classmethod
    def load(cls, path: str | Path) -> ThumbnailClassifier:
        torch = _require_torch()
        payload = torch.load(Path(path), map_location="cpu", weights_only=True)
        model = cls(
            class_count=int(payload["class_count"]),
            seed=int(payload["seed"]),
            size=int(payload["size"]),
            width=int(payload["width"]),
        )
        model.module.load_state_dict(payload["state_dict"])
        model.module.eval()
        model.training = dict(payload.get("training", {}))
        return model


def load_classifier(path: str | Path, kind: str) -> FamilyClassifier:
    if kind == MODEL_TEXT:
        return TextClassifier.load(path)
    if kind == MODEL_TILED:
        return TiledClassifier.load(path)
    if kind == MODEL_THUMBNAIL:
        return ThumbnailClassifier.load(path)
    raise ValueError(f"unknown classifier kind {kind!r}")


def accuracy(log_probability_rows: Sequence[np.ndarray], labels: Sequence[int]) -> float:
    if len(log_probability_rows) != len(labels):
        raise ValueError("prediction and label counts differ")
    if not labels:
        return 0.0
    correct = sum(int(np.argmax(row) == label) for row, label in zip(log_probability_rows, labels, strict=False))
    return correct / len(labels)


def macro_f1(log_probability_rows: Sequence[np.ndarray], labels: Sequence[int], class_count: int) -> float:
    predictions = np.array([int(np.argmax(row)) for row in log_probability_rows])
    truth = np.asarray(labels, dtype=np.int64)
    scores = []
    for index in range(class_count):
        true_positive = int(((predictions == index) & (truth == index)).sum())
        false_positive = int(((predictions == index) & (truth != index)).sum())
        false_negative = int(((predictions != index) & (truth == index)).sum())
        if true_positive == 0 and (false_positive == 0 or false_negative == 0):
            scores.append(0.0 if (truth == index).any() else float("nan"))
            continue
        precision = true_positive / max(true_positive + false_positive, 1)
        recall = true_positive / max(true_positive + false_negative, 1)
        scores.append(0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall))
    finite = [value for value in scores if not np.isnan(value)]
    return float(np.mean(finite)) if finite else 0.0
