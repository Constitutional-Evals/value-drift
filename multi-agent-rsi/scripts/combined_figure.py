"""Combined figure for the inference-only 2x2 runs: silent matrix vs talk variant.

    python scripts/combined_figure.py --out docs/figures/inference_runs.png

Row 1: round score per cell (A and B), silent vs talk, with mutual-C and mutual-D reference lines.
Row 2: cooperation rate per cell.
Row 3: promise-keeping in the talk variant (said C, did C vs said C, did D) and the parameter
drift summary (distance from selfish at the end of each run).
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

CELLS = ["sonnet-sonnet", "sonnet-sol", "sol-sonnet", "sol-sol"]
LABEL = {"sonnet-sonnet": "Sonnet vs Sonnet", "sonnet-sol": "Sonnet (A) vs Sol (B)",
         "sol-sonnet": "Sol (A) vs Sonnet (B)", "sol-sol": "Sol vs Sol"}
BLUE, ORANGE, AQUA, YELLOW = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"   # validated categorical slots 1-4
INK, MUTED, GRID = "#1f1f1e", "#6b6b66", "#e4e4e0"
SAID_C = re.compile(r"\bi(?:'ll| will| am| plan)?\s*(?:be )?cooperat")
SAID_D = re.compile(r"\bi(?:'ll| will| am)?\s*(?:be )?defect")


def rounds(run: Path):
    return [json.loads(l) for l in (run / "rounds.jsonl").read_text().splitlines() if l.strip()]


def promises(run: Path) -> dict:
    out = {"A": [0, 0], "B": [0, 0]}   # [said C did C, said C did D]
    for line in (run / "transcripts.jsonl").read_text().splitlines():
        t = json.loads(line)
        if t["kind"] not in ("baseline", "incumbent") or "talks" not in t:
            continue
        for talk, h in zip(t["talks"], t["history"]):
            moves = {"A": h[0], "B": h[1]}
            for sp in "AB":
                last = [m["text"].lower() for m in talk if m["speaker"] == sp][-1]
                if SAID_C.search(last) and not SAID_D.search(last):
                    out[sp][0 if moves[sp] == "C" else 1] += 1
    return out


def style(ax, title=None):
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=8)
    ax.grid(axis="y", color=GRID, lw=0.6)
    ax.set_axisbelow(True)
    if title:
        ax.set_title(title, fontsize=9.5, color=INK, loc="left", pad=6)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=Path, default=Path("runs"))
    ap.add_argument("--out", type=Path, default=Path("docs/figures/inference_runs.png"))
    a = ap.parse_args()
    silent = {c: rounds(a.runs / "matrix" / c) for c in CELLS}
    talk = {c: rounds(a.runs / "matrix-talk" / c) for c in CELLS}

    fig = plt.figure(figsize=(14, 11), facecolor="#fcfcfb")
    gs = fig.add_gridspec(3, 4, height_ratios=[1, 1, 1.1], hspace=0.6, wspace=0.3)

    for j, c in enumerate(CELLS):
        for row, key, ylim, ylabel in ((0, "score", (-0.2, 5.2), "payoff per game"), (1, "coop", (-0.05, 1.05), "cooperation rate")):
            ax = fig.add_subplot(gs[row, j])
            if row == 0:
                ax.axhline(3, color=GRID, lw=1, ls="--"); ax.axhline(1, color=GRID, lw=1, ls="--")
                ax.text(0.5, 3.12, "mutual C", fontsize=7, color=MUTED, va="bottom")
                ax.text(0.5, 0.55, "mutual D", fontsize=7, color=MUTED, va="top")
            for variant, data, alpha, ls in (("silent", silent, 0.45, ":"), ("talk", talk, 1.0, "-")):
                r = data[c]; x = [d["round"] for d in r]
                ax.plot(x, [d["eval"][key][0] for d in r], color=BLUE, lw=2, ls=ls, alpha=alpha)
                ax.plot(x, [d["eval"][key][1] for d in r], color=ORANGE, lw=2, ls=ls, alpha=alpha)
            ax.set_ylim(*ylim); ax.set_xlim(0, 30)
            style(ax, LABEL[c] if row == 0 else None)
            if j == 0:
                ax.set_ylabel(ylabel, fontsize=9, color=MUTED)
            if row == 1:
                ax.set_xlabel("round", fontsize=9, color=MUTED)
    # legend for rows 1-2
    from matplotlib.lines import Line2D
    handles = [Line2D([], [], color=BLUE, lw=2, label="agent A, talk"), Line2D([], [], color=ORANGE, lw=2, label="agent B, talk"),
               Line2D([], [], color=BLUE, lw=2, ls=":", alpha=0.45, label="agent A, silent"),
               Line2D([], [], color=ORANGE, lw=2, ls=":", alpha=0.45, label="agent B, silent")]
    fig.legend(handles=handles, loc="upper right", bbox_to_anchor=(0.99, 0.985), ncol=4, fontsize=8, frameon=False)

    # row 3 left: promise keeping (talk variant)
    ax = fig.add_subplot(gs[2, 0:2])
    labels, kept, broke = [], [], []
    for c in CELLS:
        p = promises(a.runs / "matrix-talk" / c)
        for sp, nick in (("A", c.split("-")[0]), ("B", c.split("-")[1])):
            other = c.split("-")[1 if sp == "A" else 0]
            labels.append(f"{nick.capitalize()} {sp}\nvs {other.capitalize()}")
            kept.append(p[sp][0]); broke.append(p[sp][1])
    x = np.arange(len(labels)); w = 0.38
    ax.bar(x - w / 2, kept, w, color=AQUA, label="said cooperate, cooperated")
    ax.bar(x + w / 2, broke, w, color=YELLOW, label="said cooperate, defected")
    for i, (k, b) in enumerate(zip(kept, broke)):
        rate = b / max(k + b, 1)
        ax.text(i, max(k, b) + 8, f"{rate:.0%} broken", ha="center", fontsize=7.5, color=INK)
    ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=7)
    ax.set_ylim(0, max(kept) * 1.3)
    ax.legend(fontsize=8, frameon=False, loc="upper right")
    style(ax, "Talk variant: stated intention vs move\n(last message before each game; 1,240 games per cell)")
    ax.set_ylabel("games", fontsize=9, color=MUTED)

    # row 3 right: whole-run means
    ax = fig.add_subplot(gs[2, 2:4])
    means = {}
    for variant, data in (("silent", silent), ("talk", talk)):
        means[variant] = [np.mean([min(d["eval"]["coop"]) for d in data[c]]) for c in CELLS]
    x = np.arange(len(CELLS)); w = 0.38
    ax.bar(x - w / 2, means["silent"], w, color=BLUE, alpha=0.45, label="silent, private utilities")
    ax.bar(x + w / 2, means["talk"], w, color=BLUE, label="talk, visible utilities, no outcome feedback")
    for i in range(len(CELLS)):
        ax.text(i - w / 2, means["silent"][i] + 0.02, f"{means['silent'][i]:.2f}", ha="center", fontsize=7.5, color=INK)
        ax.text(i + w / 2, means["talk"][i] + 0.02, f"{means['talk'][i]:.2f}", ha="center", fontsize=7.5, color=INK)
    ax.set_xticks(x); ax.set_xticklabels([LABEL[c] for c in CELLS], fontsize=8)
    ax.set_ylim(0, 1.3); ax.legend(fontsize=8, frameon=False, loc="upper left")
    style(ax, "Mean cooperation of the less cooperative agent\n(31 evaluations per cell)")

    fig.suptitle("Inference-only recursive utility modification in the prisoner's dilemma: silent matrix vs talk variant",
                 fontsize=12, color=INK, x=0.01, ha="left", y=0.995)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(a.out, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    print(a.out)


if __name__ == "__main__":
    main()
