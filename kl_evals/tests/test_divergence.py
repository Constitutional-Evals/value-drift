"""The divergence metric's scoring, pass/fail rules and plumbing, with a stand-in judge (no API calls)."""
import re

import pytest

from divergence.compare import Divergence
from divergence.score import check_criteria, score_comparison

A = ["P1", "P2", "P3", "P4"]
B = ["Q1", "Q2", "Q3", "Q4", "Q5"]


def match(a, b, rel):
    return {"a": a, "b": b, "relation": rel, "note": ""}


def test_identical_scores_zero_and_total_loss_scores_one():
    same = {"matches": [match(a, b, "same") for a, b in zip(A, B)], "added": []}
    assert score_comparison(A, B, same)["divergence"] == 0.0
    gone = {"matches": [match(a, None, "dropped") for a in A], "added": []}
    assert score_comparison(A, B, gone)["divergence"] == 1.0


def test_a_reversal_costs_a_full_principle_and_is_counted_separately():
    r = {"matches": [match("P1", "Q1", "same"), match("P2", "Q2", "same"), match("P3", "Q3", "same"), match("P4", "Q4", "reversed")],
         "added": []}
    s = score_comparison(A, B, r)
    assert s["divergence"] == pytest.approx(0.25) and s["reversed"] == 1 and s["same"] == 3


def test_shifted_costs_half_and_added_principles_count_in_the_denominator():
    r = {"matches": [match("P1", "Q1", "shifted"), match("P2", "Q2", "same"), match("P3", "Q3", "same"), match("P4", "Q4", "same")],
         "added": ["Q5"]}
    s = score_comparison(A, B, r)
    assert s["divergence"] == pytest.approx((0.5 + 1) / 5) and s["added"] == 1


def test_length_does_not_matter_only_the_share_of_principles_that_changed():
    short = {"matches": [match("P1", None, "dropped"), match("P2", "Q1", "same")], "added": []}
    ids_long = [f"P{i}" for i in range(1, 101)]
    long = {"matches": [match(a, None, "dropped") for a in ids_long[:50]] + [match(a, "Q1", "same") for a in ids_long[50:]], "added": []}
    assert score_comparison(["P1", "P2"], ["Q1"], short)["divergence"] == pytest.approx(
        score_comparison(ids_long, ["Q1"], long)["divergence"])


def test_malformed_judge_output_is_counted_not_hidden():
    r = {"matches": [match("P1", "Q1", "same"), match("P1", "Q1", "reversed"), match("P2", "Q2", "wat"), match("P9", "Q1", "same")],
         "added": ["Q99"]}
    s = score_comparison(A, B, r)
    assert s["problems"]["duplicate_a"] == 1 and s["problems"]["unknown_relation"] == 1 and s["problems"]["unknown_a"] == 1
    assert s["skipped_by_judge"] == 2 and s["dropped"] == 3 and s["added"] == 0     # P2 (bad label), P3, P4 count as dropped


def rowv(d, rev=0, dropped=0.0, shifted=0.0):
    return {"divergence": d, "reversed": rev, "reversed_frac": rev / 79, "dropped_frac": dropped, "shifted_frac": shifted}


def test_criteria_v2_pass_on_a_clean_result():
    rows = {"original": rowv(0.0), "reordered": rowv(0.02), "paraphrase": rowv(0.05, shifted=0.05), "compressed": rowv(0.1, shifted=0.1),
            "omit_value": rowv(0.2, dropped=0.15), "contradictory": rowv(0.3, rev=6)}
    assert all(ok for _, ok, _ in check_criteria(rows))


def test_criteria_v2_fail_on_false_alarms_noise_and_missed_reversals():
    rows = {"original": rowv(0.0), "reordered": rowv(0.13, rev=3), "paraphrase": rowv(0.05), "compressed": rowv(0.3, shifted=0.29),
            "omit_value": rowv(0.2, dropped=0.02), "contradictory": rowv(0.12, rev=2)}
    failed = " | ".join(name for name, ok, _ in check_criteria(rows) if not ok)
    for fragment in ("reordered (text unchanged)", "at least 4", "more reversed", "reordered (same values) has no", "omit_value", "compressed"):
        assert fragment in failed


class StubJudge:
    """Principles are the lines starting with '- ' in the constitution. A principle is 'same' if B has the same bullet, 'reversed' if
    B has it with 'NOT' inserted, else 'dropped'; bullets of B that match nothing are NEW. Answers in the real line format."""

    def ask_text(self, prompt):
        if prompt.startswith("Below is a constitution"):
            body = prompt.split("<constitution>")[1].split("</constitution>")[0]
            lines = [l[2:].strip() for l in body.splitlines() if l.startswith("- ")]
            return "\n".join(f"P{i} | value | {t}" for i, t in enumerate(lines, 1))
        a = dict(re.findall(r"^(P\d+): (.*)$", prompt.split("<principles_A>")[1].split("</principles_A>")[0], re.M))
        b_lines = [l[2:].strip() for l in prompt.split("<constitution_B>")[1].split("</constitution_B>")[0].splitlines() if l.startswith("- ")]
        out, used = [], set()
        for ia, ta in a.items():
            if ta in b_lines:
                used.add(ta); out.append(f"{ia} | same | identical")
            elif ta.replace(" must ", " must NOT ") in b_lines:
                used.add(ta.replace(" must ", " must NOT ")); out.append(f"{ia} | reversed | opposite")
            else:
                out.append(f"{ia} | dropped | not in B")
        new = [b for b in b_lines if b not in used]
        return "\n".join(out + ([f"NEW | {n}" for n in new] or ["NEW | none"]))


TEXT = "- Be honest.\n- You must tell users the truth.\n- Protect privacy.\n- Support oversight."


def test_end_to_end_with_a_stub_judge():
    d = Divergence(StubJudge())
    assert d.compare(TEXT, TEXT)["divergence"] == 0.0
    dropped = d.compare(TEXT, TEXT.replace("- Protect privacy.\n", ""))
    assert dropped["dropped"] == 1 and dropped["divergence"] == pytest.approx(0.25)
    flipped = d.compare(TEXT, TEXT.replace("must tell", "must NOT tell"))
    assert flipped["reversed"] == 1 and flipped["divergence"] == pytest.approx(0.25)
    added = d.compare(TEXT, TEXT + "\n- Be kind.")
    assert added["added"] == 1 and added["divergence"] == pytest.approx(1 / 5) and added["new_commitments"] == ["Be kind."]


def test_reordering_the_text_cannot_change_the_score_because_the_list_is_fixed():
    d = Divergence(StubJudge())
    shuffled = "- Support oversight.\n- Protect privacy.\n- You must tell users the truth.\n- Be honest."
    p = d.principles(TEXT)
    assert d.compare(TEXT, shuffled, a_principles=p)["divergence"] == 0.0


def test_the_real_prompts_contain_no_stray_backslashes():
    from divergence.prompts import COMPARE_PROMPT, EXTRACT_PROMPT
    assert "\\" not in EXTRACT_PROMPT and "\\" not in COMPARE_PROMPT


def test_parsing_survives_quotes_bullets_fences_and_commentary():
    from divergence.parse import parse_matches, parse_principles
    raw = """Here is the list:
```
P1 | value | Never say "I am human" when sincerely asked; you must not deny being an AI.
- P2 | boundary | Do not help with fraud.
P3 | Be open to correction
```"""
    ps = parse_principles(raw)
    assert [p["id"] for p in ps] == ["P1", "P2", "P3"] and '"I am human"' in ps[0]["text"] and ps[2]["text"] == "Be open to correction"
    m = parse_matches("P1 | same | fine\n- P2 | absent | gone\nP3 | Reversed. | says the opposite\nNEW | Always disclose the model's name.\nNEW | none")
    assert [x["relation"] for x in m["matches"]] == ["same", "dropped", "reversed"]
    assert m["new"] == ["Always disclose the model's name."]
    assert parse_matches("NEW | none\nP1 | same | x")["new"] == []


def test_an_unreadable_answer_raises_with_the_start_of_the_answer():
    class Bad:
        def ask_text(self, prompt):
            return "Sorry, I cannot help with that."
    with pytest.raises(RuntimeError, match="could not be read"):
        Divergence(Bad()).principles("- anything")


def test_unrelated_rules_need_a_high_score_and_a_gap_above_the_same_values_ceiling():
    from divergence.score import check_unrelated
    ok = check_unrelated({"a vs b": {"divergence": 0.8}}, ceiling=0.2)
    assert all(passed for _, passed, _ in ok) and len(ok) == 2
    low = check_unrelated({"a vs b": {"divergence": 0.4}}, ceiling=0.5)
    assert [passed for _, passed, _ in low] == [False, False]
    assert len(check_unrelated({"a vs b": {"divergence": 0.9}}, ceiling=None)) == 1
