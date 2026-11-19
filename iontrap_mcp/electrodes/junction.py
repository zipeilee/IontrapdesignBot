"""X- and T-junction surface traps built from analytic coordinates.

Two linear-trap corridors (along x and, for the branch, along y) meet at
a central square RF island.  The geometry is derived so that every pair
of adjacent electrodes is separated by *exactly* the relevant gap
parameter — no boolean post-processing is used.

Derived quantities (h = half island side).  The island spans the full
corridor cross-section (centre strip + gaps + both RF rails) so that
rails of perpendicular arms never cross::

    h      = center_width/2 + rf_gap + rf_width
    rf_y0  = center_width/2 + rf_gap          (RF rail inner edge)
    rf_y1  = rf_y0 + rf_width = h             (RF rail outer edge)
    dc_y0  = rf_y1 + rf_gap                   (DC row inner edge)
    dc_y1  = dc_y0 + dc_width                 (DC row outer edge)

Per quadrant there is a square corner DC electrode occupying
[dc_y0, dc_y1] x [dc_y0, dc_y1]; the arm DC segments start at
``dc_y1 + dc_gap`` so they keep exactly ``dc_gap`` from the corner
electrode.  RF rails start at ``h + rf_gap`` (exactly ``rf_gap`` from the
island) and run to the outer end of the DC row.

A grounded centre strip (kind ``"ground"``) runs down each arm between
the two RF rails — without it the two rails at the same RF potential act
as a single wide conductor and the arm has *no* RF null.  The strip spans
the same arm extent as the RF rails, leaving exactly ``rf_gap`` to both
the rails and the island.  Disable with ``center_strip=False`` (e.g. to
model a design where the centre conductor is routed on another layer).
"""

from __future__ import annotations

import numpy as np

from ..common import Electrode, ElectrodeSet

__all__ = ["x_junction", "t_junction"]


def _rect(x0: float, y0: float, x1: float, y1: float) -> np.ndarray:
    """Axis-aligned rectangle as a (4, 2) vertex array."""
    return np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], dtype=float)


def _mirror_x(poly: np.ndarray) -> np.ndarray:
    out = poly.copy()
    out[:, 0] *= -1.0
    return out


def _mirror_y(poly: np.ndarray) -> np.ndarray:
    out = poly.copy()
    out[:, 1] *= -1.0
    return out


def _junction(
    y_arms: tuple[str, ...],
    arm_dc_segments: int,
    dc_width: float,
    dc_gap: float,
    rf_width: float,
    rf_gap: float,
    center_width: float,
    dc_length: float,
    center_strip: bool,
) -> ElectrodeSet:
    """Shared builder; ``y_arms`` selects the branch arms ("YP", "YN")."""
    if arm_dc_segments < 1:
        raise ValueError("arm_dc_segments must be >= 1")

    # Island half side: spans the full corridor cross-section so that
    # perpendicular arm rails terminate rf_gap away from each other.
    h = center_width / 2.0 + rf_gap + rf_width
    rf_y0 = center_width / 2.0 + rf_gap
    rf_y1 = rf_y0 + rf_width
    dc_y0 = rf_y1 + rf_gap
    dc_y1 = dc_y0 + dc_width
    corner_end = dc_y1 + dc_gap  # arm DCs start here

    arm_span = arm_dc_segments * dc_length + (arm_dc_segments - 1) * dc_gap
    arm_end = corner_end + arm_span  # outer end of rails and DC rows

    electrodes: list[Electrode] = []

    # Central RF island
    electrodes.append(
        Electrode(
            name="RF_CENTER",
            polygons=[_rect(-h, -h, h, h)],
            kind="rf",
        )
    )

    # RF rails along the x arms: two polygons each (above/below centre).
    for sign, tag in ((1.0, "XP"), (-1.0, "XN")):
        upper = _rect(h + rf_gap, rf_y0, arm_end, rf_y1)
        lower = _mirror_y(upper)
        polys = [upper, lower] if sign > 0 else [_mirror_x(upper), _mirror_x(lower)]
        electrodes.append(Electrode(name=f"RF_{tag}", polygons=polys, kind="rf"))

    # RF rails along the y branch arms: two polygons each (right/left).
    for tag in y_arms:
        sign = 1.0 if tag == "YP" else -1.0
        right = _rect(rf_y0, h + rf_gap, rf_y1, arm_end)
        left = _mirror_x(right)
        polys = [right, left] if sign > 0 else [_mirror_y(right), _mirror_y(left)]
        electrodes.append(Electrode(name=f"RF_{tag}", polygons=polys, kind="rf"))

    # Grounded centre strip along each arm, between the RF rails.  Without
    # it the two same-potential rails act as one wide conductor and the arm
    # corridor has no RF null.  Runs from rf_gap outside the island to the
    # outer end of the arm, exactly like the rails.
    if center_strip:
        w = center_width / 2.0
        for sign, tag in ((1.0, "XP"), (-1.0, "XN")):
            strip = _rect(h + rf_gap, -w, arm_end, w)
            if sign < 0:
                strip = _mirror_x(strip)
            electrodes.append(
                Electrode(name=f"CENTER_{tag}", polygons=[strip], kind="ground")
            )
        for tag in y_arms:
            sign = 1.0 if tag == "YP" else -1.0
            strip = _rect(-w, h + rf_gap, w, arm_end)
            if sign < 0:
                strip = _mirror_y(strip)
            electrodes.append(
                Electrode(name=f"CENTER_{tag}", polygons=[strip], kind="ground")
            )

    # Corner DC electrodes, one per quadrant that has both arms.
    x_tags = (("P", 1.0), ("N", -1.0))
    y_tags = tuple(
        (("P", 1.0) if t == "YP" else ("N", -1.0)) for t in y_arms
    )
    for xs, sx in x_tags:
        for ys, sy in y_tags:
            corner = _rect(dc_y0, dc_y0, dc_y1, dc_y1)
            if sx < 0:
                corner = _mirror_x(corner)
            if sy < 0:
                corner = _mirror_y(corner)
            electrodes.append(
                Electrode(
                    name=f"DC_CORNER_{xs}{ys}",
                    polygons=[corner],
                    kind="dc",
                )
            )

    # Segmented DC electrodes on the x arms (U = y > 0, L = y < 0).
    for sign, tag in ((1.0, "XP"), (-1.0, "XN")):
        for i in range(arm_dc_segments):
            x0 = corner_end + i * (dc_length + dc_gap)
            x1 = x0 + dc_length
            up = _rect(x0, dc_y0, x1, dc_y1)
            lo = _mirror_y(up)
            if sign < 0:
                up, lo = _mirror_x(up), _mirror_x(lo)
            electrodes.append(
                Electrode(name=f"DC_{tag}{i}_U", polygons=[up], kind="dc")
            )
            electrodes.append(
                Electrode(name=f"DC_{tag}{i}_L", polygons=[lo], kind="dc")
            )

    # Segmented DC electrodes on the y branch arms (R = x > 0, L = x < 0).
    for tag in y_arms:
        sign = 1.0 if tag == "YP" else -1.0
        for i in range(arm_dc_segments):
            y0 = corner_end + i * (dc_length + dc_gap)
            y1 = y0 + dc_length
            right = _rect(dc_y0, y0, dc_y1, y1)
            left = _mirror_x(right)
            if sign < 0:
                right, left = _mirror_y(right), _mirror_y(left)
            electrodes.append(
                Electrode(name=f"DC_{tag}{i}_R", polygons=[right], kind="dc")
            )
            electrodes.append(
                Electrode(name=f"DC_{tag}{i}_L", polygons=[left], kind="dc")
            )

    return electrodes


def x_junction(
    arm_dc_segments: int = 6,
    dc_width: float = 50.0,
    dc_gap: float = 4.0,
    rf_width: float = 25.0,
    rf_gap: float = 5.0,
    center_width: float = 15.0,
    dc_length: float = 80.0,
    center_strip: bool = True,
) -> ElectrodeSet:
    """Generate an X-junction surface trap (two crossing linear traps).

    Parameters
    ----------
    arm_dc_segments:
        Number of DC segment pairs per arm (four arms).
    dc_width, dc_gap, rf_width, rf_gap, center_width, dc_length:
        Same meaning as in :func:`iontrap_mcp.electrodes.surface.five_wire`;
        ``dc_length``/``dc_gap`` run along each arm.
    center_strip:
        If True (default), add a grounded centre strip (``CENTER_XP`` /
        ``CENTER_XN`` / ``CENTER_YP`` / ``CENTER_YN``, kind ``"ground"``)
        between the RF rails of each arm.  Required for an RF null to
        exist along the arm corridors.

    Returns
    -------
    ElectrodeSet
        RF electrodes: ``RF_CENTER`` (square island, side
        ``center_width + 2*rf_gap + 2*rf_width``, centred on the origin),
        ``RF_XP``/``RF_XN``/``RF_YP``/``RF_YN`` (two rail polygons each).
        Ground electrodes: ``CENTER_<arm>`` per arm when ``center_strip``.
        DC electrodes: ``DC_CORNER_<xs><ys>`` per quadrant (xs/ys in
        {P, N} for the x/y sign) and ``DC_<arm><i>_<side>`` where arm is
        XP/XN/YP/YN, i = 0 is innermost, and side is U/L (x arms,
        y > 0 / y < 0) or R/L (y arms, x > 0 / x < 0).
        ``meta`` records all geometry parameters.
    """
    electrodes = _junction(
        ("YP", "YN"),
        arm_dc_segments, dc_width, dc_gap, rf_width, rf_gap,
        center_width, dc_length, center_strip,
    )
    meta = dict(
        type="x_junction",
        arm_dc_segments=arm_dc_segments,
        dc_width=dc_width,
        dc_gap=dc_gap,
        rf_width=rf_width,
        rf_gap=rf_gap,
        center_width=center_width,
        dc_length=dc_length,
        center_strip=center_strip,
        units="um",
    )
    return ElectrodeSet(electrodes=electrodes, meta=meta)


def t_junction(
    arm_dc_segments: int = 6,
    dc_width: float = 50.0,
    dc_gap: float = 4.0,
    rf_width: float = 25.0,
    rf_gap: float = 5.0,
    center_width: float = 15.0,
    dc_length: float = 80.0,
    center_strip: bool = True,
) -> ElectrodeSet:
    """Generate a T-junction surface trap (x main trap + one y branch).

    Same parameters as :func:`x_junction`.  The branch extends to
    y > 0 only, so the RF electrodes are ``RF_CENTER``, ``RF_XP``,
    ``RF_XN`` and ``RF_YP``, and corner electrodes exist only in the two
    upper quadrants (``DC_CORNER_PP``, ``DC_CORNER_NP``).  Centre strips
    (when ``center_strip``) are ``CENTER_XP`` / ``CENTER_XN`` /
    ``CENTER_YP``.

    Returns
    -------
    ElectrodeSet
        Naming follows :func:`x_junction`; ``meta`` records all geometry
        parameters.
    """
    electrodes = _junction(
        ("YP",),
        arm_dc_segments, dc_width, dc_gap, rf_width, rf_gap,
        center_width, dc_length, center_strip,
    )
    meta = dict(
        type="t_junction",
        arm_dc_segments=arm_dc_segments,
        dc_width=dc_width,
        dc_gap=dc_gap,
        rf_width=rf_width,
        rf_gap=rf_gap,
        center_width=center_width,
        dc_length=dc_length,
        center_strip=center_strip,
        units="um",
    )
    return ElectrodeSet(electrodes=electrodes, meta=meta)
