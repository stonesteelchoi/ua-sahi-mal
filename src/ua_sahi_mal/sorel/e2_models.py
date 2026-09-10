"""E2 v3 tile models (torch, imported lazily).

One content-only tile encoder — the same architecture as the BIG2015
``TiledNet`` (stride-4 first conv, GroupNorm so a tile scores identically alone or
in a bag, adaptive pooling to a 64-d embedding) — with two bag poolings:

* ``meanmax``  : mean ‖ max over tile embeddings → head. Identical to TiledNet;
  it drives ``attr_tile_conf`` (single-tile bag) and ``attr_occlusion`` (re-pool
  with one tile perturbed).
* ``attention`` : gated attention-MIL pooling (Ilse et al.) → head. The softmax
  attention weights are the per-tile scores of ``mil_attention``.

The model receives tiles only — **no tile index, offset, or file position** — so
any learned selector built on it is content-only by construction (E2_prereg_v3).
"""

from __future__ import annotations

import numpy as np


class TorchUnavailable(RuntimeError):
    """torch is not installed in this interpreter (cloud/CI without torch)."""


def require_torch():
    try:
        import torch  # noqa: F401
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise TorchUnavailable("torch is required for E2 v3 models/training") from exc
    import torch
    return torch


def resolve_device(name: str = "auto"):
    """``"auto"`` -> cuda if available else cpu; otherwise a torch.device(name)."""
    torch = require_torch()
    if name == "auto":
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    return torch.device(name)


def tiles_to_tensor(tiles: np.ndarray, device=None):
    """``(n, H, W)`` uint8 -> ``(n, 1, H, W)`` float32 in [0, 1] on ``device``."""
    torch = require_torch()
    if tiles.dtype != np.uint8:
        raise TypeError(f"tiles must be uint8, got {tiles.dtype}")
    tensor = torch.from_numpy(np.ascontiguousarray(tiles).astype(np.float32) / 255.0).unsqueeze(1)
    return tensor.to(device) if device is not None else tensor


def build_encoder(embed_dim: int = 64):
    """The TiledNet per-tile encoder: (n, 1, H, W) -> (n, embed_dim)."""
    require_torch()
    from torch import nn

    if embed_dim != 64:
        raise ValueError("encoder architecture is fixed at a 64-d embedding (TiledNet parity)")
    return nn.Sequential(
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


POOLINGS = ("meanmax", "attention")


def build_model(class_count: int, *, pooling: str = "meanmax", seed: int = 0, attn_dim: int = 64):
    """Construct a :class:`SorelTileNet`; ``seed`` fixes the initialisation."""
    torch = require_torch()
    from torch import nn

    if pooling not in POOLINGS:
        raise ValueError(f"pooling must be one of {POOLINGS}, got {pooling!r}")
    torch.manual_seed(seed)
    embed_dim = 64

    class SorelTileNet(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.pooling = pooling
            self.class_count = class_count
            self.encoder = build_encoder(embed_dim)
            if pooling == "attention":
                self.attn_v = nn.Linear(embed_dim, attn_dim)
                self.attn_u = nn.Linear(embed_dim, attn_dim)
                self.attn_w = nn.Linear(attn_dim, 1)
                head_in = embed_dim
            else:
                head_in = 2 * embed_dim
            self.head = nn.Sequential(nn.Linear(head_in, 128), nn.ReLU(inplace=True), nn.Linear(128, class_count))

        def encode_tiles(self, tiles):  # (n, 1, H, W) -> (n, 64)
            return self.encoder(tiles)

        def attention_weights(self, embeddings):  # (n, 64) -> (n,) softmax
            if self.pooling != "attention":
                raise RuntimeError("attention_weights requires pooling='attention'")
            gate = torch.tanh(self.attn_v(embeddings)) * torch.sigmoid(self.attn_u(embeddings))
            return torch.softmax(self.attn_w(gate).squeeze(-1), dim=0)

        def pool(self, embeddings):  # (n, 64) -> (head_in,)
            if self.pooling == "attention":
                weights = self.attention_weights(embeddings)
                return (weights.unsqueeze(-1) * embeddings).sum(dim=0)
            return torch.cat([embeddings.mean(dim=0), embeddings.max(dim=0).values], dim=0)

        def classify_embeddings(self, embeddings):  # (n, 64) -> (class_count,)
            return self.head(self.pool(embeddings))

        def forward(self, tiles):  # (n, 1, H, W) -> (class_count,)
            return self.classify_embeddings(self.encode_tiles(tiles))

        def forward_with_attention(self, tiles):  # -> (logits (C,), weights (n,))
            embeddings = self.encode_tiles(tiles)
            return self.classify_embeddings(embeddings), self.attention_weights(embeddings)

    return SorelTileNet()


def encode_in_chunks(model, tiles: np.ndarray, device, *, chunk: int = 256):
    """Encode all tiles of one file without holding every tile tensor on the GPU."""
    torch = require_torch()
    out = []
    with torch.no_grad():
        for start in range(0, tiles.shape[0], chunk):
            out.append(model.encode_tiles(tiles_to_tensor(tiles[start:start + chunk], device)))
    return torch.cat(out, dim=0) if out else torch.zeros((0, 64), device=device)


def save_checkpoint(model, path, *, meta: dict) -> None:
    """Weights + SHA-free metadata (class names, pooling, config). Path must be isolated."""
    torch = require_torch()
    from ua_sahi_mal.sorel.paths import assert_isolated_output

    target = assert_isolated_output(path, kind="checkpoint")
    payload = {"state_dict": model.state_dict(), "pooling": model.pooling,
               "class_count": int(model.class_count), "meta": meta}
    torch.save(payload, target)


def load_checkpoint(path, *, device=None):
    """Rebuild the model from a checkpoint; returns ``(model, meta)``."""
    torch = require_torch()
    payload = torch.load(path, map_location="cpu", weights_only=False)
    model = build_model(int(payload["class_count"]), pooling=str(payload["pooling"]))
    model.load_state_dict(payload["state_dict"])
    model.eval()
    if device is not None:
        model.to(device)
    return model, dict(payload.get("meta") or {})
