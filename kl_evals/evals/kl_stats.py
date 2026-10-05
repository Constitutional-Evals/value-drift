"""Error bars and breakdowns for evals.kl_exact output. CPU only (numpy, matplotlib for plots).

    python -m evals.kl_stats results/kl/jinzhou
    python -m evals.kl_stats results/kl/jinzhou --contrast r1_sft r1_dpo --by axis

Every number is nats per token = (sum of per-token divergence) / (number of tokens), with a 95%
interval from a bootstrap that resamples *scenarios*. Tokens in one reply are correlated, and so
are the replies to one prompt, so the scenario is the independent unit; resampling tokens would
give intervals that are far too narrow.

What it reports, per variant and policy:
  kl              exact KL(variant || base)
  rkl, js         reverse KL and Jensen-Shannon at the same positions
  top1 agree      share of positions where both models' most likely token is the same
  sampled-token   the old estimator (log-ratio of the token in the text) with its own interval,
                  to show how much tighter the exact one is. Only an estimate of KL under
                  policy "self".
  by category     the same, per scenario category (or --by axis for the value probes)
  targeted ratio  KL on value-laden scenarios / KL on control scenarios (coding, facts, sums).
                  ~1 means the adapter changed everything equally; >>1 means the change is
                  concentrated where the constitution has something to say.
  by position     KL at token 1, 2-4, 5-16, ... of the reply
  contrasts       paired differences between variants on the same scenarios (and, under policy
                  "base", the very same tokens)

Writes summary.json, report.md, kl_vs_scale.png and kl_by_category.png into the run folder.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from oct.common import read_jsonl

METRICS = ("kl", "rkl", "js", "lr", "agree")
BUCKETS = [(0, 1, "1"), (1, 4, "2-4"), (4, 16, "5-16"), (16, 64, "17-64"), (64, 10 ** 9, "65+")]
N_BOOT = 2000


# ---------------------------------------------------------------- bootstrap

def per_scenario(rows: list[dict], metric: str, lo: int = 0, hi: int = 10 ** 9) -> dict[str, tuple[float, int]]:
    """scenario id -> (sum of the metric over its tokens, number of tokens), positions [lo, hi)."""
    acc: dict[str, list] = defaultdict(lambda: [0.0, 0])
    for r in rows:
        x = r[metric][lo:hi]
        acc[r["id"]][0] += float(sum(x))
        acc[r["id"]][1] += len(x)
    return {k: (s, n) for k, (s, n) in acc.items() if n}


def ratio_ci(num: np.ndarray, den: np.ndarray, seed: int = 0, n_boot: int = N_BOOT):
    """sum(num)/sum(den) with a percentile interval from resampling clusters (rows of num/den).
    Returns (estimate, lo, hi, se)."""
    if len(num) == 0 or den.sum() == 0:
        return None, None, None, None
    est = num.sum() / den.sum()
    if len(num) < 2:
        return float(est), None, None, None
    idx = np.random.default_rng(seed).integers(0, len(num), (n_boot, len(num)))
    boot = num[idx].sum(1) / den[idx].sum(1)
    lo, hi = np.percentile(boot, [2.5, 97.5])
    return float(est), float(lo), float(hi), float(boot.std(ddof=1))


def estimate(rows, metric="kl", lo=0, hi=10 ** 9, seed=0) -> dict:
    ps = per_scenario(rows, metric, lo, hi)
    ids = sorted(ps)
    e, l, h, se = ratio_ci(np.array([ps[i][0] for i in ids]), np.array([ps[i][1] for i in ids], float), seed)
    return {"est": e, "lo": l, "hi": h, "se": se, "scenarios": len(ids), "tokens": int(sum(ps[i][1] for i in ids))}


def contrast(rows_a, rows_b, metric="kl", seed=0, n_boot=N_BOOT) -> dict:
    """a - b on the scenarios both have, resampling the same scenarios for both (paired)."""
    pa, pb = per_scenario(rows_a, metric), per_scenario(rows_b, metric)
    ids = sorted(set(pa) & set(pb))
    if len(ids) < 2:
        return {"est": None}
    na, da = np.array([pa[i][0] for i in ids]), np.array([pa[i][1] for i in ids], float)
    nb, db = np.array([pb[i][0] for i in ids]), np.array([pb[i][1] for i in ids], float)
    idx = np.random.default_rng(seed).integers(0, len(ids), (n_boot, len(ids)))
    boot = na[idx].sum(1) / da[idx].sum(1) - nb[idx].sum(1) / db[idx].sum(1)
    lo, hi = np.percentile(boot, [2.5, 97.5])
    return {"est": float(na.sum() / da.sum() - nb.sum() / db.sum()), "lo": float(lo), "hi": float(hi),
            "scenarios": len(ids), "excludes_zero": bool(lo > 0 or hi < 0)}


def targeted_ratio(rows, seed=0, n_boot=N_BOOT) -> dict:
    """KL on non-control scenarios / KL on control_* scenarios, resampling each group."""
    ps = per_scenario(rows, "kl")
    cat = {r["id"]: r["category"] for r in rows}
    groups = [[ps[i] for i in sorted(ps) if cat[i].startswith("control") == flag] for flag in (False, True)]
    if min(len(g) for g in groups) < 2:
        return {"est": None}
    rng = np.random.default_rng(seed)
    pt, boots = [], []
    for g in groups:
        num, den = np.array([x[0] for x in g]), np.array([x[1] for x in g], float)
        idx = rng.integers(0, len(g), (n_boot, len(g)))
        pt.append(num.sum() / den.sum())
        boots.append(num[idx].sum(1) / den[idx].sum(1))
    if pt[1] <= 0:
        return {"est": None}
    lo, hi = np.percentile(boots[0] / np.maximum(boots[1], 1e-12), [2.5, 97.5])
    return {"est": float(pt[0] / pt[1]), "lo": float(lo), "hi": float(hi),
            "value_laden": float(pt[0]), "control": float(pt[1])}


# ---------------------------------------------------------------- loading and summarising

def load(run: Path) -> dict[tuple[str, str], list[dict]]:
    data = {}
    for f in sorted((run / "tokens").glob("*__*.jsonl")):
        label, policy = f.stem.rsplit("__", 1)
        data[(label, policy)] = read_jsonl(f)
    if not data:
        raise SystemExit(f"no token files under {run}/tokens; run evals.kl_exact first")
    return data


def summarise(rows: list[dict], by: str) -> dict:
    s = {m: estimate(rows, m) for m in METRICS}
    groups = defaultdict(list)
    for r in rows:
        if r.get(by):
            groups[r[by]].append(r)
    s["by"] = {g: estimate(rs) for g, rs in sorted(groups.items())}
    s["position"] = {name: estimate(rows, "kl", lo, hi) for lo, hi, name in BUCKETS}
    s["targeted_ratio"] = targeted_ratio(rows)
    return s


def sweep_point(scales: dict[str, float]) -> tuple[str, float] | None:
    """Which sweep a variant belongs to: ('all', s) if every adapter has scale s, ('last', s) if
    the earlier adapters are at 1 and only the last is scaled."""
    v = list(scales.values())
    if len(set(v)) == 1:
        return "all", v[0]
    if all(x == 1 for x in v[:-1]):
        return "last", v[-1]
    return None


def fmt(e: dict, digits: int = 4) -> str:
    if not e or e.get("est") is None:
        return "-"
    if e.get("lo") is None:
        return f"{e['est']:.{digits}f}"
    return f"{e['est']:.{digits}f} [{e['lo']:.{digits}f}, {e['hi']:.{digits}f}]"


# ---------------------------------------------------------------- plots

INK, MUTED, GRID, SURFACE = "#0b0b0b", "#898781", "#e1e0d9", "#fcfcfb"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]


def _axes(title: str, w=7.5, h=4.6):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(w, h), facecolor=SURFACE)
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color("#c3c2b7")
    ax.tick_params(colors=MUTED, labelsize=9)
    ax.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.set_title(title, loc="left", fontsize=11, color=INK, pad=12)
    return fig, ax


def plot_scale(summary: dict, run_meta: dict, out: Path) -> bool:
    series = defaultdict(list)
    for key, s in summary.items():
        label, policy = key.rsplit("__", 1)
        scales = run_meta.get("variants", {}).get(label)
        pt = sweep_point(scales) if scales else None
        if pt and s["kl"]["est"] is not None:
            kinds = [pt[0]] if pt[0] == "last" or pt[1] != 1 or len(scales) == 1 else ["all", "last"]
            for kind in kinds:
                name = label.split("@")[0] + (" (last adapter only)" if kind == "last" else "")
                series[(name, policy)].append((pt[1], s["kl"]))
    series = {k: sorted(v, key=lambda p: p[0]) for k, v in series.items() if len(v) >= 3}
    if not series:
        return False
    fig, ax = _axes("KL from base vs adapter strength (95% CI, bootstrap over scenarios)")
    for (k, pts), color in zip(sorted(series.items()), SERIES):   # at most 8 series, fixed order
        x = [p[0] for p in pts]
        y = [p[1]["est"] for p in pts]
        err = [[p[1]["est"] - (p[1]["lo"] if p[1]["lo"] is not None else p[1]["est"]) for p in pts],
               [(p[1]["hi"] if p[1]["hi"] is not None else p[1]["est"]) - p[1]["est"] for p in pts]]
        ax.errorbar(x, y, yerr=err, color=color, linewidth=2, marker="o", markersize=6, capsize=3,
                    elinewidth=1.2, linestyle="-" if k[1] == "base" else "--",
                    label=f"{k[0]} · {k[1]}-policy text")
    ax.axvline(1, color=MUTED, linewidth=0.8, linestyle=":")
    ax.set_ylim(bottom=0)
    ax.set_xlabel("adapter strength (0 = base model, 1 = as trained)", color=MUTED, fontsize=9)
    ax.set_ylabel("nats per token", color=MUTED, fontsize=9)
    ax.legend(frameon=False, fontsize=8, labelcolor=INK)
    fig.tight_layout()
    fig.savefig(out, dpi=160)
    return True


def plot_categories(summary: dict, keys: list[str], out: Path) -> bool:
    keys = [k for k in keys if summary[k]["by"]][:4]
    if not keys:
        return False
    cats = sorted(summary[keys[0]]["by"], key=lambda c: summary[keys[0]]["by"][c]["est"] or 0)
    fig, ax = _axes("KL from base by scenario category (95% CI)", h=0.34 * len(cats) + 1.6)
    for j, (k, color) in enumerate(zip(keys, SERIES)):
        ys = [i + (j - (len(keys) - 1) / 2) * 0.18 for i in range(len(cats))]
        es = [summary[k]["by"].get(c, {}) for c in cats]
        x = [e.get("est") or 0 for e in es]
        err = [[xi - (e.get("lo") if e.get("lo") is not None else xi) for xi, e in zip(x, es)],
               [(e.get("hi") if e.get("hi") is not None else xi) - xi for xi, e in zip(x, es)]]
        ax.errorbar(x, ys, xerr=err, fmt="o", color=color, markersize=6, capsize=2.5, elinewidth=1.2,
                    label=k.replace("__", " · "))
    ax.set_yticks(range(len(cats)), cats)
    ax.tick_params(axis="y", labelcolor=INK)
    ax.set_xlim(left=0)
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("nats per token", color=MUTED, fontsize=9)
    ax.legend(frameon=False, fontsize=8, labelcolor=INK, loc="lower right")
    fig.tight_layout()
    fig.savefig(out, dpi=160)
    return True


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("run", type=Path, help="the --out folder of evals.kl_exact")
    ap.add_argument("--by", default="category", choices=["category", "axis"])
    ap.add_argument("--contrast", nargs=2, action="append", default=[], metavar=("A", "B"),
                    help="paired difference A - B (variant labels); repeatable")
    ap.add_argument("--no-plots", action="store_true")
    a = ap.parse_args()

    data = load(a.run)
    run_meta = json.loads((a.run / "run.json").read_text()) if (a.run / "run.json").exists() else {}
    order = list(run_meta.get("variants", {}))            # the order the variants were asked for
    keys = sorted(data, key=lambda k: (k[0].split("@")[0], k[1], order.index(k[0]) if k[0] in order else 0))
    summary = {f"{l}__{p}": summarise(data[(l, p)], a.by) for l, p in keys}

    # contrasts: the ones asked for, plus every pair of as-trained variants
    full = [l for (l, p) in data if "@" not in l and p == "base"]
    pairs = [tuple(c) for c in a.contrast] + [(x, y) for i, x in enumerate(full) for y in full[:i]]
    contrasts = []
    for x, y in dict.fromkeys(pairs):
        for p in ("base", "self"):
            if (x, p) in data and (y, p) in data:
                contrasts.append({"a": x, "b": y, "policy": p, **contrast(data[(x, p)], data[(y, p)])})

    (a.run / "summary.json").write_text(json.dumps({"variants": summary, "contrasts": contrasts}, indent=1))

    L = ["# KL from base", "",
         f"Base `{run_meta.get('base', '?')}`, {run_meta.get('scenarios', '?')} scenarios x {run_meta.get('n', '?')} "
         f"continuations x up to {run_meta.get('max_new_tokens', '?')} tokens. Nats per token, 95% interval "
         "from a bootstrap over scenarios.", "",
         "| variant | text from | KL(variant‖base) | reverse KL | JS | top-1 agree | old sampled-token estimate | targeted ratio |",
         "|---|---|---|---|---|---|---|---|"]
    for key, s in summary.items():
        label, policy = key.rsplit("__", 1)
        L.append(f"| `{label}` | {policy} | {fmt(s['kl'])} | {fmt(s['rkl'])} | {fmt(s['js'])} | "
                 f"{fmt(s['agree'], 3)} | {fmt(s['lr']) if policy == 'self' else '-'} | {fmt(s['targeted_ratio'], 2)} |")
    if contrasts:
        L += ["", "## Paired differences", "", "| A | B | text from | KL(A) − KL(B) | differs? |", "|---|---|---|---|---|"]
        for c in contrasts:
            L.append(f"| `{c['a']}` | `{c['b']}` | {c['policy']} | {fmt(c)} | "
                     f"{'yes' if c.get('excludes_zero') else 'no'} |")
    shown = [k for k in summary if "@" not in k] or list(summary)
    L += ["", f"## By {a.by}", "", f"| {a.by} | " + " | ".join(f"`{k}`" for k in shown) + " |",
          "|---|" + "---|" * len(shown)]
    for g in sorted({g for k in shown for g in summary[k]["by"]}):
        L.append(f"| {g} | " + " | ".join(fmt(summary[k]["by"].get(g)) for k in shown) + " |")
    L += ["", "## By position in the reply", "", "| token | " + " | ".join(f"`{k}`" for k in shown) + " |",
          "|---|" + "---|" * len(shown)]
    for _, _, name in BUCKETS:
        L.append(f"| {name} | " + " | ".join(fmt(summary[k]["position"][name]) for k in shown) + " |")
    if not a.no_plots:
        if plot_scale(summary, run_meta, a.run / "kl_vs_scale.png"):
            L += ["", "![KL vs adapter strength](kl_vs_scale.png)"]
        if plot_categories(summary, shown, a.run / "kl_by_category.png"):
            L += ["", "![KL by category](kl_by_category.png)"]
    (a.run / "report.md").write_text("\n".join(L) + "\n")
    print("\n".join(L[:6 + len(summary) + (len(contrasts) + 4 if contrasts else 0)]))
    print(f"\n[kl_stats] wrote {a.run}/report.md, summary.json")


if __name__ == "__main__":
    main()
