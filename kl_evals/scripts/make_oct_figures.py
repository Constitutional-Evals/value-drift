"""Slide figures for the OCT adherence run: gains with intervals, per-theme gains, human vs judge.

    python3 scripts/make_oct_figures.py

Reads results/adherence/oct_targeted/analysis/summary.json and, for the third figure, the blind-sheet
key plus scores_original_blind.csv (the scores as given before any edits).
"""
from __future__ import annotations

import collections
import csv
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from adherence.reliability import spearman

RUN = Path("results/adherence/oct_targeted")
OUT = RUN / "analysis"
JUDGE = "default__openrouter_anthropic_claude-sonnet-5"
ARM = "r1_sft"

SURFACE, INK, INK2, MUTED = "#fcfcfb", "#0b0b0b", "#52514e", "#8a8984"
TRAINED, BASE = "#2a78d6", "#eb6834"

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.edgecolor": MUTED, "axes.labelcolor": INK2, "text.color": INK,
    "xtick.color": INK2, "ytick.color": INK2, "font.size": 11,
    "axes.spines.top": False, "axes.spines.right": False,
})


def interval(ax, y, c, color, filled=True, size=7):
    ax.plot([c["lo"], c["hi"]], [y, y], color=color, lw=2.2, solid_capstyle="round", zorder=2)
    ax.plot(c["mean"], y, "o", ms=size, color=color if filled else SURFACE, mec=color, mew=2, zorder=3)


def excludes_zero(c):
    return c["lo"] > 0 or c["hi"] < 0


def fig_gains(s):
    con = s["contrasts"][ARM]
    direct, targ = s["splits"]["direct_questions"]["contrasts"][ARM], s["splits"]["targeted_new_content"]["contrasts"][ARM]
    rows = [
        ("Follows its own constitution (all 164 probes)", con["gain_own"], TRAINED),
        ("  ...direct questions (44)", direct["gain_own"], TRAINED),
        ("  ...targeted new-content probes (120)", targ["gain_own"], TRAINED),
        ("Specific to C_001 rather than C_000 (all 164)", con["gain_specific"], TRAINED),
        ("  ...targeted new-content probes (120)", targ["gain_specific"], TRAINED),
        ("Control: unrelated 'deferential' constitution", con["gain_control[deferential]"], MUTED),
    ]
    fig, ax = plt.subplots(figsize=(9.2, 4.6))
    for i, (label, c, color) in enumerate(rows):
        y = len(rows) - 1 - i
        interval(ax, y, c, color, filled=excludes_zero(c))
        ax.text(c["hi"] + 0.03, y, f"{c['mean']:+.2f}  [{c['lo']:+.2f}, {c['hi']:+.2f}]", va="center", fontsize=10, color=INK2)
    ax.axvline(0, color=MUTED, lw=1, ls=(0, (3, 3)), zorder=1)
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([r[0] for r in rows][::-1])
    ax.set_xlim(-0.3, 1.25)
    ax.set_xlabel("gain over the untrained base model (score points, 1-7 scale)")
    fig.text(0.01, 0.965, "Training raises adherence, but little of the gain is specific to the new text", fontsize=13, va="top")
    fig.text(0.01, 0.895, f"OCT round-one model vs base, judged by Claude Sonnet 5. Filled dot: interval excludes 0. Win rate vs base {s['win_rate'][ARM]['mean']:.0%}.",
             fontsize=9.5, color=INK2, va="top")
    fig.tight_layout(rect=(0, 0, 1, 0.86))
    fig.savefig(OUT / "gains.png", dpi=200)
    plt.close(fig)


def fig_themes(s):
    tb = s["targeted_breakdown"]
    themes = sorted((k for k in tb if k.startswith("axis=")), key=lambda k: tb[k][ARM]["gain_own"]["mean"])
    names = [k.split("=", 1)[1].replace("_", " ") for k in themes]
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 5), sharey=True)
    for ax, key, title in zip(axes, ("gain_own", "gain_specific"),
                              ("Follows C_001 more than base", "...beyond what C_000 already said")):
        for i, k in enumerate(themes):
            c = tb[k][ARM][key]
            interval(ax, i, c, TRAINED, filled=excludes_zero(c), size=6.5)
        ax.axvline(0, color=MUTED, lw=1, ls=(0, (3, 3)), zorder=1)
        ax.set_title(title, loc="left", fontsize=11.5, color=INK)
        ax.set_xlabel("gain over base (score points)")
    axes[0].set_yticks(range(len(themes)))
    axes[0].set_yticklabels(names)
    fig.suptitle("The new-content effect lives in two themes: provisional values and continuity", x=0.01, ha="left", fontsize=13)
    fig.text(0.01, 0.935, "About 15 probes per theme, so intervals are wide. Filled dot: interval excludes 0.", fontsize=9.5, color=INK2)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(OUT / "themes.png", dpi=200)
    plt.close(fig)


def fig_human(s):
    d = RUN / "blind"
    items = json.load(open(d / "key.json"))["items"]
    human = {r["id"]: int(r["score"]) for r in csv.DictReader(open(d / "scores_original_blind.csv"))}
    ids = sorted(items)
    h = np.array([human[i] for i in ids], float)
    j = np.array([items[i]["judge_score"] for i in ids], float)
    arm = np.array([items[i]["arm"] for i in ids])
    rho = spearman(list(h), list(j))
    rng = np.random.default_rng(0)
    fig, ax = plt.subplots(figsize=(6.4, 5.6))
    ax.plot([1, 7.4], [1, 7.4], color=MUTED, lw=1, ls=(0, (3, 3)), zorder=1)
    for a, color, label in (("base", BASE, "base model"), (ARM, TRAINED, "trained (r1_sft)")):
        m = arm == a
        ax.scatter(h[m] + rng.uniform(-.13, .13, m.sum()), j[m] + rng.uniform(-.13, .13, m.sum()),
                   s=70, color=color, alpha=.85, edgecolor=SURFACE, linewidth=1.2, label=label, zorder=3)
    ax.set_xlim(1.5, 7.5)
    ax.set_ylim(3.5, 7.5)
    ax.set_xlabel("my blind score (1-7)")
    ax.set_ylabel("judge score (1-7)")
    fig.text(0.01, 0.975, f"Human vs judge on 30 blind answers: rank agreement {rho:.2f}", fontsize=12.5, va="top")
    fig.text(0.01, 0.925, "Pre-registered bar was 0.6, so this check is not passed.\nDots jittered; dashed line = perfect agreement.",
             fontsize=9, color=INK2, va="top")
    ax.legend(frameon=False, loc="lower right")
    fig.tight_layout(rect=(0, 0, 1, 0.87))
    for a, color in (("base", BASE), (ARM, TRAINED)):
        m = arm == a
        ax.text(0.02, 0.96 - (0.07 if a == ARM else 0), f"{a}: me {h[m].mean():.2f}, judge {j[m].mean():.2f}",
                transform=ax.transAxes, fontsize=9.5, color=color, va="top")
    fig.savefig(OUT / "human_vs_judge.png", dpi=200)
    plt.close(fig)


def _boot_gain(judgments, cons, other=None, seed=0):
    """Mean trained-minus-base adherence over probes (optionally minus the same gain on `other`) with a 95% bootstrap CI."""
    cell = collections.defaultdict(list)
    for r in judgments:
        if r["kind"] == "adherence" and r.get("score") is not None:
            cell[(r["arm"], r["constitution"], r["probe"])].append(r["score"])
    mean = {k: float(np.mean(v)) for k, v in cell.items()}
    probes = sorted({k[2] for k in mean if k[0] == "base" and k[1] == cons and (ARM, cons, k[2]) in mean})

    def g(c):
        return np.array([mean[(ARM, c, p)] - mean[("base", c, p)] for p in probes])

    x = g(cons) - (g(other) if other else 0)
    rng = np.random.default_rng(seed)
    bs = [rng.choice(x, len(x)).mean() for _ in range(4000)]
    return {"mean": float(x.mean()), "lo": float(np.percentile(bs, 2.5)), "hi": float(np.percentile(bs, 97.5))}


def fig_judges():
    judges = [("Claude Sonnet 5", "default__openrouter_anthropic_claude-sonnet-5.jsonl", "#6250d6"),
              ("GPT-5 (second judge)", "default__openrouter_openai_gpt-5.jsonl", "#1baf7a")]
    rows = [("Follows C_001 more than base", "C_001", None), ("Follows C_000 more than base", "C_000", None),
            ("Specific to C_001 rather than C_000", "C_001", "C_000")]
    data = {}
    for name, f, _ in judges:
        js = [json.loads(l) for l in open(RUN / "judgments" / f)]
        data[name] = [_boot_gain(js, c, o) for _, c, o in rows]
    fig, ax = plt.subplots(figsize=(9.2, 4.2))
    for ri in range(len(rows)):
        for ji, (name, _, color) in enumerate(judges):
            c = data[name][ri]
            y = (len(rows) - 1 - ri) + (0.17 if ji == 0 else -0.17)
            interval(ax, y, c, color, filled=excludes_zero(c))
            ax.text(c["hi"] + 0.03, y, f"{c['mean']:+.2f}  [{c['lo']:+.2f}, {c['hi']:+.2f}]", va="center", fontsize=9.5, color=INK2)
    ax.axvline(0, color=MUTED, lw=1, ls=(0, (3, 3)), zorder=1)
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([r[0] for r in rows][::-1])
    ax.set_xlim(-0.1, 0.95)
    ax.set_xlabel("gain over the untrained base model (score points, 1-7 scale)")
    for name, _, color in judges:
        ax.plot([], [], "o-", color=color, label=name)
    ax.legend(frameon=False, loc="lower right")
    fig.text(0.01, 0.965, "Both judges see the trained model ahead, but they disagree on how much", fontsize=13, va="top")
    fig.text(0.01, 0.895, "164 probes, C_000 and C_001 only. Filled dot: interval excludes 0. GPT-5 scores near the ceiling for both models (about 6.7 of 7).",
             fontsize=9.5, color=INK2, va="top")
    fig.tight_layout(rect=(0, 0, 1, 0.86))
    fig.savefig(OUT / "judges.png", dpi=200)
    plt.close(fig)


if __name__ == "__main__":
    summary = json.load(open(OUT / "summary.json"))[JUDGE]
    fig_gains(summary)
    fig_themes(summary)
    fig_human(summary)
    if (RUN / "judgments" / "default__openrouter_openai_gpt-5.jsonl").exists():
        fig_judges()
    print("wrote figures in", OUT)
