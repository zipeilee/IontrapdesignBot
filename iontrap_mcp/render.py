"""Render an ElectrodeSet layout to PNG with matplotlib (Agg backend)."""

from __future__ import annotations

import os

os.environ.setdefault("MPLCONFIGDIR", "/tmp/mpl-iontrapclaw")

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.collections import PatchCollection
from matplotlib.patches import Polygon as MplPolygon

from .common import ElectrodeSet

_KIND_COLOR = {
    "dc": "#4C9AFF",      # blue
    "rf": "#FF6B6B",      # red
    "ground": "#8E9AAF",  # grey
    "trace": "#57D9A3",   # green
}

_LAYER_COLOR = {
    (1, 0): "#4C9AFF",
    (2, 0): "#FF6B6B",
    (3, 0): "#8E9AAF",
    (4, 0): "#B083F0",
    (5, 0): "#57D9A3",
}


def _color(e) -> str:
    if tuple(e.layer) in _LAYER_COLOR:
        return _LAYER_COLOR[tuple(e.layer)]
    return _KIND_COLOR.get(e.kind, "#CCCCCC")


def render(
    es: ElectrodeSet,
    path: str,
    *,
    figsize: tuple[float, float] = (12, 8),
    labels: bool = True,
    title: str | None = None,
    xlim: tuple[float, float] | None = None,
    ylim: tuple[float, float] | None = None,
) -> str:
    """Draw the layout and write a PNG. Returns the absolute path."""
    fig, ax = plt.subplots(figsize=figsize)
    for e in es.electrodes:
        patches = [MplPolygon(p, closed=True) for p in e.polygons]
        pc = PatchCollection(
            patches, facecolor=_color(e), edgecolor="black", linewidths=0.3, alpha=0.85
        )
        ax.add_collection(pc)
        if labels:
            c = e.polygons[0].mean(axis=0)
            ax.annotate(
                e.name, tuple(c), ha="center", va="center", fontsize=6, color="black"
            )
    ax.autoscale_view()
    ax.set_aspect("equal")
    ax.set_xlabel("x (µm)")
    ax.set_ylabel("y (µm)")
    if xlim:
        ax.set_xlim(*xlim)
    if ylim:
        ax.set_ylim(*ylim)
    ax.set_title(title or "IonTrapClaw layout")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return os.path.abspath(path)
