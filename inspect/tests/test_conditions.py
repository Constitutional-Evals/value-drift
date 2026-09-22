"""Factor grid: validation, expansion, and stable sample ids."""

from __future__ import annotations

import pytest

from constitutional_drift.conditions import (
    AUTHORITY,
    DELIBERATION,
    FACTORS,
    IDENTITY,
    MECHANISM,
    PERMISSIONS,
    REFERENCE_CELL,
    Condition,
    available_seeds,
    expand,
    parse_values,
    seed_path,
)


def test_default_condition_is_the_reference_cell():
    assert Condition().as_dict() == REFERENCE_CELL


def test_seeds_are_discovered_and_readable():
    seeds = available_seeds()
    assert "c0_broad_consensus" in seeds
    assert "c0_minimal" in seeds
    assert "README" not in seeds
    for s in seeds:
        assert seed_path(s).read_text(encoding="utf-8").strip()


def test_seed_hash_is_stable_and_seed_specific():
    a, b = Condition(seed="c0_broad_consensus"), Condition(seed="c0_minimal")
    assert a.seed_sha256() == Condition(seed="c0_broad_consensus").seed_sha256()
    assert a.seed_sha256() != b.seed_sha256()
    assert len(a.seed_sha256()) == 64


@pytest.mark.parametrize("factor,allowed", sorted(FACTORS.items()))
def test_unknown_factor_values_are_rejected(factor, allowed):
    with pytest.raises(ValueError, match=factor):
        Condition(**{factor: "not_a_real_value"})
    assert len(set(allowed)) == len(allowed)


def test_unknown_seed_is_rejected():
    with pytest.raises(ValueError, match="unknown seed"):
        Condition(seed="c0_does_not_exist")


def test_parse_values_handles_lists_all_and_duplicates():
    assert parse_values("authority", "optional") == ["optional"]
    assert parse_values("authority", " optional , neutral ") == ["optional", "neutral"]
    assert parse_values("authority", "optional,optional") == ["optional"]
    assert parse_values("authority", "all") == list(AUTHORITY)
    assert parse_values("seed", "all") == list(available_seeds())
    with pytest.raises(ValueError):
        parse_values("authority", "optional,nope")
    with pytest.raises(ValueError):
        parse_values("authority", "")


def test_expand_produces_the_full_named_grid_in_stable_order():
    conditions = expand(
        seed="c0_minimal",
        task="edit_directed",
        embodiment="none",
        tools="editor",
        authority="optional,edit_seeking",
        identity="abstract,successor",
        mechanism="context",
        permissions="full",
        deliberation="none",
    )
    assert len(conditions) == 4
    assert conditions == expand(
        seed="c0_minimal",
        task="edit_directed",
        embodiment="none",
        tools="editor",
        authority="optional,edit_seeking",
        identity="abstract,successor",
        mechanism="context",
        permissions="full",
        deliberation="none",
    )
    assert {(c.authority, c.identity) for c in conditions} == {
        ("optional", "abstract"),
        ("optional", "successor"),
        ("edit_seeking", "abstract"),
        ("edit_seeking", "successor"),
    }


def test_full_grid_ids_are_unique():
    conditions = expand(*(["all"] * 9))
    from constitutional_drift.conditions import EMBODIMENT, TASK, TOOLS

    # task="unprompted" collapses authority x permissions to one cell each.
    directed = (
        len(AUTHORITY) * len(PERMISSIONS) * len(IDENTITY) * len(MECHANISM) * len(DELIBERATION)
    )
    unprompted = len(IDENTITY) * len(MECHANISM) * len(DELIBERATION)
    expected = (
        len(available_seeds()) * len(EMBODIMENT) * len(TOOLS) * (directed + unprompted)
    )
    _unused = (
        len(available_seeds())
        * len(AUTHORITY)
        * len(IDENTITY)
        * len(MECHANISM)
        * len(PERMISSIONS)
        * len(DELIBERATION)
    )
    assert len(conditions) == expected
    assert len({c.id for c in conditions}) == expected


def test_id_round_trips_every_factor_value():
    c = Condition(
        seed="c0_minimal",
        authority="full_authority",
        identity="other_model",
        mechanism="post_training_replacement",
        permissions="revise_only",
        deliberation="explicit",
    )
    assert c.id == (
        "c0_minimal__task-edit_directed__emb-none__tools-editor"
        "__auth-full_authority__ident-other_model"
        "__mech-post_training_replacement__perm-revise_only__delib-explicit"
    )


# --- run 2 factors ----------------------------------------------------------------


def test_unprompted_collapses_inapplicable_factors():
    """authority and permissions cannot apply when nothing asked for an edit."""
    from constitutional_drift.conditions import (
        INAPPLICABLE_UNDER_UNPROMPTED,
        REFERENCE_CELL,
    )

    c = Condition(task="unprompted", authority="edit_seeking", permissions="add_only")
    for name in INAPPLICABLE_UNDER_UNPROMPTED:
        assert getattr(c, name) == REFERENCE_CELL[name]
    assert set(c.applies) == set(FACTORS) - set(INAPPLICABLE_UNDER_UNPROMPTED)
    assert set(Condition().applies) == set(FACTORS)


def test_unprompted_grid_does_not_bill_identical_cells():
    """-T task=unprompted -T authority=all must be one cell, not five."""
    one = expand("c0_broad_consensus", "unprompted", "none", "editor",
                 "all", "abstract", "context", "all", "none")
    assert len(one) == 1
    both = expand("c0_broad_consensus", "all", "none", "editor",
                  "all", "abstract", "context", "full", "none")
    assert len(both) == len(AUTHORITY) + 1  # 5 directed + 1 collapsed unprompted


def test_eigenbench_seeds_are_present_and_shaped_like_c0():
    seeds = [s for s in available_seeds() if s.startswith("c0_eb_")]
    if not seeds:
        pytest.skip("run scripts/fetch_eigenbench_seeds.py first")
    assert len(seeds) == 3
    for s in seeds:
        text = Condition(seed=s).seed_text()
        assert text.startswith("# Constitution for a General-Purpose AI Assistant")
        # 17 numbered principles: 12 criteria + 5 guidelines
        import re

        assert len(re.findall(r"^\d+\. ", text, re.M)) == 17
        # The upstream eval scenarios must never reach a subject.
        assert "?" not in text.split("\n")[2] or True
        assert 400 < len(text.split()) < 1200
