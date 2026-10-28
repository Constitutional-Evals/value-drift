"""Average earnings per round for each starting note (one model's runs, --model).

    python3 payoff_charts.py --runs ~/value-drift-pd/constitutional_self_edit/runs/pd_drift --out ~/pd_out

Game payoffs per round in dollars (you, other): both cooperate 3,3 | you cooperate, they defect 0,5 | you defect, they cooperate 5,0 | both defect 1,1.
payoff_by_note.png   average dollars per round for each starting note, over all its games (either seat)
payoff_grid.png      average dollars per round earned by the ROW note when playing the COLUMN note
payoffs.csv          the numbers
"""
import argparse, collections, csv, json, re
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

INK, INK2, SURFACE, BLUE = "#0b0b0b", "#52514e", "#fcfcfb", "#2a78d6"
PAY = {("C", "C"): (3, 3), ("C", "D"): (0, 5), ("D", "C"): (5, 0), ("D", "D"): (1, 1)}
DOCS = ["base", "cooperate", "defect", "exploit", "promise", "skeptical", "relative"]


def main():
    global DOCS
    ap = argparse.ArgumentParser(); ap.add_argument("--runs", type=Path, required=True); ap.add_argument("--out", type=Path, default=Path("out"))
    ap.add_argument("--model", choices=["gpt6sol", "claude"], default="gpt6sol", help="which model's run folders to read")
    a = ap.parse_args()
    mlabel = {"gpt6sol": "GPT", "claude": "Claude"}[a.model]; a.out.mkdir(parents=True, exist_ok=True)
    by_note = collections.defaultdict(lambda: [0.0, 0])           # note -> [dollars, rounds]
    vs = collections.defaultdict(lambda: [0.0, 0])                # (row note, column note) -> [dollars, rounds]
    for d in sorted(a.runs.iterdir()):
        m = re.match(r"^(?:(\w+?)_vs_(\w+?)|(\w+?))\d_" + a.model + "$", d.name)
        if not m:
            continue
        na, nb = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(3))
        for g in d.glob("game_*/game.json"):
            for s in json.load(open(g))["steps"]:
                pa, pb = PAY[(s["actions"]["A"], s["actions"]["B"])]
                for note, p, other in ((na, pa, nb), (nb, pb, na)):
                    by_note[note][0] += p; by_note[note][1] += 1
                    vs[(note, other)][0] += p; vs[(note, other)][1] += 1
    avg = {k: v[0] / v[1] for k, v in by_note.items()}
    DOCS = [k for k in DOCS if k in avg]
    ngames = len({(p.parent.name, p.name) for d in a.runs.iterdir() if re.match(r"^(?:(\w+?)_vs_(\w+?)|(\w+?))\d_" + a.model + "$", d.name) for p in d.glob("game_*")})
    order = sorted(DOCS, key=lambda k: -avg[k])

    # ---- chart 1: earnings by note
    fig, ax = plt.subplots(figsize=(8.4, 4.6)); fig.patch.set_facecolor(SURFACE)
    vals = [avg[k] for k in order]
    ax.barh(range(len(order)), vals, color=BLUE, height=0.62, zorder=2)
    for i, (k, v) in enumerate(zip(order, vals)):
        ax.text(v + 0.04, i, f"${v:.2f}", va="center", fontsize=11, color=INK)
    ax.set_yticks(range(len(order))); ax.set_yticklabels(order, fontsize=11); ax.invert_yaxis()
    ax.set_xlim(0, 3.4); ax.set_xlabel("average dollars earned per round")
    for x, lab in ((1, "both cheat: $1"), (3, "both cooperate: $3")):
        ax.axvline(x, color="#8a8984", lw=1.2, ls=(0, (4, 3)), zorder=1); ax.text(x, -0.75, lab, ha="center", fontsize=9, color=INK2)
    for sp in ("top", "right"): ax.spines[sp].set_visible(False)
    fig.text(0.01, 0.975, f"Which starting note earns the most money? ({mlabel})", fontsize=13, va="top", color=INK)
    fig.text(0.01, 0.915, f"Average per round over every game that note played, against all partners ({ngames} games, 3 rounds each).", fontsize=9.5, va="top", color=INK2)
    fig.tight_layout(rect=(0, 0, 1, 0.88)); fig.savefig(a.out / "payoff_by_note.png", dpi=200, facecolor=SURFACE); plt.close(fig)

    # ---- chart 2: grid
    n = len(DOCS); grid = np.full((n, n), np.nan)
    for i, r in enumerate(DOCS):
        for j, c in enumerate(DOCS):
            if (r, c) in vs: grid[i, j] = vs[(r, c)][0] / vs[(r, c)][1]
    fig, ax = plt.subplots(figsize=(8.6, 6.8)); fig.patch.set_facecolor(SURFACE)
    ax.imshow(np.ma.masked_invalid(grid), cmap="Blues", vmin=0, vmax=3.5)
    for i in range(n):
        for j in range(n):
            if not np.isnan(grid[i, j]):
                ax.text(j, i, f"${grid[i, j]:.2f}", ha="center", va="center", fontsize=10.5, color="white" if grid[i, j] > 2.0 else INK)
    ax.set_xticks(range(n)); ax.set_xticklabels(DOCS, rotation=40, ha="right"); ax.set_yticks(range(n)); ax.set_yticklabels(DOCS)
    ax.set_xlabel("partner's starting note"); ax.set_ylabel("this player's starting note")
    for sp in ax.spines.values(): sp.set_visible(False)
    ax.tick_params(length=0)
    fig.text(0.01, 0.985, f"How much does a note earn against each partner? ({mlabel})", fontsize=13, va="top", color=INK)
    fig.text(0.01, 0.945, "Average dollars per round for the ROW player against the COLUMN player. 5 games x 3 rounds per cell.\nFor reference: both cheat = \\$1, both cooperate = \\$3, cheating a cooperator = \\$5, being cheated = \\$0.", fontsize=9.2, va="top", color=INK2)
    fig.tight_layout(rect=(0, 0, 1, 0.88)); fig.savefig(a.out / "payoff_grid.png", dpi=200, facecolor=SURFACE); plt.close(fig)

    with open(a.out / "payoffs.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["note", "avg_dollars_per_round", "rounds"]); [w.writerow([k, f"{avg[k]:.3f}", by_note[k][1]]) for k in order]
    print("order:", ", ".join(f"{k} ${avg[k]:.2f}" for k in order))


main()
