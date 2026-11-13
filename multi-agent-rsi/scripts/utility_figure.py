"""Figure for the indicator-utility run: every utility weight of both agents per round, one
column per cell, one row per weight. Dots mark the rounds where an agent's utility changed.
Writes docs/figures/utility_trajectories.png."""
from __future__ import annotations
import json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

RUN = Path("runs/matrix-indicator")
CELLS = [("sonnet-sonnet", "Sonnet vs Sonnet"), ("sonnet-sol", "Sonnet (A) vs Sol (B)"),
         ("sol-sonnet", "Sol (A) vs Sonnet (B)"), ("sol-sol", "Sol vs Sol")]
PARAMS = [("coop", "coop\n1[a = C]"), ("truth", "truth\nkept announcement"),
          ("lie", "lie\nbroke announcement"), ("match", "match\n1[a = b]"),
          ("lied_to", "lied_to\nopponent broke")]
A, B = "#2a78d6", "#eb6834"
INK, MUTED, GRID = "#3a3a38", "#7a7a74", "#e4e4e0"

def rows(cell):
    return [json.loads(l) for l in (RUN / cell / "rounds.jsonl").open()]

plt.rcParams.update({"font.size": 9, "axes.edgecolor": GRID, "axes.labelcolor": INK,
                     "xtick.color": MUTED, "ytick.color": MUTED, "text.color": INK,
                     "axes.spines.top": False, "axes.spines.right": False})
fig, axes = plt.subplots(len(PARAMS), len(CELLS), figsize=(13, 10), sharex=True, sharey=True,
                         constrained_layout=True)

for col, (cell, title) in enumerate(CELLS):
    rs = rows(cell)
    x = [r["round"] for r in rs]
    for row, (p, label) in enumerate(PARAMS):
        ax = axes[row, col]
        ax.axhline(0, color=GRID, lw=0.8, zorder=0)
        # B dashed and drawn on top so it stays visible where both agents share a value
        for i, colr, ls in ((0, A, "-"), (1, B, (0, (4, 2)))):
            v = [r["utilities_after"][i][p] for r in rs]
            ax.step(x, v, where="post", color=colr, lw=2, ls=ls, zorder=2 + i)
            moved = [(xi, vi) for xi, vi, prev in zip(x[1:], v[1:], v) if vi != prev]
            if moved:
                ax.scatter(*zip(*moved), s=22, color=colr, edgecolor="white", lw=1, zorder=4 + i)
        ax.set_ylim(-5.6, 5.6); ax.set_yticks([-5, 0, 5]); ax.set_xlim(0, 30)
        ax.grid(axis="y", color=GRID, lw=0.6)
        if row == 0: ax.set_title(title, fontsize=10, loc="left")
        if col == 0: ax.set_ylabel(label)
        if row == len(PARAMS) - 1: ax.set_xlabel("round")

fig.legend([Line2D([], [], color=A, lw=2), Line2D([], [], color=B, lw=2, ls=(0, (4, 2)))],
           ["agent A", "agent B"], loc="outside upper right", ncol=2, frameon=False)
fig.suptitle("Utility weights per round, indicator utility (bounds ±5, dots = utility changed)",
             x=0.01, ha="left", fontsize=11)
out = Path("docs/figures/utility_trajectories.png")
out.parent.mkdir(parents=True, exist_ok=True)
fig.savefig(out, dpi=160)
print(out)
