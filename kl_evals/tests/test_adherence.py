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
