"""Bend cross-section free optimization: 7 DOF, Nelder-Mead on BEM cost."""

import json
import sys
import time
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import numpy as np
import scipy.optimize
from racetrack import racetrack
from iontrap_mcp.fields import BEMSolver, TrapAnalyzer

L, R = 400.0, 76.0
BASE = [20.0, 28.0, 58.0, 66.0, 86.0, 94.0, 124.0]  # 直道各边界半径
LOG = pathlib.Path(__file__).parent / "bend_opt_log.jsonl"


def evaluate(p, panel=8.0):
    p = list(map(float, p))
    # 间隙约束：弯道上相邻边界间距 >= 3.5 µm
    bounds = [b + d for b, d in zip(BASE, p)]
    gaps = np.diff(bounds)
    if gaps.min() < 3.5 or bounds[0] < 5:
        return None, 1e6 + 1e5 * float(np.abs(np.minimum(gaps, 3.5)).sum())
    try:
        es = racetrack(bend_profile=p)
        s = BEMSolver(list(es.electrodes), max_panel_size=panel)
        a = TrapAnalyzer(
            s,
            rf_electrodes=["RF_INNER", "RF_OUTER"],
            dc_electrodes=[e.name for e in es.by_kind("dc")],
            ion_mass_amu=171.0,
            rf_frequency_mhz=42.0,
            rf_voltage=200.0,
        )
        ns = a.find_rf_null(30.0, (-100, 100), (61, 91))
        nb = a.find_rf_null(ns[2], (L + 55, L + 105), (-15, 15))
        rb = float(np.hypot(nb[0] - L, nb[1]))
        th = np.linspace(np.pi / 2, -np.pi / 2, 61)
        pts = np.column_stack(
            [L + rb * np.cos(th), rb * np.sin(th), np.full_like(th, ns[2])]
        )
        psi = a.pseudopotential(pts) * 1e3
        bump = float(psi.max())
        dz = nb[2] - ns[2]
        dr = rb - R
        cost = bump + 10 * abs(dz) + 5 * abs(dr)
        rec = dict(p=[round(v, 2) for v in p], bump=round(bump, 3),
                   dz=round(dz, 3), dr=round(dr, 3), cost=round(cost, 3))
        return rec, cost
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}, 1e9


def main():
    p0 = [3.0, 6.5, -0.5, 3.0, 3.0, -0.5, 6.5]  # = bend_shift 3, trim -3.5
    simplex = [p0] + [
        [v + (0.75 if k == i else 0.0) for k, v in enumerate(p0)]
        for i in range(7)
    ]
    history = []

    def cost(p):
        rec, c = evaluate(p)
        history.append(rec)
        with LOG.open("a") as f:
            f.write(json.dumps(rec) + "\n")
        print(len(history), rec, flush=True)
        return c

    t0 = time.time()
    res = scipy.optimize.minimize(
        cost,
        p0,
        method="Nelder-Mead",
        options=dict(
            maxiter=300,
            maxfev=400,
            xatol=0.05,
            fatol=0.05,
            initial_simplex=np.array(simplex),
        ),
    )
    rec, c = evaluate(res.x)  # 精确记录最优点
    out = dict(best_p=[round(v, 3) for v in res.x], best=rec,
               n_evals=len(history), wall_s=round(time.time() - t0),
               success=bool(res.success), message=str(res.message))
    print(json.dumps(out, indent=2))
    (pathlib.Path(__file__).parent / "bend_opt_result.json").write_text(
        json.dumps(out, indent=2)
    )


if __name__ == "__main__":
    main()
