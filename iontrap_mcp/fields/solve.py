"""DC voltage synthesis: inverse field/potential problems and shuttling.

Given a :class:`~iontrap_mcp.fields.bem.BEMSolver`, compute the DC electrode
voltages that realise field-null / potential targets at specified ion
positions, and generate voltage waveforms for ion shuttling.

Unit conventions
----------------
* positions: um; voltages: V; fields: V/m (SI)
* linear system rows from ``field_null`` targets use V/m per volt; rows from
  ``potential`` targets use V per volt.
"""

from __future__ import annotations

import numpy as np

from .bem import BEMSolver


def solve_dc_voltages(
    solver: BEMSolver,
    dc_names: list[str],
    targets: list[dict],
    alpha: float = 1e-6,
    null_scale: float = 1.0,
) -> dict[str, float]:
    """Least-squares DC voltages realising a list of targets.

    Parameters
    ----------
    solver:
        Assembled :class:`~iontrap_mcp.fields.bem.BEMSolver`.
    dc_names:
        Names of the DC electrodes to solve for (all others held at 0 V).
    targets:
        Each target is a dict of one of the forms

        * ``{"point": (x, y, z), "type": "field_null", "axes": [0, 1, 2]}``
          — vanishing electrostatic field components at ``point`` [um]
          (``axes`` selects which of Ex, Ey, Ez; default all three);
        * ``{"point": (x, y, z), "type": "potential", "value": V}``
          — electrostatic potential equal to ``value`` [V] at ``point``.
    alpha:
        Ridge (Tikhonov) regularisation parameter.  Constraint rows are
        normalised to unit norm first (so field [V/m] and potential [V]
        rows are weighted comparably), then the solution minimises
        ``||A v - b||^2 + alpha ||v||^2`` on the normalised system.
    null_scale:
        If every target is homogeneous (``b == 0``, e.g. only field-null
        targets), the least-squares solution would be the trivial zero vector.
        In that case the voltage pattern is instead taken from the smallest
        right-singular vector of ``A`` (best achievable null) and rescaled so
        ``max |v| = null_scale`` V.

    Returns
    -------
    dict
        ``{dc_name: voltage [V]}`` for every name in ``dc_names``.
    """
    for n in dc_names:
        if n not in solver.names:
            raise KeyError(f"electrode {n!r} not in solver {solver.names}")

    rows: list[np.ndarray] = []
    rhs: list[float] = []
    # per-electrode unit responses, cached per target point
    field_cache: dict[tuple, np.ndarray] = {}
    pot_cache: dict[tuple, np.ndarray] = {}

    def unit_fields(pt: np.ndarray) -> np.ndarray:
        key = tuple(pt)
        if key not in field_cache:
            field_cache[key] = np.vstack(
                [solver.field(pt, {n: 1.0})[0] for n in dc_names]
            )  # (K, 3), V/m per V
        return field_cache[key]

    def unit_pots(pt: np.ndarray) -> np.ndarray:
        key = tuple(pt)
        if key not in pot_cache:
            pot_cache[key] = np.array(
                [solver.potential(pt, {n: 1.0})[0] for n in dc_names]
            )  # (K,), V per V
        return pot_cache[key]

    for t in targets:
        pt = np.asarray(t["point"], dtype=float)
        ttype = t["type"]
        if ttype == "field_null":
            axes = t.get("axes", [0, 1, 2])
            E = unit_fields(pt)  # (K, 3)
            for ax in axes:
                rows.append(E[:, ax])
                rhs.append(0.0)
        elif ttype == "potential":
            rows.append(unit_pots(pt))
            rhs.append(float(t["value"]))
        else:
            raise ValueError(f"unknown target type {ttype!r}")

    if not rows:
        return {n: 0.0 for n in dc_names}

    A = np.vstack(rows)  # (R, K)
    b = np.asarray(rhs, dtype=float)

    # Row-normalise so that field (V/m) and potential (V) constraints are
    # weighted comparably and the ridge parameter is scale-independent.
    norms = np.linalg.norm(A, axis=1)
    keep = norms > 0.0
    A = A[keep] / norms[keep, None]
    b = b[keep] / norms[keep]

    if np.all(b == 0.0):
        # homogeneous problem: best-null pattern from the SVD.  Use the full
        # Vt so that underdetermined systems yield their exact null vector.
        _, _, vt = np.linalg.svd(A, full_matrices=True)
        v = vt[-1]
        m = np.max(np.abs(v))
        v = v / m * null_scale if m > 0 else v
    else:
        # ridge-regularised least squares on the normalised system, with
        # iterative refinement of the residual (keeps the regularised
        # solution but pushes the constraint residual well below alpha)
        K = len(dc_names)
        ata = A.T @ A + alpha * np.eye(K)
        v = np.linalg.solve(ata, A.T @ b)
        tol = 1e-12 * max(1.0, float(np.linalg.norm(b)))
        for _ in range(3):
            r = b - A @ v
            if float(np.linalg.norm(r)) <= tol:
                break
            v = v + np.linalg.solve(ata, A.T @ r)

    return {n: float(v[i]) for i, n in enumerate(dc_names)}


def shuttle_waveform(
    solver: BEMSolver,
    dc_names: list[str],
    positions: list,
    vmax: float = 10.0,
) -> list[dict[str, float]]:
    """Voltage sets that shuttle an ion through ``positions``.

    For each target position a field-null (all three axes) is requested and
    the resulting best-null voltage pattern is scaled so that the largest
    magnitude equals ``vmax`` (hence all voltages lie in ``[-vmax, vmax]``).

    Parameters
    ----------
    solver:
        Assembled :class:`~iontrap_mcp.fields.bem.BEMSolver`.
    dc_names:
        DC electrodes to solve for.
    positions:
        Iterable of ``(x, y, z)`` ion positions [um].
    vmax:
        Peak voltage [V] used for the normalisation of each step.

    Returns
    -------
    list of dict
        One ``{dc_name: voltage}`` dict per position.
    """
    waveform = []
    for pos in positions:
        volts = solve_dc_voltages(
            solver,
            dc_names,
            [{"point": tuple(pos), "type": "field_null", "axes": [0, 1, 2]}],
            null_scale=vmax,
        )
        waveform.append(volts)
    return waveform
