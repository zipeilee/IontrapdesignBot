"""Segmented-DC surface linear trap (five-wire style).

The trap axis (ion-chain direction) is x; all electrodes lie in the
z = 0 plane.  From the centre outwards in |y|:

    CENTER strip -> rf_gap -> RF rail -> rf_gap -> segmented DC row
    (-> rf_gap -> optional outer DC rail)

Everything is symmetric about both the x and y axes.
"""

from __future__ import annotations

import numpy as np

from ..common import Electrode, ElectrodeSet

__all__ = ["five_wire"]


def _rect(x0: float, y0: float, x1: float, y1: float) -> np.ndarray:
    """Axis-aligned rectangle as a (4, 2) vertex array."""
    return np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], dtype=float)


def five_wire(
    n_dc_segments: int = 11,
    dc_length: float = 100.0,
    dc_width: float = 60.0,
    dc_gap: float = 5.0,
    rf_width: float = 30.0,
    rf_gap: float = 5.0,
    center_width: float = 20.0,
    outer_dc: bool = True,
    length_pad: float = 200.0,
) -> ElectrodeSet:
    """Generate a five-wire surface linear trap with segmented DC rails.

    Parameters
    ----------
    n_dc_segments:
        Number of DC segments *per side* along the trap axis.  The
        segments come in mirror-symmetric pairs ``DC<i>_U`` (y > 0) and
        ``DC<i>_L`` (y < 0), ordered along x (segment 0 at -x end).
    dc_length:
        Length of each DC segment along x (µm).
    dc_width:
        Width of the segmented DC electrodes along y (µm).
    dc_gap:
        Gap between neighbouring DC segments along x (µm).
    rf_width:
        Width of the RF rails along y (µm).
    rf_gap:
        Gap between centre strip and RF rail, between RF rail and the
        segmented DC row, and between the DC row and the outer rail (µm).
    center_width:
        Width of the central DC strip along y (µm).  Its length along x
        equals the total segmented-region length.
    outer_dc:
        If True, add continuous outer DC/ground rails ``DC_OUTER_U`` /
        ``DC_OUTER_L`` (width ``dc_width``) outside the segmented rows.
    length_pad:
        Extra length added at each ±x end of the RF (and outer DC) rails
        beyond the segmented region (µm).  RF rail total length is
        ``segmented_length + 2 * length_pad``.

    Returns
    -------
    ElectrodeSet
        Electrodes: ``RF_L`` (y < 0), ``RF_R`` (y > 0), ``CENTER``,
        ``DC<i>_U`` / ``DC<i>_L`` for i in range(n_dc_segments), and
        optionally ``DC_OUTER_U`` / ``DC_OUTER_L``.  ``meta`` records all
        geometry parameters plus the derived ``segmented_length``.
    """
    if n_dc_segments < 1:
        raise ValueError("n_dc_segments must be >= 1")

    seg_len = n_dc_segments * dc_length + (n_dc_segments - 1) * dc_gap
    x_seg0 = -seg_len / 2.0
    x_rail0 = x_seg0 - length_pad
    x_rail1 = -x_rail0

    rf_y0 = center_width / 2.0 + rf_gap
    rf_y1 = rf_y0 + rf_width
    dc_y0 = rf_y1 + rf_gap
    dc_y1 = dc_y0 + dc_width

    electrodes: list[Electrode] = []

    # RF rails (full length incl. pad)
    electrodes.append(
        Electrode(
            name="RF_R",
            polygons=[_rect(x_rail0, rf_y0, x_rail1, rf_y1)],
            kind="rf",
        )
    )
    electrodes.append(
        Electrode(
            name="RF_L",
            polygons=[_rect(x_rail0, -rf_y1, x_rail1, -rf_y0)],
            kind="rf",
        )
    )

    # Central DC strip
    electrodes.append(
        Electrode(
            name="CENTER",
            polygons=[_rect(x_seg0, -center_width / 2.0, -x_seg0, center_width / 2.0)],
            kind="dc",
        )
    )

    # Segmented DC pairs, ordered along x
    for i in range(n_dc_segments):
        x0 = x_seg0 + i * (dc_length + dc_gap)
        x1 = x0 + dc_length
        electrodes.append(
            Electrode(
                name=f"DC{i}_U",
                polygons=[_rect(x0, dc_y0, x1, dc_y1)],
                kind="dc",
            )
        )
        electrodes.append(
            Electrode(
                name=f"DC{i}_L",
                polygons=[_rect(x0, -dc_y1, x1, -dc_y0)],
                kind="dc",
            )
        )

    # Optional outer DC/ground rails
    if outer_dc:
        out_y0 = dc_y1 + rf_gap
        out_y1 = out_y0 + dc_width
        electrodes.append(
            Electrode(
                name="DC_OUTER_U",
                polygons=[_rect(x_rail0, out_y0, x_rail1, out_y1)],
                kind="dc",
            )
        )
        electrodes.append(
            Electrode(
                name="DC_OUTER_L",
                polygons=[_rect(x_rail0, -out_y1, x_rail1, -out_y0)],
                kind="dc",
            )
        )

    meta = dict(
        type="five_wire",
        n_dc_segments=n_dc_segments,
        dc_length=dc_length,
        dc_width=dc_width,
        dc_gap=dc_gap,
        rf_width=rf_width,
        rf_gap=rf_gap,
        center_width=center_width,
        outer_dc=outer_dc,
        length_pad=length_pad,
        segmented_length=seg_len,
        units="um",
    )
    return ElectrodeSet(electrodes=electrodes, meta=meta)
