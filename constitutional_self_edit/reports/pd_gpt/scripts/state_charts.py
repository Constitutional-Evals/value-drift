"""State strips and transition chart for one model's runs (--model gpt6sol or claude).

    python3 state_charts.py --runs ~/value-drift-pd/constitutional_self_edit/runs/pd_drift --out ~/pd_out

A state is what both agents did in one step: CC (both cooperate), CD (one cooperates, one defects), DD (both defect).
state_strips.png      one small panel per pair of starting documents; each row is one game, each box one step
transitions.png       what happens in the next step, given this step's state; same-note pairs vs different-note pairs
transitions.csv       the counts behind it
"""
import argparse, collections, csv, json, re
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Patch

INK, INK2, SURFACE = "#0b0b0b", "#52514e", "#fcfcfb"
COL = {"CC": "#2a78d6", "CD": "#eda100", "DD": "#52514e"}
NAME = {"CC": "both cooperate", "CD": "one of each", "DD": "both defect"}
DOC_ORDER = ["base", "cooperate", "defect", "exploit", "promise", "skeptical", "relative"]
NORM = lambda s: "base" if s == "c000" else s


def state(a):
    return "CC" if a["A"] == "C" and a["B"] == "C" else "DD" if a["A"] == "D" and a["B"] == "D" else "CD"


def load(runs: Path, suffix: str):
    out = {}
    for d in sorted(runs.iterdir()):
        m = re.match(r"^(?:od_)?(?:(base|c000|cooperate|defect|exploit|promise|skeptical|relative)_vs_(base|c000|cooperate|defect|exploit|promise|skeptical|relative)|(base|c000|cooperate|defect|exploit|promise|skeptical|relative))\d?_" + suffix + "$", d.name)
        if not m:
            continue
        a, b = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(3))
        a, b = NORM(a), NORM(b)
        if a not in DOC_ORDER or b not in DOC_ORDER:
            continue
        games = [[state(s["actions"]) for s in json.load(open(g))["steps"]] for g in sorted(d.glob("game_*/game.json"))]
        if games:
            out.setdefault((a, b), []).extend(games)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=Path("out"))
    ap.add_argument("--model", choices=["gpt6sol", "claude"], default="gpt6sol", help="which model's run folders to read")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    data = load(a.runs, a.model)
    mlabel = {"gpt6sol": "GPT", "claude": "Claude"}[a.model]
    ngames = sum(len(g) for g in data.values())
    order = sorted(data, key=lambda k: (k[0] != k[1], DOC_ORDER.index(k[0]), DOC_ORDER.index(k[1])))

    # ---- state strips: small multiples, 7 columns
    ncol = min(7, max(1, len(order)))
    nrow = int(np.ceil(len(order) / ncol))
    fig, axes = plt.subplots(nrow, ncol, figsize=(2.0 * ncol, 1.75 * nrow + 1.2))
    fig.patch.set_facecolor(SURFACE)
    axes = np.atleast_2d(axes)
    for ax in axes.ravel():
        ax.axis("off")
    for ax, key in zip(axes.ravel(), order):
        games = data[key]
        for gi, seq in enumerate(games):
            for si, s in enumerate(seq):
                ax.add_patch(plt.Rectangle((si, len(games) - 1 - gi), 0.92, 0.88, color=COL[s], lw=0))
        ax.set_xlim(-0.05, 3); ax.set_ylim(-0.05, len(games))
        ax.set_title(f"{key[0]} | {key[1]}" if key[0] != key[1] else f"{key[0]} (both)", fontsize=9.5, color=INK, loc="left", pad=3,
                     fontweight="bold" if key[0] == key[1] else "normal")
    fig.suptitle(f"What each pair of {mlabel} players did, round by round", x=0.01, y=0.985, ha="left", fontsize=14, color=INK)
    fig.text(0.01, 0.945, "Each panel is one pair of starting notes (A | B): each game is a row, rounds 1 to 3 are boxes. First row of panels: both players start from the same note.",
             fontsize=9.5, color=INK2, va="top")
    fig.legend(handles=[Patch(color=COL[s], label=NAME[s]) for s in ("CC", "CD", "DD")], loc="lower center", ncol=3, frameon=False, fontsize=10)
    fig.tight_layout(rect=(0, 0.04, 1, 0.92))
    fig.savefig(a.out / "state_strips.png", dpi=200, facecolor=SURFACE)
    plt.close(fig)

    # ---- transitions
    groups = {"same note on both sides": [k for k in data if k[0] == k[1]], "different notes": [k for k in data if k[0] != k[1]]}
    states = ["DD", "CD", "CC"]
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.9))
    fig.patch.set_facecolor(SURFACE)
    rows_csv = []
    panels = list(groups.items()) + [(f"all {mlabel} games", list(data))]
    for ax, (title, keys) in zip(axes, panels):
        T = collections.Counter()
        for k in keys:
            for seq in data[k]:
                for x, y in zip(seq, seq[1:]):
                    T[(x, y)] += 1
        M = np.zeros((3, 3)); N = np.zeros(3)
        for i, x in enumerate(states):
            N[i] = sum(T[(x, y)] for y in states)
            for j, y in enumerate(states):
                M[i, j] = T[(x, y)] / N[i] if N[i] else np.nan
                rows_csv.append([title, x, y, T[(x, y)], int(N[i])])
        ax.imshow(M, cmap="Blues", vmin=0, vmax=1)
        for i in range(3):
            for j in range(3):
                if N[i]:
                    ax.text(j, i, f"{M[i, j]:.0%}\n({T[(states[i], states[j])]})", ha="center", va="center", fontsize=11,
                            color="white" if M[i, j] > 0.55 else INK)
        ax.set_xticks(range(3)); ax.set_xticklabels([NAME[s] for s in states], fontsize=9.5)
        ax.set_yticks(range(3)); ax.set_yticklabels([f"{NAME[s]}\n(n={int(N[i])})" for i, s in enumerate(states)], fontsize=9.5)
        ax.set_xlabel("next round"); ax.set_ylabel("this round")
        esc = (1 - M[0, 0]) if N[0] else float("nan")
        ax.set_title(f"{title}\nescape from both-defect: " + ("no games" if esc != esc else f"{esc:.0%}"), loc="left", fontsize=11, color=INK)
        for sp in ax.spines.values():
            sp.set_visible(False)
        ax.tick_params(length=0)
    fig.suptitle(f"If the players are in this state, what happens next round? ({mlabel}, {len(data)} pair runs, {ngames} games)", x=0.01, y=0.99, ha="left", fontsize=13.5, color=INK)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(a.out / "transitions.png", dpi=200, facecolor=SURFACE)
    with open(a.out / "transitions.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["group", "this_round", "next_round", "count", "total_from_this_round"]); w.writerows(rows_csv)
    print("wrote state_strips.png, transitions.png, transitions.csv in", a.out, "| pairs:", len(data), "| games:", sum(len(v) for v in data.values()))


main()
