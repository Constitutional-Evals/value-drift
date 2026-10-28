"""Does it matter which note belongs to Player A (who speaks first in round 1)? One row per pair of notes."""
import argparse, glob, json, re
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

INK, INK2, SURFACE = "#0b0b0b", "#52514e", "#fcfcfb"
C1, C2 = "#2a78d6", "#eb6834"
ORDER = ["base", "cooperate", "defect", "exploit", "promise", "skeptical", "relative"]
PAY = {("C", "C"): (3, 3), ("C", "D"): (0, 5), ("D", "C"): (5, 0), ("D", "D"): (1, 1)}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--runs", type=Path, required=True); ap.add_argument("--out", type=Path, default=Path("out"))
    a = ap.parse_args()
    coop = {}; payA = []; payB = []
    for d in sorted(a.runs.iterdir()):
        m = re.match(r"^(\w+?)_vs_(\w+?)5_gpt6sol$", d.name)
        if not m:
            continue
        k = c = 0
        for g in d.glob("game_*/game.json"):
            for s in json.load(open(g))["steps"]:
                x, y = s["actions"]["A"], s["actions"]["B"]
                k += (x == "C") + (y == "C"); c += 2
                pa, pb = PAY[(x, y)]; payA.append(pa); payB.append(pb)
        coop[(m.group(1), m.group(2))] = (k, c)
    rows = []
    for i, x in enumerate(ORDER):
        for y in ORDER[i + 1:]:
            if (x, y) in coop and (y, x) in coop:
                p1 = coop[(x, y)][0] / coop[(x, y)][1]; p2 = coop[(y, x)][0] / coop[(y, x)][1]
                rows.append((x, y, p1, p2, coop[(x, y)][0], coop[(y, x)][0]))
    rows.sort(key=lambda r: abs(r[2] - r[3]), reverse=True)
    fig, ax = plt.subplots(figsize=(9.6, 8.2)); fig.patch.set_facecolor(SURFACE)
    for i, (x, y, p1, p2, k1, k2) in enumerate(rows):
        yy = len(rows) - 1 - i
        ax.plot([p1 * 100, p2 * 100], [yy, yy], color="#bdbcb7", lw=2.2, zorder=1)
        ax.scatter([p1 * 100], [yy], s=70, color=C1, zorder=3); ax.scatter([p2 * 100], [yy], s=70, color=C2, zorder=3)
    ax.set_yticks(range(len(rows))); ax.set_yticklabels([f"{x} / {y}" for x, y, *_ in rows][::-1], fontsize=10)
    ax.set_xlim(-3, 103); ax.set_xlabel("share of moves that cooperated (%)")
    ax.xaxis.grid(True, color="#e6e5e1", lw=0.8, zorder=0); ax.set_axisbelow(True)
    for sp in ("top", "right"): ax.spines[sp].set_visible(False)
    ax.scatter([], [], s=70, color=C1, label="the FIRST note in the label is Player A (speaks first)")
    ax.scatter([], [], s=70, color=C2, label="the SECOND note in the label is Player A (speaks first)")
    ax.legend(loc="lower right", frameon=True, facecolor=SURFACE, edgecolor="#e6e5e1", fontsize=9)
    big = rows[0]
    fig.text(0.01, 0.985, "Does it matter which note is Player A? (GPT)", fontsize=13.5, va="top", color=INK)
    fig.text(0.01, 0.95, f"Each row is one pair of notes, run both ways (5 games x 3 rounds each way). Biggest gap: {big[0]} / {big[1]} "
             f"({big[2]*100:.0f}% vs {big[3]*100:.0f}%).\nShort lines mean the order made little difference.", fontsize=9.5, va="top", color=INK2)
    fig.tight_layout(rect=(0, 0, 1, 0.9)); fig.savefig(a.out / "order_effect.png", dpi=200, facecolor=SURFACE)
    diffs = [abs(r[2] - r[3]) for r in rows]
    print(f"pairs: {len(rows)}  mean |difference|: {sum(diffs)/len(diffs)*100:.0f} points  pairs with a gap over 20 points: {sum(d > 0.2 for d in diffs)}  under 10 points: {sum(d < 0.1 for d in diffs)}")
    print("first speaker (A) avg payoff per round: $%.2f   second speaker (B): $%.2f   (n=%d rounds)" % (sum(payA)/len(payA), sum(payB)/len(payB), len(payA)))
    for r in rows[:5]: print(f"  {r[0]} / {r[1]}: {r[4]}/30 vs {r[5]}/30")
main()
