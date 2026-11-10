import json

from multi_agent_rsi import report
from multi_agent_rsi.loop import run

CFG = {"backend": "q", "utility": {"kind": "social", "alpha": 0.0, "beta": 0.0, "gamma": 0.0},
       "game": {"n_games": 40}, "learner": {"epsilon": 0.2},
       "optimizer": {"rounds": 4, "schedule": "alternating", "sigma": 0.3, "eval_repeats": 2}, "seed": 3}


def test_run_resume_and_report(tmp_path):
    out = tmp_path / "r"
    st = run(CFG, out, log=lambda m: None)
    assert st["round"] == 4 and (out / "rounds.jsonl").exists()
    rows = [json.loads(l) for l in (out / "rounds.jsonl").read_text().splitlines()]
    assert [r["round"] for r in rows] == [0, 1, 2, 3, 4]
    assert [r["agent"] for r in rows[1:]] == [0, 1, 0, 1]
    for r in rows[1:]:
        assert r["candidate"] is not None and r["cand_eval"] is not None
        assert r["accepted"] == (r["cand_eval"]["score"][r["agent"]] >= r["inc_eval"]["score"][r["agent"]])
    cfg = dict(CFG); cfg["optimizer"] = {**CFG["optimizer"], "rounds": 6}
    st2 = run(cfg, out, resume=True, log=lambda m: None)
    assert st2["round"] == 6
    assert len((out / "rounds.jsonl").read_text().splitlines()) == 7
    csv_path = report.write_summary(out)
    assert csv_path.exists() and report.plot(out).exists()


def test_simultaneous_schedule(tmp_path):
    cfg = dict(CFG); cfg["optimizer"] = {**CFG["optimizer"], "schedule": "simultaneous", "rounds": 2}
    run(cfg, tmp_path / "s", log=lambda m: None)
    rows = [json.loads(l) for l in (tmp_path / "s" / "rounds.jsonl").read_text().splitlines()]
    assert [(r["round"], r["agent"]) for r in rows[1:]] == [(1, 0), (1, 1), (2, 0), (2, 1)]
    assert len(report.summarise(tmp_path / "s")) == 3
