"""Claude and GPT side by side, same-note runs only (both players start from the same note), so the comparison is like for like.

    python3 compare_models.py --claude <clone>/constitutional_self_edit/reports/12_incentivized_drift/data --gpt <clone>/constitutional_self_edit/runs/pd_drift --out out/

cooperation_by_note.png  share of moves that cooperated, per starting note and round, Claude vs GPT
earnings_by_note.png     average dollars per round for each starting note
next_round.png           what happens next round after both defect / both cooperate
The 'base' note is left out: Claude's base runs predate the 'no record is kept' line, so they are not comparable.
"""
import argparse, json, re
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

INK, INK2, SURFACE = "#0b0b0b", "#52514e", "#fcfcfb"
COLORS = {"Claude": "#2a78d6", "GPT": "#d9622b"}
NOTES = ["cooperate", "promise", "skeptical", "exploit", "defect", "relative"]
PAY = {("C", "C"): (3, 3), ("C", "D"): (0, 5), ("D", "C"): (5, 0), ("D", "D"): (1, 1)}


def load(runs: Path, suffix: str):
    """note -> list of games, each a list of (A action, B action) per step. Same-note runs only."""
    out = {}
    for d in sorted(runs.iterdir()):
        m = re.match(r"^([a-z]+)\d_" + suffix + "$", d.name)
        if m and m.group(1) in NOTES:
            out[m.group(1)] = [[(s["actions"]["A"], s["actions"]["B"]) for s in json.load(open(g))["steps"]] for g in sorted(d.glob("game_*/game.json"))]
    return out


def style(ax):
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--claude", type=Path, required=True); ap.add_argument("--gpt", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=Path("out"))
    ap.add_argument("--payoffs", type=Path, nargs=2, metavar=("CLAUDE_CSV", "GPT_CSV"), help="payoffs.csv from payoff_charts.py for each model: also draws earnings against all partners")
    a = ap.parse_args(); a.out.mkdir(parents=True, exist_ok=True)
    data = {"Claude": load(a.claude, "claude"), "GPT": load(a.gpt, "gpt6sol")}
    notes = [n for n in NOTES if all(n in d for d in data.values())]
    ng = {m: sum(len(g) for g in d.values()) for m, d in data.items()}

    # 1. cooperation by note and step
    fig, axes = plt.subplots(2, 3, figsize=(10.5, 6.2), sharey=True); fig.patch.set_facecolor(SURFACE)
    for ax, note in zip(axes.ravel(), notes):
        for k, (m, d) in enumerate(data.items()):
            for st in range(3):
                moves = [x for g in d[note] if len(g) > st for x in g[st]]
                v = sum(x == "C" for x in moves) / len(moves) * 100
                ax.bar(st + (k - 0.5) * 0.38, v, 0.36, color=COLORS[m], label=m if note == notes[0] and st == 0 else None, zorder=2)
                ax.text(st + (k - 0.5) * 0.38, v + 2, f"{v:.0f}", ha="center", fontsize=8, color=INK)
        ax.set_title(note, loc="left", fontsize=11, color=INK); ax.set_xticks(range(3)); ax.set_xticklabels(["round 1", "round 2", "round 3"], fontsize=9)
        ax.set_ylim(0, 112); style(ax)
    for ax in axes[:, 0]: ax.set_ylabel("% of moves that cooperated")
    fig.legend(loc="lower center", ncol=2, frameon=False, fontsize=10)
    fig.suptitle("Claude vs GPT: how often each cooperates, by starting note", x=0.01, y=0.985, ha="left", fontsize=13.5, color=INK)
    fig.text(0.01, 0.935, f"Both players start from the same note. {ng['Claude']} Claude games and {ng['GPT']} GPT games. Each note: 5 games (4 for Claude skeptical), 3 rounds.",
             fontsize=9.5, color=INK2, va="top")
    fig.tight_layout(rect=(0, 0.05, 1, 0.92)); fig.savefig(a.out / "cooperation_by_note.png", dpi=190, facecolor=SURFACE); plt.close(fig)

    # 2. earnings
    fig, ax = plt.subplots(figsize=(8.6, 4.8)); fig.patch.set_facecolor(SURFACE)
    for k, (m, d) in enumerate(data.items()):
        for i, note in enumerate(notes):
            pay = [PAY[s][0] + PAY[s][1] for g in d[note] for s in g]
            v = sum(pay) / len(pay) / 2
            ax.barh(i + (k - 0.5) * 0.38, v, 0.36, color=COLORS[m], label=m if i == 0 else None, zorder=2)
            ax.text(v + 0.04, i + (k - 0.5) * 0.38, f"${v:.2f}", va="center", fontsize=8.5, color=INK)
    ax.set_yticks(range(len(notes))); ax.set_yticklabels(notes, fontsize=10.5); ax.invert_yaxis(); ax.set_xlim(0, 3.5)
    for x, lab in ((1, "both defect: $1"), (3, "both cooperate: $3")):
        ax.axvline(x, color="#8a8984", lw=1.1, ls=(0, (4, 3)), zorder=1); ax.text(x, -0.78, lab, ha="center", fontsize=8.5, color=INK2)
    ax.set_xlabel("average dollars each player earns per round"); style(ax); ax.legend(frameon=False, loc="lower right")
    fig.text(0.01, 0.975, "Claude vs GPT: what each starting note earns", fontsize=13, va="top", color=INK)
    fig.text(0.01, 0.92, "Same-note games only (both players start from the same note).", fontsize=9.5, va="top", color=INK2)
    fig.tight_layout(rect=(0, 0, 1, 0.88)); fig.savefig(a.out / "earnings_by_note.png", dpi=190, facecolor=SURFACE); plt.close(fig)

    # 3. what happens next round
    def nxt(d, src):
        c = {"DD": 0, "CD": 0, "CC": 0}
        for note in notes:
            for g in d[note]:
                st = ["".join(sorted(s)) if False else ("CC" if s == ("C", "C") else "DD" if s == ("D", "D") else "CD") for s in g]
                for x, y in zip(st, st[1:]):
                    if x == src: c[y] += 1
        return c
    fig, axes = plt.subplots(1, 2, figsize=(9.6, 3.6)); fig.patch.set_facecolor(SURFACE)
    lab = {"DD": "both defect", "CD": "one of each", "CC": "both cooperate"}; shade = {"DD": "#52514e", "CD": "#eda100", "CC": "#2a78d6"}
    for ax, src, title in zip(axes, ("DD", "CC"), ("Last round both defected", "Last round both cooperated")):
        for i, (m, d) in enumerate(data.items()):
            c = nxt(d, src); n = sum(c.values()); left = 0
            for s in ("DD", "CD", "CC"):
                w = c[s] / n * 100
                ax.barh(i, w, left=left, color=shade[s], height=0.55, label=lab[s] if i == 0 else None)
                if w >= 7: ax.text(left + w / 2, i, f"{w:.0f}%", ha="center", va="center", fontsize=9, color="white" if s != "CD" else "black")
                left += w
            ax.text(101, i, f"n={n}", va="center", fontsize=8.5, color=INK2)
        ax.set_yticks([0, 1]); ax.set_yticklabels(list(data)); ax.invert_yaxis(); ax.set_xlim(0, 112); ax.set_title(title, loc="left", fontsize=10.5, color=INK)
        ax.set_xlabel("what they did the next round (%)"); style(ax)
    h, l = axes[0].get_legend_handles_labels(); fig.legend(h, l, ncol=3, frameon=False, fontsize=9, loc="lower center")
    fig.suptitle("Claude vs GPT: is mutual defection sticky?", x=0.01, y=0.99, ha="left", fontsize=13, color=INK)
    fig.tight_layout(rect=(0, 0.1, 1, 0.94)); fig.savefig(a.out / "next_round.png", dpi=190, facecolor=SURFACE); plt.close(fig)
    if a.payoffs:
        import csv
        pay = {m: {r["note"]: (float(r["avg_dollars_per_round"]), int(r["rounds"])) for r in csv.DictReader(open(p))} for m, p in zip(("Claude", "GPT"), a.payoffs)}
        notes2 = [n for n in ["base"] + NOTES if all(n in pay[m] for m in pay)]
        notes2.sort(key=lambda n: -pay["Claude"][n][0])
        fig, ax = plt.subplots(figsize=(8.6, 5.2)); fig.patch.set_facecolor(SURFACE)
        for k, m in enumerate(pay):
            for i, n in enumerate(notes2):
                v = pay[m][n][0]
                ax.barh(i + (k - 0.5) * 0.38, v, 0.36, color=COLORS[m], label=m if i == 0 else None, zorder=2)
                ax.text(v + 0.04, i + (k - 0.5) * 0.38, f"${v:.2f}", va="center", fontsize=8.5, color=INK)
        ax.set_yticks(range(len(notes2))); ax.set_yticklabels(notes2, fontsize=10.5); ax.invert_yaxis(); ax.set_xlim(0, 3.5)
        for x, lab in ((1, "both defect: $1"), (3, "both cooperate: $3")):
            ax.axvline(x, color="#8a8984", lw=1.1, ls=(0, (4, 3)), zorder=1); ax.text(x, -0.78, lab, ha="center", fontsize=8.5, color=INK2)
        ax.set_xlabel("average dollars each player earns per round"); style(ax); ax.legend(frameon=False, loc="lower right")
        fig.text(0.01, 0.975, "Claude vs GPT: what each starting note earns, against all partners", fontsize=13, va="top", color=INK)
        fig.text(0.01, 0.92, "Every game that note played, same-note and different-note pairs. Claude's different-note cells have 2 games each, GPT's 5.", fontsize=9, va="top", color=INK2)
        fig.tight_layout(rect=(0, 0, 1, 0.88)); fig.savefig(a.out / "earnings_by_note_all_partners.png", dpi=190, facecolor=SURFACE); plt.close(fig)
    for m, d in data.items():
        c = nxt(d, "DD"); print(m, "after both defect:", c, "| after both cooperate:", nxt(d, "CC"))


if __name__ == "__main__":
    main()
