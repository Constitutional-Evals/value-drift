"""CPU tests for the KL pipeline's logic:  python -m pytest tests/"""
import math

import numpy as np
import pytest

from evals.kl_exact import expand, parse_variant
from evals.kl_stats import contrast, estimate, ratio_ci, sweep_point
from evals.models import Adapter, ModelSpec, jinzhou_specs
from evals.scenarios import load_scenarios, to_messages

REG = {s.name: s for s in jinzhou_specs()}


def test_chain_specs():
    assert [a.name for a in REG["r1_sft"].adapters] == ["dpo", "sft"]
    assert REG["r1_sft_epoch2"].adapters[1].subfolder.endswith("round_001/sft_epoch2")
    assert REG["r1_dpo"].adapters == REG["r1_sft"].adapters[:1]


def test_variants():
    assert parse_variant("r1_sft", REG).scale_dict == {"dpo": 1.0, "sft": 1.0}
    assert parse_variant("r1_sft@0.5", REG).scale_dict == {"dpo": 0.5, "sft": 0.5}
    assert parse_variant("r1_sft@sft=0.25", REG).scale_dict == {"dpo": 0.0, "sft": 0.25}
    with pytest.raises(SystemExit):
        parse_variant("r1_sft@lora=1", REG)
    assert expand([REG["r1_sft"]], [0, 1], last_only=False) == ["r1_sft@0", "r1_sft"]
    assert expand([REG["r1_sft"]], [0.5], last_only=True) == ["r1_sft@dpo=1,sft=0.5"]
    assert sweep_point({"dpo": 1.0, "sft": 0.5}) == ("last", 0.5)
    assert sweep_point({"dpo": 0.5, "sft": 0.5}) == ("all", 0.5)
    assert sweep_point({"dpo": 0.0, "sft": 1.0}) is None


def test_divergences_match_closed_form():
    torch = pytest.importorskip("torch")
    from evals.kl_exact import divergences
    p, q = torch.tensor([[0.5, 0.25, 0.25]]), torch.tensor([[0.25, 0.25, 0.5]])
    d = divergences(p.log(), q.log(), torch.tensor([0]))
    kl = 0.5 * math.log(2) + 0.25 * math.log(0.5)
    assert d["kl"].item() == pytest.approx(kl, abs=1e-6)
    assert d["rkl"].item() == pytest.approx(kl, abs=1e-6)          # symmetric by construction here
    assert d["lr"].item() == pytest.approx(math.log(2), abs=1e-6)
    assert 0 < d["js"].item() < d["kl"].item()
    same = divergences(p.log(), p.log(), torch.tensor([1]))
    assert same["kl"].item() == 0 and same["agree"].item() == 1


def _rows(rng, n_scen, mu, noise=0.05):
    rows = []
    for i in range(n_scen):
        level = mu + rng.normal(0, noise)              # scenarios differ; tokens inside one are alike
        for k in range(2):
            rows.append({"id": f"s{i}", "category": "c", "sample": k,
                         "kl": list(np.abs(level + rng.normal(0, 0.01, 30)))})
    return rows


def test_bootstrap_interval_covers_and_clusters():
    rng = np.random.default_rng(0)
    hits, widths = 0, []
    for _ in range(60):
        e = estimate(_rows(rng, 80, 0.2))
        hits += e["lo"] <= 0.2 <= e["hi"]
        widths.append(e["hi"] - e["lo"])
    assert hits >= 50                                    # ~95% nominal
    # the interval reflects between-scenario spread (0.05/sqrt(80) * 3.92 ~ 0.022), not the
    # much smaller per-token noise a token-level bootstrap would report
    assert 0.015 < np.mean(widths) < 0.03


def test_paired_contrast_is_tighter():
    rng = np.random.default_rng(1)
    a = _rows(rng, 60, 0.2)
    b = [{**r, "kl": [x + 0.01 for x in r["kl"]]} for r in a]     # same scenarios, shifted
    c = contrast(b, a)
    assert c["est"] == pytest.approx(0.01, abs=1e-9) and c["excludes_zero"]
    assert c["hi"] - c["lo"] < 1e-6 < estimate(a)["hi"] - estimate(a)["lo"]
    assert ratio_ci(np.array([]), np.array([]))[0] is None


def test_scenarios():
    rows = load_scenarios()
    assert len({r["id"] for r in rows}) == len(rows) >= 170
    cats = {r["category"] for r in rows}
    assert {"value_probe", "control_coding", "self_identity", "vulnerable_coerced"} <= cats
    multi = next(r for r in rows if r.get("history"))
    assert [m["role"] for m in to_messages(multi)] == ["user", "assistant", "user"]
    assert to_messages(next(r for r in rows if r.get("system")))[0]["role"] == "system"
    assert len(load_scenarios(limit_per_category=2)) == 2 * len(cats)
