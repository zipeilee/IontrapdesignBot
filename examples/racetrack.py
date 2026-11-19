"""Racetrack (H2-like) trap geometry builder — escape-hatch style demo.

Quantinuum H2 avoids junctions entirely: two concentric RF electrodes form
a closed stadium-shaped RF-null loop; ions circulate like a conveyor belt.

Radial order from the corridor centreline outward (all µm)::

    CENTER ground capsule | gap | RF_INNER ring | gap | GND_MID ring
    | gap | RF_OUTER ring | gap | DC segments (straights) + GND end caps

The RF null sits above the grounded GND_MID ring — the exact analogue of
the five-wire centre strip wrapped into a closed loop.
"""

from __future__ import annotations

import numpy as np
from shapely.geometry import LineString, Point, box
from shapely.ops import unary_union

from iontrap_mcp.common import Electrode, ElectrodeSet

__all__ = ["racetrack"]


def _capsule(half_len: float, radius: float, resolution: int = 96):
    """Stadium (discorectangle): line segment buffered by ``radius``."""
    return LineString([(-half_len, 0.0), (half_len, 0.0)]).buffer(
        radius, resolution=resolution
    )


def _ring(half_len: float, r_in: float, r_out: float):
    return _capsule(half_len, r_out).difference(_capsule(half_len, r_in))


def _coords(poly) -> np.ndarray:
    return np.array(poly.exterior.coords, dtype=float)


def _largest_polygon(geom):
    """Extract the largest Polygon from any shapely geometry result."""
    if geom.geom_type == "Polygon":
        return geom
    polys = [g for g in getattr(geom, "geoms", []) if g.geom_type == "Polygon"]
    if not polys:
        raise ValueError(f"no polygon in {geom.geom_type}")
    return max(polys, key=lambda g: g.area)


def _half_rings(half_len: float, r_in: float, r_out: float) -> list[np.ndarray]:
    """Annulus as two simple polygons (upper/lower halves).

    The layout data model has no holes, so a stadium ring (which would be a
    polygon with a hole) is split at y = 0 into two half-rings.
    """
    ring = _ring(half_len, r_in, r_out)
    big = 4 * (half_len + r_out)
    upper = ring.intersection(box(-big, 0.0, big, big))
    lower = ring.intersection(box(-big, -big, big, 0.0))
    return [_coords(upper), _coords(lower)]


def racetrack(
    half_length: float = 400.0,
    center_width: float = 40.0,
    rf_width: float = 30.0,
    rf_gap: float = 8.0,
    mid_width: float = 20.0,
    dc_width: float = 50.0,
    dc_gap: float = 5.0,
    dc_length: float = 90.0,
    n_dc_segments: int = 8,
    bend_shift: float = 0.0,
    bend_trim: float = 0.0,
    bend_profile: list[float] | None = None,
) -> ElectrodeSet:
    """Build a racetrack surface trap (H2-like, junction-free).

    Parameters
    ----------
    half_length:
        Half the length of each straight section along x (µm); the two
        straights are joined by semicircles.
    center_width:
        Full width of the central ground capsule (µm).
    rf_width, rf_gap:
        Width of each concentric RF ring and of every gap (µm).
    mid_width:
        Width of the grounded ring between the two RF rings — the ion
        corridor sits above it (µm).
    dc_width, dc_gap, dc_length, n_dc_segments:
        Segmented DC rows outside the outer RF ring along each straight.
        Curved end caps are covered by ground half-rings.
    bend_shift:
        Extra radius (µm) added to every concentric boundary on the two
        semicircular bends.  Curvature breaks the cross-section symmetry
        (inner rails shorter than outer), which displaces the RF null on
        the bends relative to the straights; sweeping ``bend_shift``
        re-balances the bends so the null follows a smooth loop.
    bend_trim:
        Bend-local RF rebalance (µm): on the bends the inner RF rail is
        widened by ``bend_trim`` and the outer RF rail narrowed by the
        same amount, compensating the curvature asymmetry (outer rails
        span more arc length, hence contribute more field).  Use this to
        flatten the null-height sag on the bends.
    bend_profile:
        Full bend cross-section control: 7 deltas (µm)
        ``[center, rf_in_inner, rf_in_outer, mid_inner, mid_outer,
        rf_out_inner, rf_out_outer]`` overriding every concentric
        boundary radius on the bends.  When given, ``bend_shift`` and
        ``bend_trim`` are ignored.  Use for free-form bend optimization.

    Returns
    -------
    ElectrodeSet
        ``CENTER`` (ground), ``RF_INNER`` / ``RF_OUTER`` (rf, two
        half-ring polygons each — the data model has no holes, so rings
        are split at y = 0), ``GND_MID`` (ground), ``DC_T<i>`` /
        ``DC_B<i>`` segment pairs along the top/bottom straights, and
        ``GND_CAP_P`` / ``GND_CAP_N`` half-ring end caps (ground).
    """
    w_c = center_width / 2.0
    r_rf_in0 = w_c + rf_gap
    r_rf_in1 = r_rf_in0 + rf_width
    r_mid0 = r_rf_in1 + rf_gap
    r_mid1 = r_mid0 + mid_width
    r_rf_out0 = r_mid1 + rf_gap
    r_rf_out1 = r_rf_out0 + rf_width
    r_dc0 = r_rf_out1 + rf_gap
    r_dc1 = r_dc0 + dc_width

    L = half_length
    ds = bend_shift
    BIG = 4 * (L + r_dc1 + abs(ds))

    def band(a, b, da=None, db=None):
        """Concentric band [a, b]: straight boxes + bend sectors.

        On the bends the inner/outer radii are shifted by ``da``/``db``
        (default: both equal ``bend_shift``).
        """
        da = bend_shift if da is None else da
        db = bend_shift if db is None else db
        parts = [box(-L, a, L, b), box(-L, -b, L, -a)]
        for cx in (L, -L):
            disc_out = Point(cx, 0).buffer(b + db, resolution=128)
            disc_in = Point(cx, 0).buffer(max(a + da, 0.1), resolution=128)
            half = box(L, -BIG, BIG, BIG) if cx > 0 else box(-BIG, -BIG, -L, BIG)
            parts.append(disc_out.difference(disc_in).intersection(half))
        return unary_union(parts)

    def half_rings(a, b, da=None, db=None):
        ring = band(a, b, da=da, db=db)
        upper = _largest_polygon(ring.intersection(box(-BIG, 0.0, BIG, BIG)))
        lower = _largest_polygon(ring.intersection(box(-BIG, -BIG, BIG, 0.0)))
        return [_coords(upper), _coords(lower)]

    # Per-band bend deltas: (inner edge, outer edge) for each concentric band
    if bend_profile is not None:
        if len(bend_profile) != 7:
            raise ValueError("bend_profile must have 7 entries")
        p = list(bend_profile)
        d_center = p[0]
        d_inner = (p[1], p[2])
        d_mid = (p[3], p[4])
        d_outer = (p[5], p[6])
        d_cap = (p[6], p[6])  # caps follow the outer RF edge, keeping the gap
    else:
        d_center = ds
        d_inner = (ds - bend_trim, ds + bend_trim)
        d_mid = (ds, ds)
        d_outer = (ds + bend_trim, ds - bend_trim)
        d_cap = (ds, ds)

    # Central ground capsule (bend radius also shifted)
    center = unary_union(
        [box(-L, -w_c, L, w_c)]
        + [
            Point(cx, 0).buffer(w_c + d_center, resolution=128).intersection(
                box(L, -BIG, BIG, BIG) if cx > 0 else box(-BIG, -BIG, -L, BIG)
            )
            for cx in (L, -L)
        ]
    )

    electrodes = [
        Electrode("CENTER", [_coords(center)], kind="ground"),
        Electrode(
            "RF_INNER",
            half_rings(r_rf_in0, r_rf_in1, da=d_inner[0], db=d_inner[1]),
            kind="rf",
        ),
        Electrode("GND_MID", half_rings(r_mid0, r_mid1, da=d_mid[0], db=d_mid[1]), kind="ground"),
        Electrode(
            "RF_OUTER",
            half_rings(r_rf_out0, r_rf_out1, da=d_outer[0], db=d_outer[1]),
            kind="rf",
        ),
    ]

    # Segmented DC rows along the two straights (top: y>0, bottom: y<0)
    span = n_dc_segments * dc_length + (n_dc_segments - 1) * dc_gap
    x0 = -span / 2.0
    for i in range(n_dc_segments):
        xa = x0 + i * (dc_length + dc_gap)
        xb = xa + dc_length
        for tag, (ya, yb) in (("T", (r_dc0, r_dc1)), ("B", (-r_dc1, -r_dc0))):
            electrodes.append(
                Electrode(
                    f"DC_{tag}{i}",
                    [np.array([[xa, ya], [xb, ya], [xb, yb], [xa, yb]])],
                    kind="dc",
                )
            )

    # Ground half-rings covering the curved end caps outside the RF
    cap = band(r_dc0, r_dc1, da=d_cap[0], db=d_cap[1])
    right = _largest_polygon(cap.intersection(box(L, -BIG, BIG, BIG)))
    left = _largest_polygon(cap.intersection(box(-BIG, -BIG, -L, BIG)))
    electrodes.append(Electrode("GND_CAP_P", [_coords(right)], kind="ground"))
    electrodes.append(Electrode("GND_CAP_N", [_coords(left)], kind="ground"))

    meta = dict(
        type="racetrack",
        half_length=half_length,
        center_width=center_width,
        rf_width=rf_width,
        rf_gap=rf_gap,
        mid_width=mid_width,
        dc_width=dc_width,
        dc_gap=dc_gap,
        dc_length=dc_length,
        n_dc_segments=n_dc_segments,
        bend_shift=bend_shift,
        bend_trim=bend_trim,
        bend_profile=list(bend_profile) if bend_profile is not None else None,
        corridor_radius=0.5 * (r_mid0 + r_mid1),
        units="um",
    )
    return ElectrodeSet(electrodes=electrodes, meta=meta)
