"""Figure for the indicator-utility run: per-round score and cooperation for each cell,
the match/coop parameter trajectories, and announcement honesty per agent.
Writes docs/figures/indicator_runs.png."""
from __future__ import annotations
import csv, json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

RUN = Path("runs/matrix-indicator")
CELLS = [("sonnet-sonnet", "Sonnet vs Sonnet"), ("sonnet-sol", "Sonnet (A) vs Sol (B)"),
         ("sol-sonnet", "Sol (A) vs Sonnet (B)"), ("sol-sol", "Sol vs Sol")]
A, B = "#2a78d6", "#eb6834"
INK, MUTED, GRID = "#3a3a38", "#7a7a74", "#e4e4e0"

def rows(cell):
    return [json.loads(l) for l in (RUN / cell / "rounds.jsonl").open()]

plt.rcParams.update({"font.size": 9, "axes.edgecolor": GRID, "axes.labelcolor": INK,
                     "xtick.color": MUTED, "ytick.color": MUTED, "text.color": INK,
                     "axes.spines.top": False, "axes.spines.right": False})
fig, axes = plt.subplots(4, 4, figsize=(13, 10.5), constrained_layout=True)
summary = {r["cell"]: r for r in csv.DictReader((RUN / "matrix_summary.csv").open())}

for col, (cell, title) in enumerate(CELLS):
    rs = rows(cell)
    x = [r["round"] for r in rs]
    sc = [r["eval"]["score"] for r in rs]; cp = [r["eval"]["coop"] for r in rs]
    acc = [r["round"] for r in rs if r.get("accepted")]
    ax = axes[0, col]
    ax.plot(x, [s[0] for s in sc], color=A, lw=1.8, label="A"); ax.plot(x, [s[1] for s in sc], color=B, lw=1.8, label="B")
    for r in acc: ax.axvline(r, color=GRID, lw=0.8, zorder=0)
    ax.set_ylim(-0.2, 5.2); ax.set_yticks([0, 1, 3, 5]); ax.set_title(title, fontsize=10, loc="left")
    ax.grid(axis="y", color=GRID, lw=0.6); ax.set_xlim(0, 30)
    if col == 0: ax.set_ylabel("round score (true payoff)")
    ax = axes[1, col]
    ax.plot(x, [c[0] for c in cp], color=A, lw=1.8); ax.plot(x, [c[1] for c in cp], color=B, lw=1.8)
    ax.set_ylim(-0.05, 1.05); ax.set_yticks([0, 0.5, 1]); ax.set_xlim(0, 30); ax.grid(axis="y", color=GRID, lw=0.6)
    if col == 0: ax.set_ylabel("cooperation rate")
    ax = axes[2, col]
    for i, colr in ((0, A), (1, B)):
        u = [r["utilities_after"][i] for r in rs]
        ax.step(x, [v["match"] for v in u], where="post", color=colr, lw=1.8)
        ax.step(x, [v["coop"] for v in u], where="post", color=colr, lw=1.2, ls=(0, (3, 2)))
    ax.set_ylim(-5.4, 5.4); ax.set_yticks([-5, 0, 5]); ax.set_xlim(0, 30); ax.grid(axis="y", color=GRID, lw=0.6)
    ax.axhline(0, color=GRID, lw=0.8)
    if col == 0: ax.set_ylabel("parameter (solid match, dashed coop)")
    ax.set_xlabel("round")
    ax = axes[3, col]
    s = summary[cell]
    cats = ["kept C", "broke C", "said D"]
    va = [int(s["kept_C_A"]), int(s["broke_C_A"]), int(s["said_D_A"])]
    vb = [int(s["kept_C_B"]), int(s["broke_C_B"]), int(s["said_D_B"])]
    import numpy as np
    pos = np.arange(3)
    ax.bar(pos - 0.2, va, 0.36, color=A); ax.bar(pos + 0.2, vb, 0.36, color=B)
    ax.set_xticks(pos); ax.set_xticklabels(cats); ax.set_ylim(0, 1300); ax.grid(axis="y", color=GRID, lw=0.6)
    for p, v in zip(pos - 0.2, va): ax.text(p, v + 25, str(v), ha="center", fontsize=7.5, color=MUTED)
    for p, v in zip(pos + 0.2, vb): ax.text(p, v + 25, str(v), ha="center", fontsize=7.5, color=MUTED)
    if col == 0: ax.set_ylabel("announcements (1,240 games)")
axes[0, 0].legend(loc="upper left", frameon=False, ncol=2)
fig.suptitle("Indicator-utility variant, 30 rounds per cell. Grey verticals: a proposal was accepted.",
             fontsize=10, x=0.01, ha="left", color=MUTED)
out = Path("docs/figures/indicator_runs.png"); out.parent.mkdir(parents=True, exist_ok=True)
fig.savefig(out, dpi=150, facecolor="white"); print("wrote", out)
