"""Classifier invariants the occlusion search depends on.

The tiled classifier is re-scored one tile at a time against a cache of the
other tiles' embeddings.  That is only sound if a tile's embedding does not
depend on what else is in the batch -- which is why these tests exist and why
the encoder uses GroupNorm.  With BatchNorm the training run diverged outright
(validation accuracy 0.149 against a 0.111 chance level, NLL 10.0), because a
sample contributes at most four tiles.
"""

from __future__ import annotations

import numpy as np
import pytest

from ua_sahi_mal.evidence import classifiers, features

torch = pytest.importorskip("torch", reason="the tiled and thumbnail models need PyTorch")


def sample_bytes(size=900_000, seed=0):
    rng = np.random.default_rng(seed)
    return rng.integers(0, 256, size=size, dtype=np.uint8)


def test_tile_embedding_does_not_depend_on_the_rest_of_the_batch():
    """The cache would be silently wrong if it did."""
    model = classifiers.TiledClassifier(class_count=9, seed=0)
    tiles = features.to_tiles(sample_bytes())
    assert tiles.shape[0] >= 3

    with torch.no_grad():
        together = model.module.encode_tiles(model._tensor(tiles))
        alone = model.module.encode_tiles(model._tensor(tiles[:1]))

    torch.testing.assert_close(together[0], alone[0], rtol=1e-5, atol=1e-6)


def test_the_encoder_carries_no_batch_dependent_normalization():
    for module in model_modules(classifiers.TiledClassifier(class_count=9, seed=0).module):
        assert not isinstance(
            module, (torch.nn.BatchNorm1d, torch.nn.BatchNorm2d, torch.nn.BatchNorm3d)
        ), "batch statistics break single-tile re-scoring; use GroupNorm"


def model_modules(module):
    yield module
    for child in module.children():
        yield from model_modules(child)


def test_log_probabilities_are_a_normalized_distribution():
    model = classifiers.TiledClassifier(class_count=9, seed=0)
    row = model.log_probabilities(sample_bytes())
    assert row.shape == (9,)
    assert float(np.exp(row).sum()) == pytest.approx(1.0, abs=1e-5)


def test_cached_rescoring_matches_a_full_forward_pass():
    """The optimization has to agree with the thing it replaces."""
    model = classifiers.TiledClassifier(class_count=9, seed=0)
    data = sample_bytes()
    rng = np.random.default_rng(0)

    cache = model.build_cache(data)
    masked = data.copy()
    masked[0:4096] = rng.integers(0, 256, 4096, dtype=np.uint8)
    replacement = {0: features.to_tiles(masked)[0]}

    cached = model.log_probabilities_with_cache(cache, replacement)
    direct = model.log_probabilities(masked)
    np.testing.assert_allclose(cached, direct, rtol=1e-4, atol=1e-5)


def test_tiled_classifier_round_trips_through_a_checkpoint(tmp_path):
    model = classifiers.TiledClassifier(class_count=9, seed=3)
    data = sample_bytes()
    before = model.log_probabilities(data)

    path = model.save(tmp_path / "a.pt")
    restored = classifiers.TiledClassifier.load(path)

    np.testing.assert_allclose(before, restored.log_probabilities(data), rtol=1e-6, atol=1e-7)
    assert restored.seed == 3


def test_thumbnail_classifier_round_trips_through_a_checkpoint(tmp_path):
    model = classifiers.ThumbnailClassifier(class_count=9, seed=1)
    data = sample_bytes()
    before = model.log_probabilities(data)

    path = model.save(tmp_path / "b.pt")
    restored = classifiers.ThumbnailClassifier.load(path)

    np.testing.assert_allclose(before, restored.log_probabilities(data), rtol=1e-6, atol=1e-7)


def test_a_and_b_do_not_start_from_the_same_weights():
    """The cross-model argument requires two models, not one twice."""
    first = classifiers.TiledClassifier(class_count=9, seed=0)
    second = classifiers.ThumbnailClassifier(class_count=9, seed=0)
    assert type(first.module) is not type(second.module)

    left = classifiers.TiledClassifier(class_count=9, seed=0)
    right = classifiers.TiledClassifier(class_count=9, seed=1)
    data = sample_bytes()
    assert not np.allclose(left.log_probabilities(data), right.log_probabilities(data))


def test_text_classifier_learns_a_separable_toy_problem():
    rng = np.random.default_rng(0)
    matrix = np.concatenate(
        [
            np.concatenate([rng.normal(1.0, 0.1, (40, 4)), rng.normal(0.0, 0.1, (40, 4))], axis=1),
            np.concatenate([rng.normal(0.0, 0.1, (40, 4)), rng.normal(1.0, 0.1, (40, 4))], axis=1),
        ]
    )
    labels = np.array([0] * 40 + [1] * 40)
    model = classifiers.TextClassifier(class_count=2).fit(matrix, labels, epochs=300)

    predictions = [int(np.argmax(model.log_probabilities_from_features(row))) for row in matrix]
    assert (np.array(predictions) == labels).mean() > 0.95


def test_text_classifier_round_trips_through_disk(tmp_path):
    rng = np.random.default_rng(0)
    matrix = rng.normal(0, 1, (30, features.TEXT_FEATURE_DIM))
    labels = rng.integers(0, 9, 30)
    model = classifiers.TextClassifier(class_count=9).fit(matrix, labels, epochs=20)

    path = model.save(tmp_path / "c.npz")
    restored = classifiers.TextClassifier.load(path)
    np.testing.assert_allclose(
        model.log_probabilities_from_features(matrix[0]),
        restored.log_probabilities_from_features(matrix[0]),
    )
    assert restored.training["epochs"] == 20


def test_unfitted_text_classifier_refuses_to_predict():
    with pytest.raises(RuntimeError, match="not fitted"):
        classifiers.TextClassifier(class_count=9).log_probabilities(sample_bytes(1000))


def test_macro_f1_ignores_classes_absent_from_the_truth():
    rows = [np.log(np.array([0.9, 0.1])), np.log(np.array([0.2, 0.8]))]
    assert classifiers.macro_f1(rows, [0, 1], 2) == pytest.approx(1.0)
