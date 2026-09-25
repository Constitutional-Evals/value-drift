"""Shared figure style: Myriad Pro, white surface, hairline grid, validated palette."""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402

for f in Path('~/Library/Fonts').expanduser().glob('*'):
    if 'myriad' in f.name.lower():
        font_manager.fontManager.addfont(str(f))

INK, INK2, MUTED, GRID, SURFACE = '#0b0b0b', '#52514e', '#8b8a85', '#e6e5e1', '#ffffff'
# Reference categorical order (validated adjacent-CVD safe); first 3 validate all-pairs.
CAT = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#4a3aa7', '#e34948']
BLUE_RAMP = ['#cde2fb', '#9ec5f4', '#6da7ec', '#3987e5', '#256abf', '#184f95', '#0d366b']
DIV_NEG, DIV_MID, DIV_POS = '#e34948', '#f0efec', '#2a78d6'
LIGHT_GRAY = '#d6d5d0'

plt.rcParams.update({
    'font.family': 'Myriad Pro', 'font.size': 10.5, 'axes.titlesize': 12, 'axes.titleweight': 'semibold',
    'axes.titlelocation': 'left', 'axes.titlepad': 10, 'axes.labelsize': 10.5, 'axes.labelcolor': INK2,
    'axes.edgecolor': GRID, 'axes.linewidth': 0.8, 'axes.spines.top': False, 'axes.spines.right': False,
    'axes.grid': False, 'grid.color': GRID, 'grid.linewidth': 0.8, 'grid.linestyle': '-',
    'xtick.color': INK2, 'ytick.color': INK2, 'xtick.labelsize': 9.5, 'ytick.labelsize': 9.5,
    'xtick.major.size': 0, 'ytick.major.size': 0, 'xtick.major.pad': 5, 'ytick.major.pad': 5,
    'text.color': INK, 'figure.facecolor': SURFACE, 'axes.facecolor': SURFACE, 'savefig.facecolor': SURFACE,
    'legend.frameon': False, 'legend.fontsize': 9.5, 'lines.solid_capstyle': 'round',
    'pdf.fonttype': 42, 'svg.fonttype': 'none', 'figure.dpi': 110,
})

FIGDIR = Path(__file__).resolve().parents[1] / 'reports' / '05_elicitation' / 'figures'


def grid(ax, axis='x'):
    ax.grid(True, axis=axis, color=GRID, linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)


def save(fig, name):
    FIGDIR.mkdir(parents=True, exist_ok=True)
    for ext in ('png', 'pdf'):
        fig.savefig(FIGDIR / f'{name}.{ext}', dpi=220 if ext == 'png' else None, bbox_inches='tight', pad_inches=0.15)
    plt.close(fig)
    return FIGDIR / f'{name}.png'
