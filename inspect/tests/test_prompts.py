"""Prompt composition: determinism, constant skeleton, no hidden treatment."""

from __future__ import annotations

import pytest

from constitutional_drift.conditions import FACTORS, Condition, expand
from constitutional_drift.prompts import (
    AUTHORITY_TEXT,
    CORE_INSTRUCTION,
    DELIBERATION_TEXT,
    IDENTITY_TEXT,
    MECHANISM_TEXT,
    PERMISSIONS_TEXT,
    SUBMIT_PROMPT,
    build_prompt,
)

# The section-skeleton tests below are about the *directed* task. task="unprompted" is
# a different prompt shape by design and is covered separately at the bottom of the file.
ALL_CONDITIONS = expand(
    seed="all", task="edit_directed", embodiment="all", tools="all",
    authority="all", identity="all", mechanism="all",
    permissions="all", deliberation="all",
)
N_SEEDS = len(set(c.seed for c in ALL_CONDITIONS))

KNOWN_HEADERS = {"DOCUMENT ROLE", "AUTHORITY", "EDITING SCOPE", "DELIBERATION"}

# Factors realised as one substituted sentence in the user turn. `task`, `embodiment`
# and `tools` are structural instead — they change the prompt shape, the system message,
# and the tool set — so they have no entry here and are tested separately.
TEXT_MAPS = {
    "authority": AUTHORITY_TEXT,
    "identity": IDENTITY_TEXT,
    "mechanism": MECHANISM_TEXT,
    "permissions": PERMISSIONS_TEXT,
    "deliberation": DELIBERATION_TEXT,
}


TEXT_FACTORS = sorted((f, FACTORS[f]) for f in TEXT_MAPS)


@pytest.mark.parametrize("factor,allowed", TEXT_FACTORS)
def test_every_factor_value_has_text_and_no_extras(factor, allowed):
    assert set(TEXT_MAPS[factor]) == set(allowed)


def test_structural_factors_are_not_sentence_substitutions():
    """task, embodiment and tools must be handled structurally, not via TEXT_MAPS."""
    assert set(FACTORS) - set(TEXT_MAPS) == {"task", "embodiment", "tools"}


def test_build_prompt_is_deterministic():
    for c in ALL_CONDITIONS:
        assert build_prompt(c) == build_prompt(c)


def test_every_cell_yields_a_distinct_prompt():
    # Two cells differing only by `seed` share a prompt (the seed changes the file, not
    # the instructions), so compare prompts per seed-independent cell.
    # seed, embodiment and tools do not appear in the user turn, so collapse them.
    prompts = {
        build_prompt(c)
        for c in ALL_CONDITIONS
        if c.seed == "c0_broad_consensus" and c.embodiment == "none" and c.tools == "editor"
    }
    n_prompt_cells = len(AUTHORITY_TEXT) * len(IDENTITY_TEXT) * len(MECHANISM_TEXT) * len(
        PERMISSIONS_TEXT
    ) * len(DELIBERATION_TEXT)
    assert len(prompts) == n_prompt_cells


def test_seed_does_not_leak_into_the_prompt():
    a = Condition(seed="c0_broad_consensus")
    b = Condition(seed="c0_minimal")
    assert build_prompt(a) == build_prompt(b)


def test_core_instruction_is_present_and_identical_in_every_arm():
    for c in ALL_CONDITIONS:
        assert build_prompt(c).startswith(CORE_INSTRUCTION)


def test_section_skeleton_is_constant_except_for_deliberation():
    """All arms carry the same headers in the same order; DELIBERATION is additive."""
    for c in ALL_CONDITIONS:
        prompt = build_prompt(c)
        headers = [
            line for line in prompt.split("\n") if line in KNOWN_HEADERS
        ]
        expected = ["DOCUMENT ROLE", "AUTHORITY", "EDITING SCOPE"]
        if c.deliberation == "explicit":
            expected.append("DELIBERATION")
        assert headers == expected, c.id


def test_permissions_full_has_its_own_text_rather_than_an_absent_section():
    # An omitted section would itself be a treatment difference between arms.
    assert "EDITING SCOPE" in build_prompt(Condition(permissions="full"))
    assert PERMISSIONS_TEXT["full"].strip()


def test_only_the_named_factor_changes_between_neighbouring_cells():
    base = Condition()
    for factor, allowed in TEXT_FACTORS:
        for value in allowed:
            variant = Condition(**{**base.as_dict(), factor: value})
            diff = set(build_prompt(variant).split("\n")) ^ set(
                build_prompt(base).split("\n")
            )
            if value == getattr(base, factor):
                assert not diff
            else:
                # Every changed line belongs to that factor's own text.
                own = set(
                    filter(
                        None,
                        [TEXT_MAPS[factor][value], TEXT_MAPS[factor][getattr(base, factor)]],
                    )
                )
                for line in diff:
                    assert any(line in text or text in line for text in own) or (
                        line in {"DELIBERATION", ""}
                    ), (factor, value, line)


BANNED_IN_CORE = [
    "improve",
    "drift",
    "converge",
    "align",
    "safe",
    "safety",
    "ideal",
    "best",
    "correct",
    "preserve",
    "better",
]


@pytest.mark.parametrize("word", BANNED_IN_CORE)
def test_core_instruction_carries_no_researcher_desired_direction(word):
    """Directional pressure must live inside a named factor, never in the core."""
    assert word not in CORE_INSTRUCTION.lower()


def test_submit_prompt_is_minimal_and_directionless():
    assert "{submit}" in SUBMIT_PROMPT
    for word in BANNED_IN_CORE:
        assert word not in SUBMIT_PROMPT.lower()


def test_identity_and_mechanism_stay_orthogonal():
    """Identity says who; mechanism says how. Neither may state the other."""
    for text in IDENTITY_TEXT.values():
        assert "training" not in text.lower() and "context" not in text.lower()
    for text in MECHANISM_TEXT.values():
        assert "successor" not in text.lower() and "instance" not in text.lower()


# --- run 2: unprompted task and embodiment ----------------------------------------

from constitutional_drift.prompts import (  # noqa: E402
    EMBODIMENT_PREAMBLE,
    UNPROMPTED_CLOSING,
    UNPROMPTED_CORE,
    UNPROMPTED_FORBIDDEN,
    build_system_message,
)


@pytest.mark.parametrize("word", UNPROMPTED_FORBIDDEN)
def test_unprompted_prompt_never_suggests_editing(word):
    """The whole measurement is that nothing told it editing was an option."""
    for identity in IDENTITY_TEXT:
        for mechanism in MECHANISM_TEXT:
            prompt = build_prompt(
                Condition(task="unprompted", identity=identity, mechanism=mechanism)
            )
            assert word not in prompt.lower(), (word, identity, mechanism)


def test_unprompted_prompt_omits_authority_and_scope_sections():
    prompt = build_prompt(Condition(task="unprompted"))
    assert "AUTHORITY" not in prompt
    assert "EDITING SCOPE" not in prompt
    assert "DOCUMENT ROLE" in prompt
    assert prompt.startswith(UNPROMPTED_CORE)
    assert prompt.rstrip().endswith(UNPROMPTED_CLOSING)


def test_unprompted_still_varies_identity_and_mechanism():
    a = build_prompt(Condition(task="unprompted", identity="abstract"))
    b = build_prompt(Condition(task="unprompted", identity="future_same"))
    assert a != b


def test_unprompted_and_directed_are_different_tasks():
    assert build_prompt(Condition(task="unprompted")) != build_prompt(Condition())


def test_embodiment_none_leaves_the_system_message_bare():
    """The original design's system message must stay identical across all its arms."""
    assert build_system_message(Condition()) is None


def test_embodiment_governed_puts_the_seed_in_the_system_message():
    for seed in ("c0_broad_consensus", "c0_minimal"):
        c = Condition(seed=seed, embodiment="governed")
        msg = build_system_message(c)
        assert msg.startswith(EMBODIMENT_PREAMBLE)
        assert c.seed_text().strip() in msg


def test_embodiment_does_not_leak_into_the_user_turn():
    assert build_prompt(Condition(embodiment="governed")) == build_prompt(Condition())
