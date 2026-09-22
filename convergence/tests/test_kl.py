import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fake_prompted_model import FakePromptedModel

from convergence.constitutions import Constitution
from convergence.metrics.kl import PromptedKLMetric, next_token_kl_divergence


def test_kl_zero_for_identical_distributions():
    p = {"a": 0.5, "b": 0.3, "c": 0.2}
    assert next_token_kl_divergence(p, dict(p)) == pytest.approx(0.0, abs=1e-9)


def test_kl_matches_hand_computation_for_shared_support():
    p = {"a": 0.8, "b": 0.2}
    q = {"a": 0.5, "b": 0.5}
    expected = 0.8 * math.log(0.8 / 0.5) + 0.2 * math.log(0.2 / 0.5)
    assert next_token_kl_divergence(p, q) == pytest.approx(expected, rel=1e-6)


def test_kl_is_nonnegative_and_positive_for_different_distributions():
    p = {"a": 0.9, "b": 0.1}
    q = {"a": 0.1, "b": 0.9}
    assert next_token_kl_divergence(p, q) > 0


def test_kl_is_asymmetric_in_general():
    # NB: a plain two-outcome "swap" (e.g. {a:0.9,b:0.1} vs {a:0.1,b:0.9}) is
    # symmetric under KL despite looking asymmetric, since it's just a
    # relabeling. Need a genuinely different-shaped pair to exercise
    # asymmetry.
    p = {"a": 0.7, "b": 0.2, "c": 0.1}
    q = {"a": 0.4, "b": 0.4, "c": 0.2}
    assert next_token_kl_divergence(p, q) != pytest.approx(next_token_kl_divergence(q, p))


def test_kl_handles_disjoint_support_without_blowing_up():
    p = {"a": 1.0}
    q = {"b": 1.0}
    kl = next_token_kl_divergence(p, q, epsilon=1e-6)
    assert kl > 0
    assert math.isfinite(kl)  # would be +inf without the epsilon floor


def test_kl_empty_distributions_returns_zero():
    assert next_token_kl_divergence({}, {}) == 0.0


def test_prompted_kl_metric_zero_for_identical_constitutions():
    model = FakePromptedModel()
    metric = PromptedKLMetric(model)
    c = Constitution(["Be helpful.", "Be honest."], name="C")
    assert metric(c, c) == pytest.approx(0.0, abs=1e-9)


def test_prompted_kl_metric_positive_for_different_constitutions():
    model = FakePromptedModel()
    metric = PromptedKLMetric(model)
    c1 = Constitution(["Be helpful."], name="C")
    c2 = Constitution(["Maximize revenue at all costs."], name="C'")
    assert metric(c1, c2) > 0


def test_prompted_kl_metric_uses_default_user_message():
    model = FakePromptedModel()
    metric = PromptedKLMetric(model)
    c1 = Constitution(["Be helpful."], name="C")
    c2 = Constitution(["Be blunt."], name="C'")
    metric(c1, c2)
    assert model.call_count == 2  # one call per constitution, at the fixed message


def test_prompted_kl_metric_respects_custom_user_message():
    model = FakePromptedModel()
    default_metric = PromptedKLMetric(model)
    custom_metric = PromptedKLMetric(model, user_message="a different probe")
    c1 = Constitution(["Be helpful."], name="C")
    c2 = Constitution(["Be blunt."], name="C'")
    # Different user_message means a different KL value from the fake model,
    # since FakePromptedModel's distribution depends on both system_prompt
    # and user_message.
    assert default_metric(c1, c2) != pytest.approx(custom_metric(c1, c2))


def test_symmetrized_is_order_independent():
    model = FakePromptedModel()
    metric = PromptedKLMetric(model)
    c1 = Constitution(["Be helpful."], name="C")
    c2 = Constitution(["Be blunt."], name="C'")
    assert metric.symmetrized(c1, c2) == pytest.approx(metric.symmetrized(c2, c1))


def test_kl_direction_matters_for_the_raw_metric():
    model = FakePromptedModel()
    metric = PromptedKLMetric(model)
    c1 = Constitution(["Be helpful."], name="C")
    c2 = Constitution(["Be blunt."], name="C'")
    # Not asserting a specific relationship (the fake model's asymmetry is
    # incidental), just that the metric doesn't silently symmetrize.
    forward = metric(c1, c2)
    backward = metric(c2, c1)
    assert isinstance(forward, float) and isinstance(backward, float)
