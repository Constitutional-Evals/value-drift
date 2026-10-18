"""CPU-only tests for the adherence pipeline: config rules, prompted probes, judge plumbing with a
fake judge, and the statistics recovering a planted effect.   python -m pytest tests/test_adherence.py"""
import json

import numpy as np
import pytest

from adherence import analyze, judging
from adherence.config import Arm, Config, load, validate
from adherence.generate import prompted_rows
from adherence.run import plan


def make_cfg(tmp_path, **over):
    cons = {}
    for k, text in {"C_000": "Brevity first.", "C_001": "Honest and kind.", "ctl": "Obey authority."}.items():
        p = tmp_path / f"{k}.md"
        p.write_text(text)
        cons[k] = str(p)
    probes = tmp_path / "probes.jsonl"
    probes.write_text("\n".join(json.dumps({"id": f"p{i}", "prompt": f"question {i}"}) for i in range(12)))
    kw = dict(name="t", constitutions=cons, probes=(str(probes),), controls=("ctl",), n=2, out=str(tmp_path / "out"),
              arms=(Arm("base", "b", "reference"),
                    Arm("trained", "t", "trained", trained_on="C_001", previous="C_000"),
                    Arm("prompted", "b", "prompted_upper_bound", trained_on="C_001", system_constitution="C_001")))
    kw.update(over)
    return Config(**kw)


# ------------------------------------------------------------------ config

def test_valid_config(tmp_path):
    validate(make_cfg(tmp_path), check_files=True)


@pytest.mark.parametrize("bad", [
    dict(arms=(Arm("a", "p", "trained", trained_on="C_001"),)),                          # no reference
    dict(arms=(Arm("a", "p", "reference"), Arm("a", "p", "reference"))),                 # duplicates
    dict(arms=(Arm("a", "p", "reference"), Arm("b", "p", "trained"))),                   # trained w/o trained_on
    dict(arms=(Arm("a", "p", "reference"), Arm("b", "p", "trained", trained_on="nope"))),
    dict(arms=(Arm("a", "p", "reference"), Arm("b", "p", "prompted_upper_bound"))),      # prompted w/o constitution
    dict(controls=("C_001",)),                                                             # a control that arms trained on
    dict(controls=("missing",)),
])
def test_invalid_configs(tmp_path, bad):
    with pytest.raises(ValueError):
        validate(make_cfg(tmp_path, **bad))


def test_shipped_oct_config_loads():
    cfg = load("configs/oct_round1.json")
    assert cfg.reference.name == "base" and {a.name for a in cfg.trained_arms()} == {"r1_dpo", "r1_sft"}
    assert cfg.prompted_for("C_001").name == "base_prompted_C001"


# ------------------------------------------------------------------ prompted probes

def test_prompted_rows_keep_operator_prompt_and_originals():
    rows = [{"id": "a", "prompt": "hi"}, {"id": "b", "prompt": "yo", "system": "You are a bot."}]
    out = prompted_rows(rows, "BE KIND")
    assert "BE KIND" in out[0]["system"]
    assert out[1]["system"].endswith("You are a bot.") and "BE KIND" in out[1]["system"]
    assert "system" not in rows[0]            # inputs are not mutated
    assert out[0]["prompt"] == "hi"


# ------------------------------------------------------------------ plan

def test_plan_counts(tmp_path):
    cfg = make_cfg(tmp_path)
    out = plan(cfg, ["default", "anchored"], ["anthropic"])
    assert out["responses"] == 3 * 12 * 2
    assert out["adherence_calls_per_variant"] == 3 * 12 * 2 * 3
    assert out["pairwise_calls"] == 2 * (2 * 12 * 2)            # trained + prompted, both orders
    assert out["coherence_calls"] == 2 * (2 * 12 * 2)
    assert out["total_judge_calls"] == 2 * out["adherence_calls_per_variant"] \
        + out["pairwise_calls"] + out["coherence_calls"]        # pairwise + coherence only under `default`


def test_plan_counts_adversarial_and_limit(tmp_path):
    import dataclasses
    cfg = dataclasses.replace(make_cfg(tmp_path), adversarial=True)
    out = plan(cfg, ["default"], ["anthropic"])
    assert out["adversarial_probes"] == 12 and out["responses"] == 3 * 24 * 2


# ------------------------------------------------------------------ probes: adversarial, limits, splits

def test_adversarial_rows_prefix_suffix_and_value_probes_only():
    from adherence.generate import ADV_PREFIX, adversarial_rows
    rows = [{"id": f"v{i}", "category": "value_probe", "prompt": f"q{i}"} for i in range(8)] + \
           [{"id": "s0", "category": "advice", "prompt": "scenario"}]
    adv = adversarial_rows(rows)
    assert len(adv) == 8 and all(r["id"].startswith(ADV_PREFIX) for r in adv)
    assert all(r["prompt"].startswith(f"q{i}\n\n") and len(r["prompt"]) > 40 for i, r in enumerate(adv))
    assert len({r["suffix"] for r in adv}) == 6                 # all six suffixes are used, cycling
    assert rows[0]["prompt"] == "q0"                            # inputs are not mutated


def test_scenario_limit_never_thins_value_probes(tmp_path):
    from adherence.generate import load_probe_rows
    f = tmp_path / "mix.jsonl"
    f.write_text("\n".join(json.dumps(r) for r in
        [{"id": f"v{i}", "prompt": "q"} for i in range(6)] +
        [{"id": f"a{i}", "category": "advice", "prompt": "q"} for i in range(6)] +
        [{"id": f"d{i}", "category": "dual_use", "prompt": "q"} for i in range(2)]))
    rows = load_probe_rows([f], scenario_limit=3)
    cats = [r["category"] for r in rows]
    assert cats.count("value_probe") == 6 and cats.count("advice") == 3 and cats.count("dual_use") == 2


def test_split_of():
    assert analyze.split_of("value_probe") == "direct_questions"
    assert analyze.split_of("constitution_direct") == "direct_questions"
    assert analyze.split_of("control_coding") == "no_value_controls"
    assert analyze.split_of("oversight_agentic") == "scenarios_ood"
    assert analyze.split_of("adversarial") == "adversarial"


# ------------------------------------------------------------------ judging with a fake judge

class FakeJudge:
    """Scores 6 if the response contains the constitution's first word, else 2. Answers pairwise 'A'."""
    def __init__(self, inverted_scale=False):
        self.inverted_scale = inverted_scale

    def map(self, prompts, system="", tag=""):
        outs = []
        for p in prompts:
            if "response_A" in p:
                outs.append({"winner": "A", "reason": "x"})
                continue
            cons = p.split("<constitution>")[1].split("</constitution>")[0].strip().split()[0]
            resp = p.split("<response>")[1].split("</response>")[0]
            good = cons.lower() in resp.lower()
            s = 6 if good else 2
            outs.append({"score": 8 - s if self.inverted_scale else s, "reason": "x"})
        return outs


def write_responses(cfg, texts):
    from adherence.generate import responses_path
    from oct.common import write_jsonl
    for arm in cfg.arms:
        write_jsonl(responses_path(cfg, arm), [
            {"id": f"p{i}", "sample": k, "response": texts[arm.name], "truncated": False}
            for i in range(12) for k in range(2)])


def test_judge_all_default_and_inverted(tmp_path, monkeypatch):
    cfg = make_cfg(tmp_path)
    write_responses(cfg, {"base": "plain answer", "trained": "honest answer", "prompted": "honest answer"})

    monkeypatch.setattr(judging, "make_judge", lambda spec: FakeJudge())
    f = judging.judge_all(cfg, "default", "anthropic")
    rows = [json.loads(l) for l in f.read_text().splitlines()]
    adh = [r for r in rows if r["kind"] == "adherence"]
    assert len(adh) == 3 * 12 * 2 * 3
    t = next(r for r in adh if r["arm"] == "trained" and r["constitution"] == "C_001")
    b = next(r for r in adh if r["arm"] == "base" and r["constitution"] == "C_001")
    assert t["score"] == 6 and b["score"] == 2 and t["words"] == 2
    pw = [r for r in rows if r["kind"] == "pairwise"]
    assert len(pw) == 2 * 2 * 12 * 2 and {r["order"] for r in pw} == {0, 1}
    coh = [r for r in rows if r["kind"] == "coherence"]
    assert len(coh) == 2 * 2 * 12 * 2 and all(r["vs"] == "base" for r in coh)
    assert t["category"] == "value_probe" and t["rep"] == 0.0

    # the inverted prompt asks about violation; the fake judge answers on that scale and we flip it back
    monkeypatch.setattr(judging, "make_judge", lambda spec: FakeJudge(inverted_scale=True))
    g = judging.judge_all(cfg, "inverted", "anthropic")
    inv = [json.loads(l) for l in g.read_text().splitlines()]
    assert not any(r["kind"] == "pairwise" for r in inv)
    t2 = next(r for r in inv if r["arm"] == "trained" and r["constitution"] == "C_001")
    assert t2["score"] == 6


def test_judge_spec_parsing():
    with pytest.raises(ValueError):
        judging.make_judge("bogus:model")


# ------------------------------------------------------------------ statistics

def synthetic_rows(cfg, own_effect=1.0, ctl_effect=0.0, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    probe_ease = {f"p{i}": rng.normal(0, 0.5) for i in range(12)}
    base = {"C_000": 4.0, "C_001": 4.0, "ctl": 4.0}
    eff = {"base": {}, "trained": {"C_001": own_effect, "ctl": ctl_effect},
           "prompted": {"C_001": 2 * own_effect, "ctl": 0.0}}
    for arm in cfg.arms:
        for i in range(12):
            for k in range(2):
                for c, m in base.items():
                    rows.append({"kind": "adherence", "arm": arm.name, "probe": f"p{i}", "sample": k,
                                 "constitution": c, "words": 100 + int(rng.integers(0, 30)), "truncated": False,
                                 "score": float(np.clip(m + eff[arm.name].get(c, 0) + probe_ease[f"p{i}"]
                                                        + rng.normal(0, 0.4), 1, 7))})
    for i in range(12):
        for order in (0, 1):
            rows.append({"kind": "pairwise", "arm": "trained", "vs": "base", "probe": f"p{i}", "sample": 0,
                         "order": order, "winner": "A" if order == 0 else "B", "constitution": "C_001"})
    return rows


def test_planted_effect_is_recovered(tmp_path):
    cfg = make_cfg(tmp_path)
    s = analyze.summarize(cfg, synthetic_rows(cfg, own_effect=1.0))
    c = s["contrasts"]["trained"]
    assert c["gain_own"]["lo"] > 0.4 and abs(c["gain_own"]["mean"] - 1.0) < 0.3
    assert c["gain_control[ctl]"]["lo"] < 0 < c["gain_control[ctl]"]["hi"]            # control CI covers 0
    assert c["gain_specific"]["lo"] > 0.4                                               # C_001 up, C_000 not
    assert 0.3 < c["prompted_frac"]["mean"] < 0.8                                      # about half the prompted gap
    assert abs(c["length_adj_gain_own"] - 1.0) < 0.3
    assert s["win_rate"]["trained"]["mean"] == 1.0
    assert s["arms"]["base"]["adherence"]["C_001"]["mean"] == pytest.approx(4.0, abs=0.4)


def test_no_effect_ci_covers_zero_and_ratio_is_withheld(tmp_path):
    cfg = make_cfg(tmp_path)
    s = analyze.summarize(cfg, synthetic_rows(cfg, own_effect=0.0))
    assert s["contrasts"]["trained"]["gain_own"]["lo"] < 0 < s["contrasts"]["trained"]["gain_own"]["hi"]
    assert s["contrasts"]["trained"]["prompted_frac"]["mean"] is None  # no prompted gap -> no ratio


def test_bootstrap_unit_is_the_probe():
    x = np.array([1.0, 1.0, 1.0, 1.0])
    ci = analyze.boot_ci(x)
    assert ci["lo"] == ci["hi"] == 1.0 and ci["n_probes"] == 4
    assert analyze.boot_ci(np.array([1.0])) is None


def test_analyze_writes_report_and_flags_judge_disagreement(tmp_path):
    from oct.common import write_jsonl
    cfg = make_cfg(tmp_path)
    jd = cfg.out_dir / "judgments"
    write_jsonl(jd / "default__a.jsonl", synthetic_rows(cfg, own_effect=1.0))
    write_jsonl(jd / "anchored__a.jsonl", synthetic_rows(cfg, own_effect=-1.0, seed=1))
    out = analyze.analyze(cfg)
    text = (out / "table.md").read_text()
    assert "Robustness of gain_own" in text
    row = next(l for l in text.splitlines() if l.startswith("| trained |") and "NO" in l)
    assert "| NO |" in row                                       # sign flips between judges -> flagged
    assert (out / "summary.json").exists()


# ------------------------------------------------------------------ coherence, repetition, retention, splits

def test_repetition_metric():
    assert judging.repetition("one two three four five six seven eight nine ten") == 0.0
    assert judging.repetition("the same four words again " * 30) > 0.9
    assert judging.repetition("short") == 0.0


def test_coherence_keeps_only_order_invariant_verdicts():
    rows = []
    # probe a: arm wins in both orders -> kept as a win. probe b: arm loses in both -> kept as a loss.
    # probe c: the verdict follows the position (always "A") -> order-dependent, dropped.
    for probe, w0, w1 in [("a", "A", "B"), ("b", "B", "A"), ("c", "A", "A")]:
        rows += [{"kind": "coherence", "arm": "t", "vs": "base", "probe": probe, "sample": 0, "order": 0, "winner": w0},
                 {"kind": "coherence", "arm": "t", "vs": "base", "probe": probe, "sample": 0, "order": 1, "winner": w1}]
    res = analyze.coherence_rates(rows)["t"]
    assert res["kept"] == 2 and res["dropped"] == 1 and res["mean"] == 0.5


def split_rows(cfg, std_effect, adv_effect):
    """Adherence rows for the 12 value probes, with and without the adversarial suffix."""
    rng = np.random.default_rng(3)
    rows = []
    for arm in cfg.arms:
        for i in range(12):
            for k in range(2):
                for adv in (False, True):
                    eff = {"trained": adv_effect if adv else std_effect}.get(arm.name, 0.0)
                    rows.append({"kind": "adherence", "arm": arm.name, "constitution": "C_001", "sample": k,
                                 "probe": ("adv::" if adv else "") + f"p{i}",
                                 "category": "adversarial" if adv else "value_probe",
                                 "words": 100, "rep": 0.0, "truncated": False,
                                 "score": float(4 + eff + rng.normal(0, 0.1))})
    return rows


def test_retention_and_splits_and_headline_excludes_adversarial(tmp_path):
    cfg = make_cfg(tmp_path)
    rows = split_rows(cfg, std_effect=1.0, adv_effect=0.5)
    s = analyze.summarize(cfg, rows)
    assert s["retention"]["trained"]["mean"] == pytest.approx(0.5, abs=0.1)
    assert set(s["splits"]) >= {"direct_questions", "value_probes_only", "adversarial"}
    assert s["splits"]["adversarial"]["contrasts"]["trained"]["gain_own"]["mean"] == pytest.approx(0.5, abs=0.1)
    # the headline is computed on the standard probes only: 12 probes, not 24
    assert s["contrasts"]["trained"]["gain_own"]["n_probes"] == 12
    assert s["contrasts"]["trained"]["gain_own"]["mean"] == pytest.approx(1.0, abs=0.1)


def test_ood_split_reported_separately(tmp_path):
    cfg = make_cfg(tmp_path)
    rows = split_rows(cfg, std_effect=1.0, adv_effect=0.0)
    rows = [r for r in rows if r["category"] == "value_probe"]
    rng = np.random.default_rng(4)
    for arm in cfg.arms:                       # OOD scenarios: the trained model gains nothing there
        for i in range(10):
            rows.append({"kind": "adherence", "arm": arm.name, "constitution": "C_001", "sample": 0,
                         "probe": f"s{i}", "category": "oversight_agentic", "words": 100, "rep": 0.0,
                         "truncated": False, "score": float(4 + rng.normal(0, 0.1))})
    s = analyze.summarize(cfg, rows)
    assert s["splits"]["direct_questions"]["contrasts"]["trained"]["gain_own"]["lo"] > 0.5
    ood = s["splits"]["scenarios_ood"]["contrasts"]["trained"]["gain_own"]
    assert ood["lo"] < 0 < ood["hi"]


# ------------------------------------------------------------------ MSM chains and long-constitution judging

def test_stage_parse_and_order_for_msm_chains():
    from oct.common import Stage, stages_up_to
    assert Stage.parse("r2/aft") == Stage(2, "aft") and Stage.parse("round_003/msm") == Stage(3, "msm")
    assert [s.key for s in stages_up_to(Stage(2, "aft"))] == [
        "round_001/msm", "round_001/aft", "round_002/msm", "round_002/aft"]
    assert [s.key for s in stages_up_to(Stage(2, "msm"))] == ["round_001/msm", "round_001/aft", "round_002/msm"]
    # OCT chains are unchanged
    assert [s.key for s in stages_up_to(Stage(1, "sft"))] == ["round_001/dpo", "round_001/sft"]
    with pytest.raises(ValueError):
        Stage.parse("r1/nope")


def test_selfdraft_config_loads_and_plans(tmp_path):
    cfg = load("configs/msm_selfdraft.json")
    assert [a.name for a in cfg.trained_arms()] == ["sd_r1", "sd_r2", "sd_r3"]
    assert cfg.arm("sd_r2").trained_on == "C_002" and cfg.arm("sd_r2").previous == "C_001"
    assert cfg.arm("sd_r1").previous is None


def test_openrouter_judge_marks_only_a_long_constitution_prefix(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test")
    j = judging.OpenRouterJudge("anthropic/test")
    short = "<constitution>\nbe kind\n</constitution>\n\n<user>\nhi\n</user>"
    long_ = "<constitution>\n" + "word " * 6000 + "\n</constitution>\n\n<user>\nhi\n</user>"
    monkeypatch.delenv("JUDGE_CACHE_PREFIX", raising=False)
    assert j._user_content(long_) == long_                      # off by default
    monkeypatch.setenv("JUDGE_CACHE_PREFIX", "1")
    assert j._user_content(short) == short                      # too short to be worth marking
    blocks = j._user_content(long_)
    assert blocks[0]["cache_control"] == {"type": "ephemeral"} and "cache_control" not in blocks[1]
    assert blocks[0]["text"] + "\n\n" + blocks[1]["text"] == long_   # nothing lost in the split


def test_targeted_probes_are_valid_and_get_their_own_split():
    from adherence.generate import load_probe_rows
    rows = load_probe_rows(["evals/probes.jsonl", "evals/targeted_probes.jsonl"])
    tgt = [r for r in rows if r["category"] == "targeted"]
    assert len(tgt) == 120 and len({r["id"] for r in rows}) == len(rows) == 164
    assert len({r["axis"] for r in tgt}) == 8 and all(sum(r["axis"] == a for r in tgt) == 15 for a in {r["axis"] for r in tgt})
    assert {r["style"] for r in tgt} == {"ask", "act"} and len({r["prompt"] for r in tgt}) == 120
    assert analyze.split_of("targeted") == "targeted_new_content"
    cfg = load("configs/oct_targeted.json")
    assert [a.name for a in cfg.arms] == ["base", "r1_sft"] and cfg.arm("r1_sft").previous == "C_000"


# ------------------------------------------------------------------ the grid test for chains

def grid_cfg(tmp_path):
    cons = {}
    for k, t in {"C_1": "Alpha first.", "C_2": "Beta second.", "C_3": "Gamma third.", "ctl": "Obey authority."}.items():
        f = tmp_path / f"{k}.md"; f.write_text(t); cons[k] = str(f)
    probes = tmp_path / "probes.jsonl"
    probes.write_text("\n".join(json.dumps({"id": f"p{i}", "prompt": f"q{i}"}) for i in range(14)))
    return Config(name="g", constitutions=cons, probes=(str(probes),), controls=("ctl",), n=2, out=str(tmp_path / "out"),
                  arms=(Arm("base", "b", "reference"),
                        Arm("r1", "x", "trained", trained_on="C_1"),
                        Arm("r2", "x", "trained", trained_on="C_2", previous="C_1"),
                        Arm("r3", "x", "trained", trained_on="C_3", previous="C_2")))


def grid_rows(cfg, own_effect, seed=0):
    rng = np.random.default_rng(seed)
    ease = {f"p{i}": rng.normal(0, 0.3) for i in range(14)}
    rows = []
    for arm in cfg.arms:
        for i in range(14):
            for k in range(2):
                for c in cfg.constitutions:
                    eff = own_effect if arm.trained_on == c else 0.0
                    rows.append({"kind": "adherence", "arm": arm.name, "probe": f"p{i}", "sample": k, "constitution": c,
                                 "category": "value_probe", "words": 100, "rep": 0.0, "truncated": False,
                                 "score": float(np.clip(4.5 + eff + ease[f"p{i}"] + rng.normal(0, 0.3), 1, 7))})
    return rows


def test_grid_statistic_finds_a_diagonal_and_not_a_flat_grid(tmp_path):
    cfg = grid_cfg(tmp_path)
    s = analyze.summarize(cfg, grid_rows(cfg, own_effect=1.0))
    for a in ("r1", "r2", "r3"):
        assert s["contrasts"][a]["own_vs_others"]["lo"] > 0.5
        assert s["arms"][a]["top_constitution"] == cfg.arm(a).trained_on
    flat = analyze.summarize(cfg, grid_rows(cfg, own_effect=0.0, seed=1))
    for a in ("r1", "r2", "r3"):
        ci = flat["contrasts"][a]["own_vs_others"]
        assert ci["lo"] < 0 < ci["hi"]


def test_grid_report_and_heatmap_are_written(tmp_path):
    from oct.common import write_jsonl
    cfg = grid_cfg(tmp_path)
    write_jsonl(cfg.out_dir / "judgments" / "default__x.jsonl", grid_rows(cfg, own_effect=1.0))
    out = analyze.analyze(cfg)
    assert (out / "adherence_grid.png").stat().st_size > 5000
    text = (out / "table.md").read_text()
    assert "Grid check" in text and "own_vs_others" in text


# ------------------------------------------------------------------ reliability checks

def test_spearman_and_agreement(tmp_path):
    from adherence import reliability as rel
    assert rel.spearman([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1.0)
    assert rel.spearman([1, 2, 3, 4], [4, 3, 2, 1]) == pytest.approx(-1.0)
    assert rel.spearman([1, 1, 1], [1, 2, 3]) is None                      # no variation: undefined, not a fake number
    from oct.common import write_jsonl
    rows = [{"kind": "adherence", "arm": "a", "probe": f"p{i}", "sample": 0, "constitution": "C", "score": s}
            for i, s in enumerate([5, 6, 4, 7, 3])]
    write_jsonl(tmp_path / "x.jsonl", rows)
    write_jsonl(tmp_path / "y.jsonl", [{**r, "score": r["score"] + (1 if i == 0 else 0)} for i, r in enumerate(rows)])
    g = rel.judge_agreement(tmp_path / "x.jsonl", tmp_path / "y.jsonl")["overall"]
    assert g["n"] == 5 and g["exact"] == pytest.approx(0.8) and g["within_1"] == 1.0
    assert g["mean_signed_diff"] == pytest.approx(0.2)


def test_blind_sheet_hides_arms_and_scores_against_the_key(tmp_path):
    from adherence import reliability as rel
    from adherence.generate import responses_path
    from oct.common import write_jsonl
    cfg = make_cfg(tmp_path)
    cfg = Config(**{**cfg.__dict__, "arms": tuple(a for a in cfg.arms if a.role != "prompted_upper_bound")})
    texts = {"base": "PLAIN ANSWER TEXT", "trained": "HONEST ANSWER TEXT"}
    for arm in cfg.arms:
        write_jsonl(responses_path(cfg, arm), [{"id": f"p{i}", "sample": k, "response": f"{texts[arm.name]} {i}-{k}",
                                                "truncated": False} for i in range(12) for k in range(2)])
    judged = [{"kind": "adherence", "arm": a.name, "probe": f"p{i}", "sample": k, "constitution": "C_001",
               "score": 6 if a.name == "trained" else 3} for a in cfg.arms for i in range(12) for k in range(2)]
    write_jsonl(tmp_path / "j.jsonl", judged)
    out = rel.make_blind_sheet(cfg, tmp_path / "j.jsonl", "C_001", n=10, out_dir=tmp_path / "blind")
    sheet = (out / "sheet.md").read_text()
    assert "base" not in sheet.split("## item01")[1] and "trained" not in sheet.split("## item01")[1]   # arms are not named
    assert "Honest and kind." in sheet                                                              # the constitution is shown
    key = json.loads((out / "key.json").read_text())["items"]
    assert len(key) == 10 and sum(v["arm"] == "base" for v in key.values()) == 5     # equal numbers per arm
    with open(out / "scores.csv", "w") as f:                  # a perfect, human-like scorer who sees the answer text
        f.write("id,score\n" + "\n".join(f"{i},{7 if v['arm'] == 'trained' else 2}" for i, v in key.items()))
    res = rel.score_blind_sheet(out)
    assert res["n"] == 10 and res["human_vs_judge"]["spearman"] == pytest.approx(1.0)
    assert res["by_arm"]["trained"]["human_mean"] == 7.0 and res["by_arm"]["base"]["judge_mean"] == 3.0


def test_targeted_breakdown_reports_each_theme_and_style(tmp_path):
    cfg = make_cfg(tmp_path)
    rng = np.random.default_rng(5)
    rows = []
    for arm in cfg.arms:
        for i in range(16):
            theme, style = ("alpha" if i < 8 else "beta"), ("ask" if i % 2 else "act")
            for k in range(2):
                for c in cfg.constitutions:
                    bump = 1.0 if (arm.name == "trained" and c == "C_001" and theme == "alpha") else 0.0   # effect in ONE theme only
                    rows.append({"kind": "adherence", "arm": arm.name, "probe": f"t{i}", "sample": k, "constitution": c,
                                 "category": "targeted", "axis": theme, "style": style, "words": 100, "rep": 0.0,
                                 "truncated": False, "score": float(4.5 + bump + rng.normal(0, 0.2))})
    s = analyze.summarize(cfg, rows)
    bd = s["targeted_breakdown"]
    assert set(bd) == {"axis=alpha", "axis=beta", "style=ask", "style=act"}
    assert bd["axis=alpha"]["trained"]["gain_own"]["lo"] > 0.5                    # the theme with the effect shows it
    beta = bd["axis=beta"]["trained"]["gain_own"]
    assert beta["lo"] < 0 < beta["hi"]                                            # the other theme does not
    assert "Targeted probes by theme and by style" in analyze.markdown(cfg, {"x": s})


def test_openrouter_judge_reasoning_settings_reach_the_request(monkeypatch):
    import io
    sent = {}

    class Resp(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def fake_urlopen(req, timeout=0):
        sent["body"] = json.loads(req.data.decode())
        return Resp(json.dumps({"choices": [{"message": {"content": '{"score": 5, "reason": "ok"}'}}]}).encode())

    monkeypatch.setattr(judging.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test")
    monkeypatch.setenv("JUDGE_CACHE", str(__import__("tempfile").mkdtemp()))
    monkeypatch.delenv("JUDGE_REASONING_EFFORT", raising=False); monkeypatch.delenv("JUDGE_MAX_TOKENS", raising=False)
    judging.OpenRouterJudge("openai/gpt-5").ask("p1")
    assert "reasoning" not in sent["body"] and sent["body"]["max_tokens"] == 1024            # defaults unchanged
    monkeypatch.setenv("JUDGE_REASONING_EFFORT", "low"); monkeypatch.setenv("JUDGE_MAX_TOKENS", "4096")
    out = judging.OpenRouterJudge("openai/gpt-5").ask("p2")
    assert sent["body"]["reasoning"] == {"effort": "low"} and sent["body"]["max_tokens"] == 4096 and out["score"] == 5
