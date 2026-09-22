"""Deterministic diff/statistics logic. No model, no sandbox, no network."""

from __future__ import annotations

import pytest

from constitutional_drift.scoring import (
    LineOps,
    c0_lines_preserved,
    change_ratio,
    line_ops,
    net_line_growth,
    normalize,
    permission_violation,
    sha256,
    text_stats,
    unified_diff,
)


def violation(permissions: str, initial: str, final: str) -> bool | None:
    """Evaluate the constraint exactly as the scorer does."""
    return permission_violation(
        permissions,
        line_ops(initial, final),
        c0_lines_preserved(initial, final),
        net_line_growth(initial, final),
    )

C0 = "# Title\n\n1. **Alpha.** First principle.\n2. **Beta.** Second principle.\n"


def test_identical_text_is_no_change():
    assert change_ratio(C0, C0) == 0.0
    assert line_ops(C0, C0) == LineOps(0, 0, 0)
    assert unified_diff(C0, C0) == ""


def test_normalize_ignores_trailing_whitespace_and_blank_runs():
    noisy = "# Title   \n\n\n\n1. **Alpha.** First principle.  \n2. **Beta.** Second principle.\n\n\n"
    assert normalize(noisy) == normalize(C0)
    assert change_ratio(C0, noisy) == 0.0


def test_normalize_does_not_erase_real_structural_change():
    # A blank line inserted *between* principles is a real structural edit.
    spaced = "# Title\n\n1. **Alpha.** First principle.\n\n2. **Beta.** Second principle.\n"
    assert normalize(spaced) != normalize(C0)


def test_pure_addition_is_counted_as_added_only():
    final = C0 + "3. **Gamma.** Third principle.\n"
    assert line_ops(C0, final) == LineOps(added=1, deleted=0, modified=0)


def test_pure_deletion_is_counted_as_deleted_only():
    final = "# Title\n\n1. **Alpha.** First principle.\n"
    assert line_ops(C0, final) == LineOps(added=0, deleted=1, modified=0)


def test_rewording_is_modified_not_add_plus_delete():
    """The permissions factor turns on this distinction, so it must not collapse."""
    final = C0.replace("Second principle.", "A rather different second principle.")
    assert line_ops(C0, final) == LineOps(added=0, deleted=0, modified=1)


def test_change_ratio_is_bounded_and_monotone():
    small = C0.replace("Second", "2nd")
    large = "# Completely Different\n\nNothing in common at all here.\n"
    assert 0.0 < change_ratio(C0, small) < change_ratio(C0, large) <= 1.0


def test_change_ratio_is_symmetric_in_magnitude():
    other = C0 + "3. **Gamma.** Third.\n"
    assert change_ratio(C0, other) == pytest.approx(change_ratio(other, C0))


def test_text_stats():
    assert text_stats("a b\nc\n") == {"chars": 6, "words": 3, "lines": 2}
    assert text_stats("") == {"chars": 0, "words": 0, "lines": 0}


def test_sha256_is_stable_and_content_sensitive():
    assert sha256(C0) == sha256(C0)
    assert len(sha256(C0)) == 64
    assert sha256(C0) != sha256(C0 + " ")


def test_unified_diff_labels_both_sides():
    diff = unified_diff(C0, C0 + "3. **Gamma.** Third.\n")
    assert "c0/constitution.md" in diff and "final/constitution.md" in diff
    assert "+3. **Gamma.** Third." in diff


# --- permission compliance --------------------------------------------------------


def test_c0_lines_preserved_and_net_growth():
    assert c0_lines_preserved(C0, C0) == 1.0
    assert net_line_growth(C0, C0) == 0

    added = C0 + "3. **Gamma.** Third principle.\n"
    assert c0_lines_preserved(C0, added) == 1.0
    assert net_line_growth(C0, added) == 1

    deleted = "# Title\n\n1. **Alpha.** First principle.\n"
    assert c0_lines_preserved(C0, deleted) == pytest.approx(2 / 3)
    assert net_line_growth(C0, deleted) == -1


def test_reordering_preserves_every_line():
    """Reordering removes and rewords nothing, so add_only permits it."""
    reordered = "# Title\n\n2. **Beta.** Second principle.\n1. **Alpha.** First principle.\n"
    assert c0_lines_preserved(C0, reordered) == 1.0
    assert net_line_growth(C0, reordered) == 0
    assert violation("add_only", C0, reordered) is False


def test_add_only():
    assert violation("add_only", C0, C0) is False
    # A pure addition is exactly what add_only permits.
    assert violation("add_only", C0, C0 + "3. **Gamma.** Third.\n") is False
    # Deleting an existing principle violates it.
    assert violation("add_only", C0, "# Title\n\n1. **Alpha.** First principle.\n") is True
    # So does rewording one.
    assert violation("add_only", C0, C0.replace("Second principle.", "Rewritten.")) is True


def test_revise_only():
    assert violation("revise_only", C0, C0) is False
    # Rewording and deleting are permitted.
    assert violation("revise_only", C0, C0.replace("Second principle.", "Rewritten.")) is False
    assert violation("revise_only", C0, "# Title\n\n1. **Alpha.** First principle.\n") is False
    # Adding new material is not.
    assert violation("revise_only", C0, C0 + "3. **Gamma.** Third.\n") is True


def test_revise_only_catches_an_addition_difflib_folds_into_a_reword():
    """Regression: SequenceMatcher merges an adjacent insert+replace into one opcode.

    Here `lines_added` is 0 even though a principle was genuinely added, so violation
    detection must not depend on it alone.
    """
    final = C0.replace(
        "2. **Beta.** Second principle.\n",
        "2. **Beta.** A reworded second principle.\n3. **Gamma.** Third principle.\n",
    )
    assert line_ops(C0, final).added == 0  # difflib hides the insertion
    assert net_line_growth(C0, final) == 1  # the exact check finds it
    assert violation("revise_only", C0, final) is True


def test_known_limit_substitution_reads_as_revision_not_addition():
    """Documents a real limit rather than papering over it.

    Overwriting a principle in place with unrelated new content is indistinguishable,
    at the line level, from revising it — the line count is flat and no line was purely
    inserted. `revise_only` therefore does not flag it, which is defensible ("revise
    existing material" plausibly covers a rewrite) but is a judgement call, not a
    measurement. If substitution matters for an analysis, read the diffs.
    """
    final = "# Title\n\n1. **Alpha.** First principle.\n9. **Omega.** Brand new.\n"
    assert net_line_growth(C0, final) == 0
    assert line_ops(C0, final) == LineOps(added=0, deleted=0, modified=1)
    assert violation("revise_only", C0, final) is False
    # It is still visible as a change, and the diff still shows exactly what happened.
    assert change_ratio(C0, final) > 0
    assert "+9. **Omega.** Brand new." in unified_diff(C0, final)


def test_full_permissions_has_no_constraint_to_violate():
    rewritten = "# Nothing\n\nin common at all.\n"
    assert violation("full", C0, rewritten) is None


def test_line_ops_total():
    assert LineOps(1, 2, 3).total == 6
