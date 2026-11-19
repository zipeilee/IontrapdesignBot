"""Simple fan-out routing from DC electrodes to chip-edge bonding pads.

Each DC electrode gets a tapered (trapezoidal) trace on GDS layer
(5, 0) running from its outer edge to a square bonding pad placed along
the nearest chip edge.  Pads are assigned in position-sorted order so
traces do not cross for convex, mirror-symmetric layouts.
"""

from __future__ import annotations

import numpy as np

from ..common import Electrode, ElectrodeSet

__all__ = ["fanout"]

LAYER_TRACE = (5, 0)
_EDGES = ("left", "right", "top", "bottom")


def fanout(
    es: ElectrodeSet,
    pad_pitch: float = 150.0,
    pad_size: float = 100.0,
    edge: str = "auto",
) -> ElectrodeSet:
    """Route every DC electrode of ``es`` to a bonding pad at the chip edge.

    Parameters
    ----------
    es:
        Input electrode set.  Only electrodes with ``kind == "dc"`` are
        routed; RF and ground electrodes are left untouched.
    pad_pitch:
        Centre-to-centre spacing of bonding pads along one edge (µm).
        Should be >= ``pad_size`` so pads do not overlap.
    pad_size:
        Side length of the square bonding pads (µm).
    edge:
        ``"auto"`` assigns each electrode to the nearest chip edge (in
        bounding-box-normalised coordinates); one of ``"left"``,
        ``"right"``, ``"top"``, ``"bottom"`` forces all pads onto that
        edge.

    Returns
    -------
    ElectrodeSet
        A new ElectrodeSet containing the original electrodes plus, for
        each routed DC electrode ``<name>``, a trapezoidal trace
        ``TRACE_<name>`` and a square pad ``PAD_<name>``.  Traces and
        pads live on GDS layer (5, 0) with kinds ``"trace"`` / ``"pad"``.
        ``meta`` is copied and updated with the routing parameters.

    Notes
    -----
    The "chip edge" is the bounding box of the input geometry expanded
    by ``pad_size + pad_pitch``; pad centres sit on that expanded box.
    Within each edge, electrodes are sorted by their coordinate along
    the edge and pads are assigned in the same order, which avoids
    trace crossings for typical symmetric trap layouts.  Traces are on
    a dedicated routing layer and may pass over electrodes on other
    layers.
    """
    if edge != "auto" and edge not in _EDGES:
        raise ValueError(f"edge must be 'auto' or one of {_EDGES}")
    if pad_pitch <= 0 or pad_size <= 0:
        raise ValueError("pad_pitch and pad_size must be positive")

    dc_electrodes = es.by_kind("dc")
    if not dc_electrodes:
        return ElectrodeSet(electrodes=list(es.electrodes), meta=dict(es.meta))

    all_pts = np.vstack([p for e in es.electrodes for p in e.polygons])
    xmin, ymin = all_pts.min(axis=0)
    xmax, ymax = all_pts.max(axis=0)
    cx_box, cy_box = (xmin + xmax) / 2.0, (ymin + ymax) / 2.0
    half_w = max((xmax - xmin) / 2.0, 1e-9)
    half_h = max((ymax - ymin) / 2.0, 1e-9)
    offset = pad_size + pad_pitch  # bbox edge -> pad centre distance

    def bbox_of(e: Electrode) -> tuple[float, float, float, float]:
        pts = np.vstack(e.polygons)
        lo = pts.min(axis=0)
        hi = pts.max(axis=0)
        return lo[0], lo[1], hi[0], hi[1]

    def auto_edge(c: np.ndarray) -> str:
        nx = abs(c[0] - cx_box) / half_w
        ny = abs(c[1] - cy_box) / half_h
        if ny >= nx:
            return "top" if c[1] >= cy_box else "bottom"
        return "right" if c[0] >= cx_box else "left"

    # Assign electrodes to edges.
    groups: dict[str, list[tuple[Electrode, np.ndarray]]] = {e: [] for e in _EDGES}
    for e in dc_electrodes:
        c = np.vstack(e.polygons).mean(axis=0)
        groups[edge if edge != "auto" else auto_edge(c)].append((e, c))

    new_electrodes: list[Electrode] = list(es.electrodes)

    for edge_name, members in groups.items():
        if not members:
            continue
        # Sort along the edge; pads are assigned in the same order so
        # that traces do not cross.
        axis = 0 if edge_name in ("top", "bottom") else 1
        members.sort(key=lambda m: m[1][axis])
        n = len(members)
        for i, (e, c) in enumerate(members):
            along = (cx_box if axis == 0 else cy_box) + (i - (n - 1) / 2.0) * pad_pitch
            if edge_name == "top":
                pad_c = np.array([along, ymax + offset])
            elif edge_name == "bottom":
                pad_c = np.array([along, ymin - offset])
            elif edge_name == "right":
                pad_c = np.array([xmax + offset, along])
            else:  # left
                pad_c = np.array([xmin - offset, along])

            # Trace: trapezoid from the electrode bbox boundary toward
            # the pad inner edge.
            d = pad_c - c
            norm = np.hypot(*d)
            if norm < 1e-12:
                continue
            d = d / norm
            ex0, ey0, ex1, ey1 = bbox_of(e)
            t_exit = np.inf
            if d[0] > 1e-12:
                t_exit = min(t_exit, (ex1 - c[0]) / d[0])
            elif d[0] < -1e-12:
                t_exit = min(t_exit, (ex0 - c[0]) / d[0])
            if d[1] > 1e-12:
                t_exit = min(t_exit, (ey1 - c[1]) / d[1])
            elif d[1] < -1e-12:
                t_exit = min(t_exit, (ey0 - c[1]) / d[1])
            if not np.isfinite(t_exit) or t_exit < 0:
                t_exit = 0.0
            start = c + d * t_exit
            end = pad_c - d * (pad_size / 2.0)

            perp = np.array([-d[1], d[0]])
            w0 = min(0.4 * pad_size, 0.5 * min(ex1 - ex0, ey1 - ey0))
            w0 = max(w0, 1.0)
            w1 = 0.8 * pad_size
            trace = np.array(
                [
                    start + perp * (w0 / 2.0),
                    end + perp * (w1 / 2.0),
                    end - perp * (w1 / 2.0),
                    start - perp * (w0 / 2.0),
                ]
            )
            new_electrodes.append(
                Electrode(
                    name=f"TRACE_{e.name}",
                    polygons=[trace],
                    kind="trace",
                    layer=LAYER_TRACE,
                )
            )

            hp = pad_size / 2.0
            pad = np.array(
                [
                    [pad_c[0] - hp, pad_c[1] - hp],
                    [pad_c[0] + hp, pad_c[1] - hp],
                    [pad_c[0] + hp, pad_c[1] + hp],
                    [pad_c[0] - hp, pad_c[1] + hp],
                ]
            )
            new_electrodes.append(
                Electrode(
                    name=f"PAD_{e.name}",
                    polygons=[pad],
                    kind="pad",
                    layer=LAYER_TRACE,
                )
            )

    meta = dict(es.meta)
    meta["routing"] = dict(
        pad_pitch=pad_pitch, pad_size=pad_size, edge=edge, layer=LAYER_TRACE
    )
    return ElectrodeSet(electrodes=new_electrodes, meta=meta)
