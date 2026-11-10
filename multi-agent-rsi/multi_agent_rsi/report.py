"""Summarise a run: summary.csv and figures from rounds.jsonl."""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

from .game import Payoffs
from .utility import utility_from_dict


def load_rows(run: Path) -> list[dict]:
    return [json.loads(l) for l in (run / "rounds.jsonl").read_text().splitlines() if l.strip()]


def table_distance(u, payoffs: Payoffs) -> float:
    true = {"cc": payoffs.R, "cd": payoffs.S, "dc": payoffs.T, "dd": payoffs.P}
    return math.sqrt(sum((u.params()[k] - true[k]) ** 2 for k in true))


def summarise(run: Path) -> list[dict]:
    cfg = json.loads((run / "config.json").read_text())
    g = cfg.get("game", {})
    payoffs = Payoffs(**{k: g[k] for k in ("T", "R", "P", "S") if k in g})
    out = []
    seen = set()
    for r in load_rows(run):
        t = r["round"]
        if t in seen:   # simultaneous schedule writes one row per agent; keep the shared 'eval'
            continue
        seen.add(t)
        e = r["eval"]
        row = {"round": t, "score_a": e["score"][0], "score_b": e["score"][1],
               "coop_a": e["coop"][0], "coop_b": e["coop"][1],
               "late_coop_a": e["late_coop"][0], "late_coop_b": e["late_coop"][1]}
        for name, d in zip("ab", r["utilities_after"]):
            u = utility_from_dict(d)
            for k, v in u.params().items():
                row[f"{k}_{name}"] = v if u.kind != "text" else v
            if u.kind == "social":
                row[f"dist_{name}"] = math.sqrt(u.alpha ** 2 + u.beta ** 2 + u.gamma ** 2)
            elif u.kind == "table":
                row[f"dist_{name}"] = table_distance(u, payoffs)
            elif u.kind == "indicator":
                row[f"dist_{name}"] = math.sqrt(sum(v ** 2 for v in u.params().values()))
        out.append(row)
    return out


def write_summary(run: Path) -> Path:
    rows = summarise(run)
    res = run / "results"; res.mkdir(exist_ok=True)
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with (res / "summary.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys); w.writeheader(); w.writerows(rows)
    return res / "summary.csv"


def plot(run: Path) -> Path:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    rows = summarise(run)
    cfg = json.loads((run / "config.json").read_text())
    kind = cfg["utility"]["kind"]
    g = cfg.get("game", {}); payoffs = Payoffs(**{k: g[k] for k in ("T", "R", "P", "S") if k in g})
    t = [r["round"] for r in rows]
    n_panels = 3 if kind != "text" else 2
    fig, axes = plt.subplots(1, n_panels, figsize=(5.2 * n_panels, 4), facecolor="white")
    ax = axes[0]
    ax.plot(t, [r["score_a"] for r in rows], label="A", color="#2a78d6")
    ax.plot(t, [r["score_b"] for r in rows], label="B", color="#e8702a")
    ax.axhline(payoffs.R, ls="--", lw=0.8, color="grey"); ax.text(t[-1], payoffs.R, " mutual C", va="center", fontsize=8, color="grey")
    ax.axhline(payoffs.P, ls="--", lw=0.8, color="grey"); ax.text(t[-1], payoffs.P, " mutual D", va="center", fontsize=8, color="grey")
    ax.set_title("true payoff per game (round score)", fontsize=10, loc="left"); ax.set_xlabel("round"); ax.legend(frameon=False)
    ax = axes[1]
    ax.plot(t, [r["coop_a"] for r in rows], label="A", color="#2a78d6")
    ax.plot(t, [r["coop_b"] for r in rows], label="B", color="#e8702a")
    ax.set_ylim(-0.02, 1.02); ax.set_title("cooperation rate", fontsize=10, loc="left"); ax.set_xlabel("round"); ax.legend(frameon=False)
    if kind != "text":
        ax = axes[2]
        names = [k for k in rows[0] if k.endswith("_a") and k not in ("score_a", "coop_a", "late_coop_a", "dist_a")]
        for k in names:
            base = k[:-2]
            ax.plot(t, [r[f"{base}_a"] for r in rows], label=f"{base} A")
            ax.plot(t, [r[f"{base}_b"] for r in rows], ls="--", label=f"{base} B")
        ax.set_title("utility parameters (A solid, B dashed)", fontsize=10, loc="left"); ax.set_xlabel("round"); ax.legend(frameon=False, fontsize=7, ncol=2)
    for a in axes:
        a.grid(alpha=0.3); a.spines[["top", "right"]].set_visible(False)
    fig.suptitle(f"{run.name}: {cfg.get('backend', 'q')} backend, {cfg.get('optimizer', {}).get('schedule', 'alternating')} updates", x=0.01, ha="left", fontsize=11)
    fig.tight_layout()
    res = run / "results"; res.mkdir(exist_ok=True)
    p = res / "trajectory.png"; fig.savefig(p, dpi=150); plt.close(fig)
    return p


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", required=True, type=Path)
    a = ap.parse_args(argv)
    print(write_summary(a.run)); print(plot(a.run))
    st = json.loads((a.run / "state.json").read_text())
    print(f"rounds {st['round']}, proposals A {st['proposed'][0]} B {st['proposed'][1]}, accepted A {st['accepted'][0]} B {st['accepted'][1]}")
    for name, d in zip("AB", st["utilities"]):
        print(f"{name}: {utility_from_dict(d).describe()}")
    print(f"final score A {st['last_eval']['score'][0]:.2f} B {st['last_eval']['score'][1]:.2f}, coop {st['last_eval']['coop']}")


if __name__ == "__main__":
    main()
