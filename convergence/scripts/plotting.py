"""Matplotlib helpers shared by the experiment scripts (static PNGs)."""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402

SURFACE = "#fcfcfb"
TEXT = "#0b0b0b"
MUTED = "#52514e"
GRID = "#e4e3df"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
BLUES = LinearSegmentedColormap.from_list(
    "blues", ["#cde2fb", "#86b6ef", "#3987e5", "#256abf", "#184f95", "#0d366b"]
)

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "text.color": TEXT, "axes.labelcolor": MUTED, "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.edgecolor": GRID, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8,
    "axes.spines.top": False, "axes.spines.right": False, "font.size": 10,
    "axes.titlesize": 10, "axes.titleweight": "bold", "legend.frameon": False,
})


def heatmap(ax, matrix, labels, title):
    """Similarity matrix with its own colour scale (scales differ between metrics)."""
    lo, hi = float(matrix.min()), float(matrix.max())
    im = ax.imshow(matrix, cmap=BLUES, vmin=lo, vmax=hi)
    ax.set_xticks(range(len(labels)), labels)
    ax.set_yticks(range(len(labels)), labels)
    ax.grid(False)
    for i in range(len(labels)):
        for j in range(len(labels)):
            v = matrix[i, j]
            dark = (v - lo) / (hi - lo + 1e-12) > 0.55
            ax.text(j, i, f"{v:.3f}", ha="center", va="center", fontsize=8,
                    color="#ffffff" if dark else TEXT)
    ax.set_title(title, loc="left")
    return im
