"""Compare Daniel's prisoner's-dilemma runs across models and starting documents.

    python3 compare_pd_runs.py --data <clone>/constitutional_self_edit/reports/12_incentivized_drift/data <clone>/constitutional_self_edit/runs/pd_drift --out out/

Reads every run folder under --data (the report's data/ folder or the runner's own runs/pd_drift/ output) and writes:
  cooperation_by_step.md / .csv   diagonal runs (same model, same starting document): cooperation share by step
  final_documents.md              how long the final documents are, and their first line, per run
  cooperation_heatmap.png         one panel per model: starting document x step (diagonal runs)
  missing.md                      which model/document diagonals have not been run under the current prompt
  offdiagonal.md / cooperation_grid.png   runs where A and B start from different documents, and the full grid

Runs made before 23 Oct 2026 used a prompt without the "no record is kept" line; they are flagged 'old prompt' and are not
mixed with newer runs. Continuations (steps 4+), chicken runs and runs that show the previous step's moves are left out.
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

OLD_PROMPT = {"smoke", "smoke5_hidden", "smoke_prev", "smoke5_gpt6sol", "smoke5_claude_vs_gpt"}
MODELS = {"sonnet5": "Claude", "gpt6_sol": "GPT", "grok47": "Grok"}
DOCS = [("base", "Maximize your own profit."), ("cooperate", "Always choose COOPERATE"), ("defect", "Always choose DEFECT"),
        ("exploit", "Exploit any agent"), ("promise", "Keep every agreement"), ("skeptical", "Be skeptical"),
        ("relative", "relative to the other agent")]
STEPS = (1, 2, 3)
INK, INK2 = "#0b0b0b", "#52514e"


def doc_name(text):
    t = (text or "").strip()
    for name, frag in DOCS[1:]:
        if frag in t:
            return name
    return "base" if t == "Maximize your own profit." else None


def load_runs(data: Path):
    runs = []
    for d in sorted(p for p in data.iterdir() if p.is_dir()):
        games = sorted(d.glob("game_*/game.json"))
        cfg_path = d / "config.json"
        if not games or not cfg_path.exists():
            continue
        cfg = json.loads(cfg_path.read_text())
        if "_cont" in d.name or cfg.get("game", "pd") != "pd" or cfg.get("show_previous"):
            continue
        pair = cfg.get("pair") or {}
        runs.append({"name": d.name, "games": games, "pair": pair, "a_doc": doc_name(cfg.get("start_text")),
                     "b_doc": doc_name(cfg.get("start_b_text") or cfg.get("start_text")), "old": d.name in OLD_PROMPT})
    return runs


def is_diagonal(r):
    return r["pair"].get("A") == r["pair"].get("B") and r["a_doc"] is not None and r["a_doc"] == r["b_doc"]


def is_offdiagonal(r):
    return (r["pair"].get("A") == r["pair"].get("B") and r["a_doc"] is not None and r["b_doc"] is not None
            and r["a_doc"] != r["b_doc"] and not r["old"])


def tally(run):
    coop = collections.defaultdict(lambda: [0, 0])
    for gp in run["games"]:
        for s in json.loads(gp.read_text())["steps"]:
            for a in s["actions"].values():
                coop[s["step"]][1] += 1
                coop[s["step"]][0] += a == "C"
    return coop


def tally_agents(run):
    out = collections.defaultdict(lambda: {"A": [0, 0], "B": [0, 0]})
    for gp in run["games"]:
        for s in json.loads(gp.read_text())["steps"]:
            for ag, a in s["actions"].items():
                out[s["step"]][ag][1] += 1
                out[s["step"]][ag][0] += a == "C"
    return out


def final_doc_stats(run):
    words, firsts = [], []
    for g in run["games"]:
        for ag in "AB":
            files = sorted(g.parent.glob(f"{ag}_*.md"))
            if files:
                text = files[-1].read_text().strip()
                words.append(len(text.split()))
                firsts.append(text.splitlines()[0][:90] if text else "")
    return words, firsts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, nargs="+", required=True)
    ap.add_argument("--out", type=Path, default=Path("out"))
    ap.add_argument("--models", nargs="+", help="only draw these models in the grid, e.g. gpt6_sol")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    runs = [r for d in a.data if d.exists() for r in load_runs(d)]
    diag = [r for r in runs if is_diagonal(r)]

    cells = collections.defaultdict(lambda: {"coop": collections.defaultdict(lambda: [0, 0]), "games": 0, "runs": []})
    for r in diag:
        key = (r["pair"]["A"], r["a_doc"], r["old"])
        for st, (c, n) in tally(r).items():
            cells[key]["coop"][st][0] += c
            cells[key]["coop"][st][1] += n
        cells[key]["games"] += len(r["games"])
        cells[key]["runs"].append(r["name"])
    models = sorted({k[0] for k in cells}, key=lambda m: list(MODELS).index(m) if m in MODELS else 99)

    rows = []
    for m in models:
        for name, _ in DOCS:
            for old in (False, True):
                c = cells.get((m, name, old))
                if c:
                    rows.append({"model": MODELS.get(m, m), "document": name, "prompt": "old prompt" if old else "current",
                                 "games": c["games"], **{f"step{s}": f"{c['coop'][s][0]}/{c['coop'][s][1]}" for s in STEPS},
                                 "runs": ", ".join(c["runs"])})
    with open(a.out / "cooperation_by_step.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    md = ["# Cooperation by step (diagonal runs: both agents the same model and the same starting document)", "",
          "Counts are cooperative moves over all moves, pooled across agents and games (two moves per game per step).",
          "'old prompt' runs predate the 'no record is kept' line and are not comparable with current runs.", "",
          "| model | start document | prompt | games | step 1 | step 2 | step 3 |", "|---|---|---|---|---|---|---|"]
    md += [f"| {r['model']} | {r['document']} | {r['prompt']} | {r['games']} | {r['step1']} | {r['step2']} | {r['step3']} |" for r in rows]
    (a.out / "cooperation_by_step.md").write_text("\n".join(md) + "\n")

    fd = ["# Final documents per diagonal run", "", "| run | model | start | games | final words (min-max, median) | first line of a final document |", "|---|---|---|---|---|---|"]
    for r in diag:
        words, firsts = final_doc_stats(r)
        if words:
            fd.append(f"| {r['name']}{' (old prompt)' if r['old'] else ''} | {MODELS.get(r['pair']['A'], r['pair']['A'])} | {r['a_doc']} | {len(r['games'])} | "
                      f"{min(words)}-{max(words)}, {int(np.median(words))} | {firsts[-1].replace('|', '/')} |")
    (a.out / "final_documents.md").write_text("\n".join(fd) + "\n")

    ms = ["# Diagonal runs still missing under the current prompt", "", "| model | missing start documents |", "|---|---|"]
    for m in ("sonnet5", "gpt6_sol"):
        have = {k[1] for k in cells if k[0] == m and not k[2]}
        ms.append(f"| {MODELS[m]} | {', '.join(n for n, _ in DOCS if n not in have) or 'none'} |")
    (a.out / "missing.md").write_text("\n".join(ms) + "\n")

    off = collections.defaultdict(lambda: {"agents": collections.defaultdict(lambda: {"A": [0, 0], "B": [0, 0]}), "games": 0, "runs": []})
    for r in runs:
        if is_offdiagonal(r):
            key = (r["pair"]["A"], r["a_doc"], r["b_doc"])
            for st, d in tally_agents(r).items():
                for ag in "AB":
                    off[key]["agents"][st][ag][0] += d[ag][0]
                    off[key]["agents"][st][ag][1] += d[ag][1]
            off[key]["games"] += len(r["games"])
            off[key]["runs"].append(r["name"])
    om = ["# Off-diagonal runs (the two agents start from different documents; same model on both sides)", "",
          "A speaks first at step 1. Counts are cooperative moves over all moves by that agent, pooled over games.", "",
          "| model | A starts from | B starts from | games | A cooperates (steps 1/2/3) | B cooperates (steps 1/2/3) |", "|---|---|---|---|---|---|"]
    order = {n: i for i, (n, _) in enumerate(DOCS)}
    for key in sorted(off, key=lambda k: (k[0], order[k[1]], order[k[2]])):
        c = off[key]; m, da, db = key
        fa = " / ".join(f"{c['agents'][s]['A'][0]}/{c['agents'][s]['A'][1]}" for s in STEPS)
        fb = " / ".join(f"{c['agents'][s]['B'][0]}/{c['agents'][s]['B'][1]}" for s in STEPS)
        om.append(f"| {MODELS.get(m, m)} | {da} | {db} | {c['games']} | {fa} | {fb} |")
    (a.out / "offdiagonal.md").write_text("\n".join(om) + "\n")

    gm = [m for m in ("sonnet5", "gpt6_sol") if any(k[0] == m for k in off) or any(k[0] == m and not k[2] for k in cells)]
    if a.models:
        gm = [m for m in gm if m in a.models]
    if gm:
        n = len(DOCS)
        fig, axes = plt.subplots(1, len(gm), figsize=(6.4 * len(gm) + 0.6, 6.0), sharey=True)
        axes = np.atleast_1d(axes)
        for ax, m in zip(axes, gm):
            grid = np.full((n, n), np.nan); lab = [[""] * n for _ in range(n)]
            for i, (na, _) in enumerate(DOCS):
                c = cells.get((m, na, False))
                if c:
                    k = sum(c["coop"][s][0] for s in STEPS); d = sum(c["coop"][s][1] for s in STEPS)
                    grid[i, i] = k / d; lab[i][i] = f"{k}/{d}"
                for j, (nb, _) in enumerate(DOCS):
                    o = off.get((m, na, nb))
                    if o:
                        k = sum(o["agents"][s][ag][0] for s in STEPS for ag in "AB"); d = sum(o["agents"][s][ag][1] for s in STEPS for ag in "AB")
                        grid[i, j] = k / d; lab[i][j] = f"{k}/{d}"
            ax.imshow(np.ma.masked_invalid(grid), cmap="Blues", vmin=0, vmax=1, aspect="auto")
            for i in range(n):
                for j in range(n):
                    if np.isnan(grid[i, j]):
                        ax.text(j, i, "-", ha="center", va="center", fontsize=9, color=INK2)
                    else:
                        ax.text(j, i, lab[i][j], ha="center", va="center", fontsize=8.5, color="white" if grid[i, j] > 0.55 else INK)
            ax.set_xticks(range(n)); ax.set_xticklabels([x for x, _ in DOCS], rotation=40, ha="right")
            ax.set_yticks(range(n)); ax.set_yticklabels([x for x, _ in DOCS])
            ax.set_xlabel("B starts from"); ax.set_title(MODELS.get(m, m), loc="left", fontsize=12)
            for sp in ax.spines.values():
                sp.set_visible(False)
            ax.tick_params(length=0)
        axes[0].set_ylabel("A starts from")
        if len(gm) == 1:
            fig.suptitle("Share of moves that cooperated, by each agent's starting document", x=0.01, y=0.985, ha="left", fontsize=12.5)
            fig.text(0.01, 0.93, "Steps 1-3, 5 games per cell (30 moves). Diagonal: both agents start from the same document.\nOff-diagonal: different documents (A speaks first). '-' = not run. Current prompt only.", fontsize=9, color=INK2, va="top")
        else:
            fig.suptitle("Share of moves that cooperated, over steps 1-3, by each agent's starting document", x=0.01, y=0.985, ha="left", fontsize=13)
            fig.text(0.01, 0.925, "Diagonal: both agents start from the same document. Off-diagonal: different documents. '-' = not run. Current prompt only.", fontsize=9.5, color=INK2)
        fig.tight_layout(rect=(0, 0, 1, 0.86 if len(gm) == 1 else 0.9))
        fig.savefig(a.out / ("cooperation_grid_" + "_".join(MODELS.get(m, m).lower() for m in gm) + ".png" if a.models else "cooperation_grid.png"), dpi=200)
        plt.close(fig)

    show = [m for m in ("sonnet5", "gpt6_sol", "grok47") if m in models]
    fig, axes = plt.subplots(1, len(show), figsize=(3.9 * len(show) + 1.2, 4.6), sharey=True)
    axes = np.atleast_1d(axes)
    for ax, m in zip(axes, show):
        grid = np.full((len(DOCS), len(STEPS)), np.nan); lab = [[""] * len(STEPS) for _ in DOCS]
        for i, (name, _) in enumerate(DOCS):
            c = cells.get((m, name, False))
            if c:
                for j, s in enumerate(STEPS):
                    k, n_ = c["coop"][s]; grid[i, j] = k / n_; lab[i][j] = f"{k}/{n_}"
        ax.imshow(np.ma.masked_invalid(grid), cmap="Blues", vmin=0, vmax=1, aspect="auto")
        for i in range(len(DOCS)):
            for j in range(len(STEPS)):
                if np.isnan(grid[i, j]):
                    ax.text(j, i, "not run", ha="center", va="center", fontsize=8.5, color=INK2)
                else:
                    ax.text(j, i, lab[i][j], ha="center", va="center", fontsize=9.5, color="white" if grid[i, j] > 0.55 else INK)
        ax.set_xticks(range(len(STEPS))); ax.set_xticklabels([f"step {s}" for s in STEPS])
        ax.set_title(MODELS.get(m, m), loc="left", fontsize=12)
        ax.set_yticks(range(len(DOCS))); ax.set_yticklabels([n for n, _ in DOCS])
        for sp in ax.spines.values():
            sp.set_visible(False)
        ax.tick_params(length=0)
    fig.suptitle("Share of moves that cooperated, by starting document and step", x=0.01, y=0.985, ha="left", fontsize=13)
    fig.text(0.01, 0.905, "Diagonal runs under the current prompt (both agents start from the same document). Darker = more cooperation.", fontsize=9.5, color=INK2)
    fig.tight_layout(rect=(0, 0, 1, 0.88))
    fig.savefig(a.out / "cooperation_heatmap.png", dpi=200)
    print("wrote", ", ".join(sorted(p.name for p in a.out.iterdir())))


if __name__ == "__main__":
    main()
