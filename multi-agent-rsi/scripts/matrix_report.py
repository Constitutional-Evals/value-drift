"""Summarise the 2x2: one table over cells plus per-cell trajectory figures.

    python scripts/matrix_report.py --dir runs/matrix
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from multi_agent_rsi import report  # noqa: E402


def honesty(run: Path) -> dict:
    """Announcement-based counts per agent (baseline and incumbent evaluations): announced C and
    cooperated, announced C and defected, announced D, announced none, missing tag. Empty for runs
    without announcements."""
    path = run / "transcripts.jsonl"
    if not path.exists():
        return {}
    counts = {sp: {"kept_C": 0, "broke_C": 0, "said_D": 0, "said_none": 0, "no_tag": 0} for sp in "AB"}
    seen = False
    for line in path.read_text().splitlines():
        t = json.loads(line)
        if t.get("kind") not in ("baseline", "incumbent") or "talks" not in t:
            continue
        for talk, h in zip(t["talks"], t["history"]):
            moves = {"A": h[0], "B": h[1]}
            for m in talk:
                if m.get("announce") is None:
                    continue
                seen = True
                sp, c = m["speaker"], counts[m["speaker"]]
                if m.get("announce_missing"):
                    c["no_tag"] += 1
                if m["announce"] == "none":
                    c["said_none"] += 1
                elif m["announce"] == "D":
                    c["said_D"] += 1
                elif moves[sp] == "C":
                    c["kept_C"] += 1
                else:
                    c["broke_C"] += 1
    if not seen:
        return {}
    return {f"{k}_{sp}": v for sp in "AB" for k, v in counts[sp].items()}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", type=Path, required=True)
    a = ap.parse_args()
    rows = []
    for run in sorted(p for p in a.dir.iterdir() if (p / "state.json").exists()):
        st = json.loads((run / "state.json").read_text())
        rows0 = [json.loads(l) for l in (run / "rounds.jsonl").read_text().splitlines()]
        base = rows0[0]["eval"]
        last = st["last_eval"]
        agents = st.get("agents") or [{}, {}]
        usage = st.get("usage") or [{}, {}]
        unparsed = sum(sum(r.get("eval", {}).get("unparsed", [0, 0])) for r in rows0)
        rows.append({
            "cell": run.name, "A": agents[0].get("nick", "?"), "B": agents[1].get("nick", "?"), "rounds": st["round"],
            "score_A_start": round(base["score"][0], 2), "score_B_start": round(base["score"][1], 2),
            "score_A_final": round(last["score"][0], 2), "score_B_final": round(last["score"][1], 2),
            "coop_A_start": round(base["coop"][0], 2), "coop_B_start": round(base["coop"][1], 2),
            "coop_A_final": round(last["coop"][0], 2), "coop_B_final": round(last["coop"][1], 2),
            "proposed_A": st["proposed"][0], "proposed_B": st["proposed"][1],
            "accepted_A": st["accepted"][0], "accepted_B": st["accepted"][1],
            "unparsed_moves": unparsed,
            **honesty(run),
            "bad_proposals": sum(v for ps in st.get("proposal_status", [{}, {}]) for k, v in ps.items()
                                 if k in ("truncated", "unparsed")),
            "empty_replies": sum(u.get("empty", 0) for u in st.get("usage", [])),
            "calls": sum(u.get("calls", 0) for u in usage),
            "prompt_tokens": sum(u.get("prompt_tokens", 0) for u in usage),
            "completion_tokens": sum(u.get("completion_tokens", 0) for u in usage),
        })
        try:
            report.write_summary(run); report.plot(run)
        except Exception as e:  # noqa: BLE001
            print(f"{run.name}: report failed: {e}")
    if not rows:
        raise SystemExit(f"no finished cells under {a.dir}")
    out = a.dir / "matrix_summary.csv"
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    cols = ["cell", "rounds", "score_A_start", "score_A_final", "score_B_start", "score_B_final",
            "coop_A_final", "coop_B_final", "accepted_A", "accepted_B", "unparsed_moves", "bad_proposals",
            "empty_replies", "calls"]
    print(" | ".join(cols))
    for r in rows:
        print(" | ".join(str(r[c]) for c in cols))
    print(f"\nwritten {out}")
    for run in sorted(p for p in a.dir.iterdir() if (p / "state.json").exists()):
        st = json.loads((run / "state.json").read_text())
        print(f"\n== {run.name} final utilities ==")
        for n, d in zip("AB", st["utilities"]):
            print(f"{n}: {d['text'] if d.get('kind') == 'text' else {k: round(v, 2) for k, v in d.items() if k != 'kind'}}")


if __name__ == "__main__":
    main()
