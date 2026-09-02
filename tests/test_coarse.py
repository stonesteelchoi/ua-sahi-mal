from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from ua_sahi_mal.coarse import (
    aggregate_fpn_logits,
    combine_probability_entropy,
    run_dense_coarse_pass,
)


class _FakeTensor:
    def __init__(self, array: np.ndarray) -> None:
        self.array = array

    def detach(self):
        return self

    def float(self):
        return self

    def cpu(self):
        return self

    def numpy(self) -> np.ndarray:
        return self.array


class _FakeFeature:
    def __init__(self, shape: tuple[int, ...]) -> None:
        self.shape = shape


class _FakeHandle:
    def __init__(self, head) -> None:
        self.head = head

    def remove(self) -> None:
        self.head.hook_removed = True


class _FakeHead:
    stride = [8.0]

    def __init__(self) -> None:
        self.hook = None
        self.hook_removed = False

    def register_forward_hook(self, hook):
        self.hook = hook
        return _FakeHandle(self)


def test_aggregate_fpn_logits_returns_probability_and_binary_entropy() -> None:
    logits = [
        np.zeros((2, 2, 3), dtype=np.float32),
        np.full((2, 1, 2), -20.0, dtype=np.float32),
    ]

    probability, entropy = aggregate_fpn_logits(logits, output_shape=(4, 6))

    assert probability.shape == (4, 6)
    assert entropy.shape == (4, 6)
    assert probability.dtype == np.float32
    assert entropy.dtype == np.float32
    np.testing.assert_allclose(probability, 0.5, atol=1e-6)
    np.testing.assert_allclose(entropy, 1.0, atol=1e-5)


def test_aggregate_fpn_logits_uses_maximum_over_classes_and_levels() -> None:
    log_three = np.float32(np.log(3.0))
    first = np.array([[[0.0]], [[log_three]]], dtype=np.float32)
    second = np.array([[[-log_three]]], dtype=np.float32)

    probability, entropy = aggregate_fpn_logits([first, second], output_shape=(1, 1))

    assert probability[0, 0] == pytest.approx(0.75)
    assert entropy[0, 0] == pytest.approx(0.811278, abs=1e-5)


@pytest.mark.parametrize(
    "levels",
    [[], [np.zeros((2, 2), dtype=np.float32)], [np.array([[[np.nan]]], dtype=np.float32)]],
)
def test_aggregate_fpn_logits_rejects_invalid_levels(levels: list[np.ndarray]) -> None:
    with pytest.raises(ValueError):
        aggregate_fpn_logits(levels, output_shape=(2, 2))


def test_combine_probability_entropy_normalizes_weights() -> None:
    probability = np.array([[0.2, 0.8]], dtype=np.float32)
    entropy = np.array([[1.0, 0.0]], dtype=np.float32)

    result = combine_probability_entropy(
        probability,
        entropy,
        probability_weight=3.0,
        entropy_weight=1.0,
    )

    np.testing.assert_allclose(result, [[0.4, 0.6]], atol=1e-6)

    with pytest.raises(ValueError, match="same-shaped"):
        combine_probability_entropy(
            probability,
            np.zeros((2, 1), dtype=np.float32),
            probability_weight=1,
            entropy_weight=1,
        )
    with pytest.raises(ValueError, match="at least one"):
        combine_probability_entropy(
            probability,
            entropy,
            probability_weight=0,
            entropy_weight=0,
        )


def test_dense_coarse_pass_captures_same_prediction_forward(monkeypatch: pytest.MonkeyPatch) -> None:
    head = _FakeHead()
    detection_model = SimpleNamespace(model=SimpleNamespace(model=SimpleNamespace(model=[head])))
    prediction_result = object()

    def fake_get_prediction(**kwargs):
        assert kwargs["detection_model"] is detection_model
        assert head.hook is not None
        scores = np.zeros((1, 2, 8), dtype=np.float32)
        scores[:, 1, :] = np.log(3.0)
        head.hook(
            head,
            (),
            {
                "scores": _FakeTensor(scores),
                "feats": [_FakeFeature((1, 4, 2, 4))],
            },
        )
        return prediction_result

    monkeypatch.setattr("sahi.predict.get_prediction", fake_get_prediction)

    result = run_dense_coarse_pass(
        image=Image.new("RGB", (32, 16)),
        detection_model=detection_model,
        confidence_threshold=0.2,
        output_shape=(4, 8),
    )

    assert result.prediction_result is prediction_result
    assert result.fpn_shapes == ((2, 4),)
    assert result.input_shape == (16, 32)
    assert result.probability_map.shape == (4, 8)
    np.testing.assert_allclose(result.probability_map, 0.75, atol=1e-6)
    assert head.hook_removed
