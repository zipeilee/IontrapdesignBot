"""Simplified two-layer (blade-like / dual-planar) trap placeholder.

The two electrode layers face each other across ``layer_gap`` in z.  In
the 2D layout they are drawn superimposed on different GDS layers:
layer 0 -> (1, 0), layer 1 -> (4, 0).  Each layer holds ``n_segments``
rectangular DC electrodes segmented along the trap axis x.
"""

from __future__ import annotations

import numpy as np

from ..common import Electrode, ElectrodeSet

__all__ = ["two_layer"]

LAYER_0 = (1, 0)
LAYER_1 = (4, 0)


def _rect(x0: float, y0: float, x1: float, y1: float) -> np.ndarray:
    """Axis-aligned rectangle as a (4, 2) vertex array."""
    return np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], dtype=float)


def two_layer(
    layer_gap: float = 100.0,
    electrode_width: float = 200.0,
    electrode_length: float = 500.0,
    n_segments: int = 5,
    segment_gap: float = 10.0,
) -> ElectrodeSet:
    """Generate a simplified two-layer (dual-planar / blade-like) trap.

    Parameters
    ----------
    layer_gap:
        Vertical (z) separation between the two electrode planes (µm).
        Recorded in ``meta`` only — the 2D layout draws both layers
        superimposed on separate GDS layers.
    electrode_width:
        Width of each electrode along y (µm), centred on y = 0.
    electrode_length:
        Length of each segment along x (µm).
    n_segments:
        Number of segments per layer along x.
    segment_gap:
        Gap between neighbouring segments along x (µm).

    Returns
    -------
    ElectrodeSet
        Electrodes ``L0_DC0`` .. ``L0_DC<n-1>`` on GDS layer (1, 0) and
        ``L1_DC0`` .. ``L1_DC<n-1>`` on GDS layer (4, 0); segment 0 sits
        at the -x end.  ``meta`` records all parameters (including
        ``layer_gap``).
    """
    if n_segments < 1:
        raise ValueError("n_segments must be >= 1")

    total = n_segments * electrode_length + (n_segments - 1) * segment_gap
    x0_base = -total / 2.0
    wy = electrode_width / 2.0

    electrodes: list[Electrode] = []
    for layer_idx, layer in ((0, LAYER_0), (1, LAYER_1)):
        for i in range(n_segments):
            x0 = x0_base + i * (electrode_length + segment_gap)
            x1 = x0 + electrode_length
            electrodes.append(
                Electrode(
                    name=f"L{layer_idx}_DC{i}",
                    polygons=[_rect(x0, -wy, x1, wy)],
                    kind="dc",
                    layer=layer,
                )
            )

    meta = dict(
        type="two_layer",
        layer_gap=layer_gap,
        electrode_width=electrode_width,
        electrode_length=electrode_length,
        n_segments=n_segments,
        segment_gap=segment_gap,
        layers={"L0": LAYER_0, "L1": LAYER_1},
        units="um",
    )
    return ElectrodeSet(electrodes=electrodes, meta=meta)
