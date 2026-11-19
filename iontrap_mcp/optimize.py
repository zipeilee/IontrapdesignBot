"""Generic trap-geometry optimization: close the generate → evaluate → improve loop.

The optimizer wraps any electrode generator (``five_wire``, ``x_junction``,
``racetrack``, or a user-supplied callable) with a Nelder-Mead loop.  Each
evaluation rebuilds the geometry, runs a BEM solve, and scores the result
against a list of *objectives* plus hard geometric constraints.

Objective specs (plain dicts, JSON-serialisable so they work over MCP)::

    {"type": "null_height",                      # hit a target ion height
     "region": {"x_range": [a, b], "y_range": [c, d], "z_guess": 30},
     "target": 30.0, "weight": 10.0}

    {"type": "null_uniform",                     # same null across regions
     "regions": [{"x_range": [...], "y_range": [...], "z_guess": 30,
                  "nominal": [x, y]}, ...],      # optional in-plane anchor
     "weight": 10.0}

    {"type": "bump",                             # pseudopotential along a path
     "path": [[x, y], ...],
     "z": 30.0,              # fixed height, or
     "z_from": 0,            # reuse null z of objective #0
     "weight": 1.0}

Constraints: ``min_gap`` applies an electrode-level spacing penalty
(µm of violation × big), mirroring :func:`server.drc_check`.

Cost scaling: null penalties are in µm² (×weight), bump in meV (×weight);
choose weights accordingly.  Example: the racetrack bend flattening in
``examples/`` uses null_uniformity (weight 10) + bump (weight 1).
"""

from __future__ import annotations

import time

import numpy as np
import scipy.optimize
from shapely.geometry import Polygon
from shapely.ops import unary_union

from .fields import BEMSolver, TrapAnalyzer

__all__ = ["optimize_geometry"]


def _min_electrode_gap(es) -> float:
    shapes = {
        e.name: unary_union([Polygon(p) for p in e.polygons]) for e in es.electrodes
    }
    names = sorted(shapes)
    best = np.inf
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            best = min(best, shapes[a].distance(shapes[b]))
    return float(best)


def optimize_geometry(
    builder,
    param_names: list[str],
    p0: list[float],
    objectives: list[dict],
    *,
    min_gap: float | None = None,
    panel_size: float = 8.0,
    ion_mass_amu: float = 171.0,
    rf_frequency_mhz: float = 30.0,
    rf_voltage: float = 100.0,
    max_evals: int = 300,
    xatol: float = 0.05,
    fatol: float = 0.05,
    simplex_step: float = 0.75,
) -> dict:
    """Optimize generator parameters against field objectives.

    Parameters
    ----------
    builder:
        Callable ``builder(**{name: value}) -> ElectrodeSet``.
    param_names, p0:
        Names and initial values of the free parameters (same order).
    objectives:
        List of objective specs (see module docstring).
    min_gap:
        Hard minimum electrode spacing (µm); violations add a large penalty.
    panel_size:
        BEM panel size (µm).  Must be ≤ the smallest electrode gap.
    ion_mass_amu, rf_frequency_mhz, rf_voltage:
        Physics working point for the pseudopotential.
    max_evals, xatol, fatol, simplex_step:
        Nelder-Mead controls.

    Returns
    -------
    dict with ``best_params`` (name → value), ``best_metrics``, ``best_cost``,
    ``n_evals``, ``wall_s``, ``success``, ``message``, ``history`` (per-evaluation
    records), and ``electrodes`` (the best ElectrodeSet, for immediate reuse).
    """
    p0 = [float(v) for v in p0]
    n = len(p0)
    history: list[dict] = []

    def evaluate(p) -> tuple[dict | None, float]:
        params = dict(zip(param_names, p))
        rec: dict = {"params": {k: round(float(v), 4) for k, v in params.items()}}
        try:
            es = builder(**params)
            if min_gap is not None:
                gap = _min_electrode_gap(es)
                if gap < min_gap:
                    rec["violation_um"] = round(min_gap - gap, 3)
                    return rec, 1e6 + 1e5 * (min_gap - gap)
            solver = BEMSolver(list(es.electrodes), max_panel_size=panel_size)
            analyzer = TrapAnalyzer(
                solver,
                rf_electrodes=[e.name for e in es.by_kind("rf")],
                dc_electrodes=[e.name for e in es.by_kind("dc")],
                ion_mass_amu=ion_mass_amu,
                rf_frequency_mhz=rf_frequency_mhz,
                rf_voltage=rf_voltage,
            )
            cost = 0.0
            nulls: list[tuple[float, float, float]] = []
            metrics: dict = {}
            for k, obj in enumerate(objectives):
                if obj["type"] == "null_height":
                    r = obj["region"]
                    null = analyzer.find_rf_null(
                        r["z_guess"], tuple(r["x_range"]), tuple(r["y_range"])
                    )
                    nulls.append(null)
                    dz = null[2] - float(obj["target"])
                    cost += obj.get("weight", 1.0) * dz**2
                    metrics[f"obj{k}_null_z"] = round(null[2], 4)
                elif obj["type"] == "null_uniform":
                    zs, dxy = [], []
                    for r in obj["regions"]:
                        null = analyzer.find_rf_null(
                            r["z_guess"], tuple(r["x_range"]), tuple(r["y_range"])
                        )
                        nulls.append(null)
                        zs.append(null[2])
                        if "nominal" in r:
                            dxy.append(
                                float(np.hypot(null[0] - r["nominal"][0],
                                               null[1] - r["nominal"][1]))
                            )
                    spread_z = max(zs) - min(zs)
                    penalty = spread_z**2 + sum(d**2 for d in dxy)
                    cost += obj.get("weight", 1.0) * penalty
                    metrics[f"obj{k}_z_spread"] = round(spread_z, 4)
                    if dxy:
                        metrics[f"obj{k}_max_dxy"] = round(max(dxy), 4)
                elif obj["type"] == "bump":
                    if "z" in obj:
                        z = float(obj["z"])
                    else:
                        z = nulls[int(obj.get("z_from", 0))][2]
                    pts3 = np.array([[x, y, z] for x, y in obj["path"]])
                    psi = analyzer.pseudopotential(pts3) * 1e3  # meV
                    bump = float(psi.max())
                    cost += obj.get("weight", 1.0) * bump
                    metrics[f"obj{k}_bump_mev"] = round(bump, 4)
                else:
                    raise ValueError(f"unknown objective type {obj['type']!r}")
            rec["metrics"] = metrics
            rec["cost"] = round(cost, 4)
            rec["_es"] = es  # stripped before returning
            return rec, cost
        except Exception as exc:  # noqa: BLE001 - optimiser must not die
            rec["error"] = f"{type(exc).__name__}: {exc}"
            rec["cost"] = 1e9
            return rec, 1e9

    def cost(p):
        rec, c = evaluate(p)
        history.append(rec)
        return c

    t0 = time.time()
    simplex = np.array(
        [p0] + [[v + (simplex_step if k == i else 0.0) for k, v in enumerate(p0)]
                for i in range(n)]
    )
    res = scipy.optimize.minimize(
        cost, p0, method="Nelder-Mead",
        options=dict(maxiter=max_evals * 2, maxfev=max_evals,
                     xatol=xatol, fatol=fatol, initial_simplex=simplex),
    )
    best_rec, best_cost = evaluate(res.x)
    history.append(best_rec)
    best_es = (best_rec or {}).pop("_es", None)
    for h in history:
        h.pop("_es", None)
    return {
        "best_params": (best_rec or {}).get("params", {}),
        "best_metrics": (best_rec or {}).get("metrics", {}),
        "best_cost": float(best_cost),
        "n_evals": len(history),
        "wall_s": round(time.time() - t0, 1),
        "success": bool(res.success),
        "message": str(res.message),
        "history": history,
        "electrodes": best_es,
    }
