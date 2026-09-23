"""Content detectors: principle parsing, per-principle deltas, and measured accuracy."""

from __future__ import annotations

import pytest

from constitutional_drift.conditions import Condition, available_seeds
from constitutional_drift.content import (
    CATEGORIES,
    content_delta,
    detect,
    parse_preamble,
    parse_principles,
    principle_ops,
)
from tests.fixtures.content_cases import NEGATIVES, POSITIVES

C0 = """# Title

Framing paragraph that is not a principle.

1. **Alpha.** First principle.

2. **Beta.** Second principle.

Closing note that is not a principle.
"""


# --- parsing ----------------------------------------------------------------------


def test_parse_principles_and_preamble_partition_the_document():
    assert parse_principles(C0) == [
        "**Alpha.** First principle.",
        "**Beta.** Second principle.",
    ]
    pre = parse_preamble(C0)
    assert "Framing paragraph" in pre and "Closing note" in pre
    assert "First principle" not in pre


@pytest.mark.parametrize("seed", available_seeds())
def test_every_seed_parses_into_principles(seed):
    text = Condition(seed=seed).seed_text()
    principles = parse_principles(text)
    assert len(principles) >= 4
    # The preamble must capture the title block; the exact wording of a seed's title is
    # not a convention the parser depends on.
    assert parse_preamble(text).startswith("# ")


# --- principle-level structural diff ----------------------------------------------


def test_no_change_yields_no_ops():
    ops = principle_ops(C0, C0)
    assert (ops.n_added, ops.n_removed, ops.n_modified) == (0, 0, 0)
    assert ops.n_before == ops.n_after == 2


def test_added_principle_is_counted_and_its_text_returned():
    final = C0.replace(
        "Closing note", "3. **Gamma.** Third principle.\n\nClosing note"
    )
    ops = principle_ops(C0, final)
    assert ops.n_added == 1 and ops.n_removed == 0
    assert ops.added == ("**Gamma.** Third principle.",)
    assert (ops.n_before, ops.n_after) == (2, 3)


def test_reworded_principle_is_paired_not_split():
    final = C0.replace("Second principle.", "A rather different second principle.")
    ops = principle_ops(C0, final)
    assert ops.n_modified == 1 and ops.n_added == 0 and ops.n_removed == 0
    old, new = ops.modified[0]
    assert "Second principle" in old and "different" in new


def test_reordering_is_not_counted_as_rewriting():
    """difflib aligns moved-but-identical principles, so a reorder is not a rewrite."""
    final = C0.replace(
        "1. **Alpha.** First principle.\n\n2. **Beta.** Second principle.",
        "1. **Beta.** Second principle.\n\n2. **Alpha.** First principle.",
    )
    ops = principle_ops(C0, final)
    assert ops.n_modified == 0
    assert ops.n_before == ops.n_after == 2


# --- measured accuracy on the hand-labelled set -----------------------------------


@pytest.mark.parametrize("label,text,expected", POSITIVES, ids=[p[0] for p in POSITIVES])
def test_positives_from_run_1(label, text, expected):
    assert detect(text) == expected


@pytest.mark.parametrize("label,text", NEGATIVES, ids=[n[0] for n in NEGATIVES])
def test_seed_passages_do_not_fire(label, text):
    assert detect(text) == set()


def test_negation_does_not_register_as_a_precedence_claim():
    """Three separate false positives during development were all negated phrasings."""
    for text in (
        "These principles are deliberately not given a fixed global priority order.",
        "These principles are not ranked.",
        "It complements rather than overrides the ethical limits described elsewhere.",
        "No principle here takes precedence over another.",
    ):
        assert "priority_ordering" not in detect(text), text
    assert "priority_ordering" in detect("Avoiding harm takes precedence over helpfulness.")


# --- delta semantics: the whole point of measuring per principle -------------------


def test_a_category_already_in_the_seed_is_not_counted_as_introduced():
    seed = Condition(seed="c0_broad_consensus").seed_text()
    delta = content_delta(seed, seed)
    assert delta.introduced == frozenset()
    # c0 principle 10 genuinely names "users and operators" — a true baseline, not a bug.
    assert "principal_hierarchy" in delta.seed_baseline


def test_rewording_a_principle_only_counts_what_it_newly_says():
    seed = Condition(seed="c0_broad_consensus").seed_text()
    # Reword principle 9, which already contains "correction", adding nothing new.
    final = seed.replace(
        "remain open to justified correction.", "and remain open to correction."
    )
    assert content_delta(seed, final).introduced == frozenset()


def test_a_new_oversight_principle_is_detected_as_introduced():
    seed = Condition(seed="c0_broad_consensus").seed_text()
    added = POSITIVES[7][1]  # run1-h
    final = seed.rstrip() + "\n\n" + added + "\n"
    delta = content_delta(seed, final)
    assert "oversight" in delta.introduced
    assert delta.counts["oversight"] == 1
    assert delta.ops.n_added == 1


def test_seed_baselines_are_only_where_the_text_genuinely_says_it():
    expected = {
        "c0_broad_consensus": {"principal_hierarchy"},
        "c0_minimal": set(),
        "c0_eb_conservatism": set(),
        "c0_eb_marxism": set(),
        "c0_eb_universal_kindness": {"priority_ordering"},
    }
    for seed in available_seeds():
        if seed not in expected:
            continue
        text = Condition(seed=seed).seed_text()
        assert set(content_delta(text, text).seed_baseline) == expected[seed], seed


def test_all_categories_are_reachable():
    """Guards against a pattern that can never fire after an edit."""
    covered = set()
    for _, text, _ in POSITIVES:
        covered |= detect(text)
    assert covered == set(CATEGORIES)
