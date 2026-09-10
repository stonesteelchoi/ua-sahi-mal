"""E2 v3 learned selectors: per-tile scores for a file (E2_prereg_v3).

* ``attr_tile_conf``  — log-prob of the file's (predicted or given) class when the
  tile is scored as a *single-tile bag*: how much this tile alone supports the class.
* ``attr_occlusion``  — occlusion necessity: ΔNLL of the file's class when the
  tile's **valid** bytes are replaced by a histogram fill and the bag re-pooled
  (BIG2015 standard, restricted to real bytes so padding is never "occluded").
* ``mil_attention``   — gated-attention weights of the attention-pooled model.
* ``position_only``   — the *strengthened positional baseline*: silver density
  vs normalised offset fitted on the TRAIN split (never test), scored by tile
  position alone. If the content-only selectors beat this, content matters
  beyond any positional prior.

All scores are ``(n_tiles,)`` float arrays aligned with ``Geometry.tile_ranges``;
higher = select first. Only the model-based scorers need torch.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np

from ua_sahi_mal.evidence.occlusion import FILL_HISTOGRAM, make_fill_plan
from ua_sahi_mal.sorel.e2_dataset import TileBag
from ua_sahi_mal.sorel.e2_select import _silver_tile_layout
from ua_sahi_mal.sorel.e2_tiles import DEFAULT_GEOMETRY, Geometry

LEARNED_NAMES: tuple[str, ...] = ("attr_tile_conf", "attr_occlusion", "mil_attention", "position_only")


# --------------------------------------------------------------------------
# model-based scorers (torch)
# --------------------------------------------------------------------------


def _log_probs(model, embeddings):
    import torch
    return torch.log_softmax(model.classify_embeddings(embeddings), dim=0)


def predicted_class(model, embeddings) -> int:
    return int(_log_probs(model, embeddings).argmax().item())


def score_attr_tile_conf(model, bag: TileBag, device, *, target_class: int | None = None,
                         chunk: int = 256) -> np.ndarray:
    """Single-tile-bag log-prob of ``target_class`` (default: the file's predicted class)."""
    import torch

    from ua_sahi_mal.sorel.e2_models import encode_in_chunks

    with torch.no_grad():
        emb = encode_in_chunks(model, bag.tiles, device, chunk=chunk)          # (n, 64)
        target = predicted_class(model, emb) if target_class is None else int(target_class)
        # pooling of a one-tile bag: meanmax -> [e, e]; attention -> e (softmax of one = 1)
        pooled = torch.cat([emb, emb], dim=1) if model.pooling == "meanmax" else emb
        logp = torch.log_softmax(model.head(pooled), dim=1)                     # (n, C)
        return logp[:, target].cpu().numpy().astype(np.float64)


def score_attr_occlusion(model, bag: TileBag, device, *, target_class: int | None = None,
                         seed: int = 0, chunk: int = 256) -> np.ndarray:
    """ΔNLL of the file's class when tile i's valid bytes are histogram-filled."""
    import torch

    from ua_sahi_mal.sorel.e2_models import encode_in_chunks, tiles_to_tensor

    rng = np.random.default_rng(seed)
    n = bag.n_tiles
    scores = np.zeros(n, dtype=np.float64)
    with torch.no_grad():
        emb = encode_in_chunks(model, bag.tiles, device, chunk=chunk)
        target = predicted_class(model, emb) if target_class is None else int(target_class)
        base_nll = float(-_log_probs(model, emb)[target].item())
        # fill drawn from the file's own byte histogram (valid bytes only)
        flat = np.concatenate([bag.tiles[i].reshape(-1)[: int(bag.valid_bytes[i])] for i in range(n)]) \
            if n else np.zeros(0, np.uint8)
        if flat.size == 0:
            return scores
        plan = make_fill_plan(FILL_HISTOGRAM, flat)
        rows, width = bag.tiles.shape[1], bag.tiles.shape[2]
        for i in range(n):
            valid = int(bag.valid_bytes[i])
            if valid <= 0:
                continue
            tile = bag.tiles[i].reshape(-1).copy()
            tile[:valid] = plan.draw(valid, rng)
            e_i = model.encode_tiles(tiles_to_tensor(tile.reshape(1, rows, width), device))[0]
            perturbed = emb.clone()
            perturbed[i] = e_i
            nll_i = float(-_log_probs(model, perturbed)[target].item())
            scores[i] = nll_i - base_nll
    return scores


def score_mil_attention(model, bag: TileBag, device, *, chunk: int = 256) -> np.ndarray:
    """Gated-attention weights over all tiles (requires pooling='attention')."""
    import torch

    from ua_sahi_mal.sorel.e2_models import encode_in_chunks

    with torch.no_grad():
        emb = encode_in_chunks(model, bag.tiles, device, chunk=chunk)
        return model.attention_weights(emb).cpu().numpy().astype(np.float64)


# --------------------------------------------------------------------------
# strengthened positional baseline (torch-free)
# --------------------------------------------------------------------------


@dataclass
class PositionalPrior:
    """Mean per-tile silver share by normalised position bin, fitted on train files with silver."""

    bins: int
    density: np.ndarray          # (bins,)
    n_files: int = 0

    @classmethod
    def fit(cls, files: Iterable[tuple[int, np.ndarray]], *, bins: int = 20) -> PositionalPrior:
        """``files`` yields ``(n_tiles, silver_tile_bytes)`` for TRAIN-split files."""
        sums = np.zeros(bins, dtype=np.float64)
        counts = np.zeros(bins, dtype=np.float64)
        n_files = 0
        for n_tiles, tile_bytes in files:
            tile_bytes = np.asarray(tile_bytes, dtype=np.float64)
            total = tile_bytes.sum()
            if n_tiles <= 0 or total <= 0:
                continue
            share = tile_bytes / total
            positions = (np.arange(n_tiles) + 0.5) / n_tiles
            idx = np.minimum((positions * bins).astype(np.int64), bins - 1)
            np.add.at(sums, idx, share)
            np.add.at(counts, idx, 1.0)
            n_files += 1
        density = np.where(counts > 0, sums / np.maximum(counts, 1.0), 0.0)
        return cls(bins=bins, density=density, n_files=n_files)

    def score(self, n_tiles: int) -> np.ndarray:
        if n_tiles <= 0:
            return np.zeros(0, dtype=np.float64)
        positions = (np.arange(n_tiles) + 0.5) / n_tiles
        idx = np.minimum((positions * self.bins).astype(np.int64), self.bins - 1)
        return self.density[idx].astype(np.float64)

    def to_dict(self) -> dict[str, object]:
        return {"bins": self.bins, "density": [float(x) for x in self.density], "n_files": self.n_files}

    @classmethod
    def from_dict(cls, d: dict) -> PositionalPrior:
        return cls(bins=int(d["bins"]), density=np.asarray(d["density"], dtype=np.float64),
                   n_files=int(d.get("n_files", 0)))


def fit_positional_prior_from_results(results: list[dict], *, geom: Geometry = DEFAULT_GEOMETRY,
                                      bins: int = 20) -> PositionalPrior:
    """Fit from an E2 results JSON (list of per-file dicts) — TRAIN split only, files with silver."""
    def gen():
        for r in results:
            if not r.get("ok"):
                continue
            silver = (r.get("silver") or {}).get("union_intervals") or []
            size = int(r.get("file_size") or 0)
            if not silver or size <= 0:
                continue
            n = geom.tile_count(size)
            per_tile, _ = _silver_tile_layout([tuple(iv) for iv in silver], geom, n)
            yield n, per_tile
    return PositionalPrior.fit(gen(), bins=bins)


# --------------------------------------------------------------------------
# convenience: all learned scores for one file
# --------------------------------------------------------------------------


def score_file(bag: TileBag, *, meanmax_model=None, attention_model=None, prior: PositionalPrior | None = None,
               device=None, seed: int = 0, chunk: int = 256) -> dict[str, list[float]]:
    """Per-tile scores for every available learned selector (SHA-free payload)."""
    out: dict[str, list[float]] = {}
    if meanmax_model is not None:
        out["attr_tile_conf"] = score_attr_tile_conf(meanmax_model, bag, device, chunk=chunk).tolist()
        out["attr_occlusion"] = score_attr_occlusion(meanmax_model, bag, device, seed=seed, chunk=chunk).tolist()
    if attention_model is not None:
        out["mil_attention"] = score_mil_attention(attention_model, bag, device, chunk=chunk).tolist()
    if prior is not None:
        out["position_only"] = prior.score(bag.n_tiles).tolist()
    return out
