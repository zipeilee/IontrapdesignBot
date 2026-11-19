"""Trap characterisation: RF null, pseudopotential, secular frequencies.

Unit conventions
----------------
* positions: um (``z`` above the electrode plane)
* RF field: computed via :class:`~iontrap_mcp.fields.bem.BEMSolver` in V/m
* pseudopotential: eV (for a singly charged ion)
* secular frequencies: MHz
* trap depth: eV

The pseudopotential for a singly charged ion of charge ``Q`` and mass ``m``
driven at angular frequency ``Omega`` with RF field amplitude ``E_rf`` is

.. math::

    \\Psi = \\frac{Q^2 |E_{rf}|^2}{4 m \\Omega^2}

evaluated here with the peak RF voltage ``rf_voltage`` applied to every RF
electrode.  Optionally the DC contribution ``Q * phi_dc`` is added.
"""

from __future__ import annotations

import numpy as np
import scipy.optimize

from .bem import BEMSolver, _field_eval, _potential_eval, UM_TO_M

QE = 1.602176634e-19  # elementary charge, C
AMU = 1.66053906660e-27  # atomic mass unit, kg


class TrapAnalyzer:
    """Characterise a surface Paul trap solved by a :class:`BEMSolver`.

    Parameters
    ----------
    solver:
        Assembled :class:`~iontrap_mcp.fields.bem.BEMSolver`.
    rf_electrodes:
        Names of the electrodes driven with the RF voltage.
    dc_electrodes:
        Names of the DC (control) electrodes.
    ion_mass_amu:
        Ion mass in atomic mass units; default 171 (Yb-171+).
    rf_frequency_mhz:
        RF drive frequency in MHz.
    rf_voltage:
        Peak RF voltage in V applied to each RF electrode.
    """

    def __init__(
        self,
        solver: BEMSolver,
        rf_electrodes: list[str],
        dc_electrodes: list[str],
        ion_mass_amu: float = 171.0,
        rf_frequency_mhz: float = 30.0,
        rf_voltage: float = 100.0,
    ):
        self.solver = solver
        self.rf_electrodes = list(rf_electrodes)
        self.dc_electrodes = list(dc_electrodes)
        self.ion_mass_amu = float(ion_mass_amu)
        self.ion_mass_kg = self.ion_mass_amu * AMU
        self.rf_frequency_mhz = float(rf_frequency_mhz)
        self.omega = 2.0 * np.pi * self.rf_frequency_mhz * 1e6  # rad/s
        self.rf_voltage = float(rf_voltage)
        for n in self.rf_electrodes + self.dc_electrodes:
            if n not in solver.names:
                raise KeyError(f"electrode {n!r} not in solver {solver.names}")
        # reduced charges for 1 V on all RF electrodes (null position is
        # independent of amplitude) and for the actual RF amplitude
        self._lam_rf_unit = solver.solve({n: 1.0 for n in self.rf_electrodes})
        self._lam_rf = solver.solve({n: self.rf_voltage for n in self.rf_electrodes})

    # ------------------------------------------------------------- RF field
    def _rf_field_unit(self, points: np.ndarray) -> np.ndarray:
        """RF field [V/m] for 1 V on the RF electrodes."""
        return _field_eval(np.atleast_2d(points), self.solver.centroids, self._lam_rf_unit)

    def _rf_field(self, points: np.ndarray) -> np.ndarray:
        """RF field amplitude [V/m] at the actual RF voltage."""
        return _field_eval(np.atleast_2d(points), self.solver.centroids, self._lam_rf)

    # -------------------------------------------------------------- RF null
    def find_rf_null(
        self,
        z_guess: float,
        x_range: tuple[float, float] = (-50.0, 50.0),
        y_range: tuple[float, float] = (-50.0, 50.0),
    ) -> tuple[float, float, float]:
        """Locate the RF field null (minimum of ``|E_rf|^2``).

        A coarse 3D grid scan (x over ``x_range``, y over ``y_range``, z on a
        geometric ladder around ``z_guess``) seeds a Nelder-Mead refinement in
        full 3D.  Uses 1 V RF amplitude; the null position is
        amplitude-independent.

        Parameters
        ----------
        z_guess:
            Rough ion height [um].
        x_range, y_range:
            Search windows [um].

        Returns
        -------
        (x0, y0, z0):
            Null position [um] above the electrode plane.
        """
        xs = np.linspace(*x_range, 15)
        ys = np.linspace(*y_range, 7)
        zs = z_guess * np.geomspace(0.3, 3.0, 7)
        gx, gy, gz = np.meshgrid(xs, ys, zs, indexing="ij")
        pts = np.column_stack([gx.ravel(), gy.ravel(), gz.ravel()])
        e2 = (self._rf_field_unit(pts) ** 2).sum(axis=1)
        best = pts[int(np.argmin(e2))]

        def cost(r):
            if r[2] <= 0.1:  # stay above the electrode plane
                return 1e30 + 1e30 * (0.1 - r[2])
            return float((self._rf_field_unit(r) ** 2).sum())

        res = scipy.optimize.minimize(
            cost,
            best,
            method="Nelder-Mead",
            options=dict(xatol=1e-5, fatol=1e-12, maxiter=4000, maxfev=8000),
        )
        x0, y0, z0 = (float(v) for v in res.x)
        return x0, y0, z0

    # -------------------------------------------------------- pseudopotential
    def pseudopotential(
        self, points, include_dc: dict[str, float] | None = None
    ) -> np.ndarray:
        """Pseudopotential [eV] at ``points`` (N, 3) [um].

        ``Psi = Q^2 |E_rf|^2 / (4 m Omega^2)`` with the configured RF voltage.
        If ``include_dc`` is given (DC voltages in V), the electrostatic
        energy ``Q * phi_dc`` is added (numerically ``+phi_dc`` in eV for a
        singly charged ion).
        """
        pts = np.atleast_2d(np.asarray(points, dtype=float))
        E = self._rf_field(pts)  # V/m
        e2 = (E**2).sum(axis=1)
        psi_j = QE**2 * e2 / (4.0 * self.ion_mass_kg * self.omega**2)
        psi_ev = psi_j / QE
        if include_dc:
            phi_dc = _potential_eval(
                pts, self.solver.centroids, self.solver.solve(include_dc)
            )
            psi_ev = psi_ev + phi_dc
        return psi_ev

    # ---------------------------------------------------------- characterize
    def characterize(
        self,
        dc_voltages: dict[str, float] | None = None,
        height: float | None = None,
        x_range: tuple[float, float] | None = None,
        y_range: tuple[float, float] | None = None,
    ) -> dict:
        """Find the trap minimum and summarise its properties.

        Parameters
        ----------
        dc_voltages:
            DC voltage set [V]; electrodes not listed default to 0 V.
        height:
            Guess for the ion height [um]; defaults to a geometry-derived
            value (mean RF-electrode width-scale).
        x_range, y_range:
            Optional RF-null search windows [um]; default derived from the RF
            electrodes' bounding box (x: full RF span, y: central third).

        Returns
        -------
        dict with keys
            ``position``            (x, y, z) of the total-potential minimum [um]
            ``rf_null_height_um``   z of the RF null [um]
            ``trap_depth_ev``       lowest escape barrier along +-x/+-y/+z [eV]
            ``secular_frequencies_mhz``  (f1, f2, f3) sorted ascending [MHz]
            ``potential_min_ev``    total potential energy at the minimum [eV]
        """
        dc = dict(dc_voltages or {})
        if height is None:
            height = self._default_height()
        if x_range is None or y_range is None:
            xr, yr = self._default_ranges()
            x_range = x_range or xr
            y_range = y_range or yr

        null = self.find_rf_null(height, x_range, y_range)

        # Keep the search in the physically sensible slab above the chip.
        z_lo, z_hi = 0.5, 20.0 * max(height, null[2])
        x_lo, x_hi = min(x_range) - 50.0, max(x_range) + 50.0
        y_lo, y_hi = min(y_range) - 50.0, max(y_range) + 50.0

        def U_ev(r):
            x, y, z = r
            if not (np.isfinite(r).all()):
                return 1e30
            if z < z_lo or z > z_hi or x < x_lo or x > x_hi or y < y_lo or y > y_hi:
                return 1e20
            return float(self.pseudopotential(np.asarray(r, float), include_dc=dc)[0])

        res = scipy.optimize.minimize(
            U_ev,
            np.array(null),
            method="Nelder-Mead",
            options=dict(xatol=1e-5, fatol=1e-12, maxiter=4000, maxfev=8000),
        )
        r_min = res.x
        if not np.isfinite(U_ev(r_min)) or U_ev(r_min) >= 1e20:
            raise RuntimeError(
                f"trap minimum search failed (best={r_min}); "
                "check geometry or pass an explicit height"
            )
        u_min = U_ev(r_min)

        # --- Hessian by central differences (h = 0.1 um) -> spring constants
        h = 0.1  # um
        H = np.empty((3, 3))
        for i in range(3):
            ei = np.zeros(3)
            ei[i] = h
            fp, fm = U_ev(r_min + ei), U_ev(r_min - ei)
            H[i, i] = (fp - 2.0 * u_min + fm) / h**2
            for j in range(i + 1, 3):
                ej = np.zeros(3)
                ej[j] = h
                fpp = U_ev(r_min + ei + ej)
                fpm = U_ev(r_min + ei - ej)
                fmp = U_ev(r_min - ei + ej)
                fmm = U_ev(r_min - ei - ej)
                H[i, j] = H[j, i] = (fpp - fpm - fmp + fmm) / (4.0 * h**2)
        H = 0.5 * (H + H.T)
        k_ev = np.linalg.eigvalsh(H)  # eV/um^2
        k_si = k_ev * QE / UM_TO_M**2  # J/m^2
        omega_i = np.sqrt(np.maximum(k_si, 0.0) / self.ion_mass_kg)
        freqs_mhz = omega_i / (2.0 * np.pi) / 1e6

        # --- trap depth: lowest saddle along +-x, +-y, +z rays
        depth = self._trap_depth(U_ev, r_min, u_min)

        return {
            "position": tuple(float(v) for v in r_min),
            "rf_null_height_um": float(null[2]),
            "trap_depth_ev": float(depth),
            "secular_frequencies_mhz": tuple(float(f) for f in freqs_mhz),
            "potential_min_ev": float(u_min),
        }

    # ------------------------------------------------------- helper: depth
    @staticmethod
    def _trap_depth(U_ev, r_min: np.ndarray, u_min: float) -> float:
        """Lowest escape barrier [eV] along +-x, +-y, +z rays from the minimum."""
        z0 = float(r_min[2])
        t_max = max(4.0 * z0, 200.0)
        ts = np.linspace(0.02 * z0, t_max, 400)
        depth = np.inf
        for axis, sign in [(0, 1), (0, -1), (1, 1), (1, -1), (2, 1)]:
            d = np.zeros(3)
            d[axis] = sign
            pts = r_min[None, :] + ts[:, None] * d[None, :]
            u = np.array([U_ev(p) for p in pts]) - u_min
            # first local maximum followed by a clear decrease = saddle
            du = np.diff(u)
            candidates = np.where((du[:-1] > 0) & (du[1:] < -1e-9))[0]
            if len(candidates):
                depth_dir = u[candidates[0] + 1]
            else:
                depth_dir = u[-1]
            depth = min(depth, depth_dir)
        return float(max(depth, 0.0))

    # ------------------------------------------------- geometry heuristics
    def _default_height(self) -> float:
        # Ion height scales with the RF rail *width* (the short in-plane
        # dimension), not with the rail length along the trap axis.
        widths = []
        for n in self.rf_electrodes:
            mask = self.solver.panel_electrode == self.solver.names.index(n)
            c = self.solver.centroids[mask]
            spans = [c[:, 0].max() - c[:, 0].min(), c[:, 1].max() - c[:, 1].min()]
            widths.append(min(spans))
        return float(max(float(np.mean(widths)), 10.0))

    def _default_ranges(self):
        xs, ys = [], []
        for n in self.rf_electrodes:
            mask = self.solver.panel_electrode == self.solver.names.index(n)
            c = self.solver.centroids[mask]
            xs.append(c[:, 0])
            ys.append(c[:, 1])
        xs = np.concatenate(xs)
        ys = np.concatenate(ys)
        yspan = ys.max() - ys.min()
        ymid = 0.5 * (ys.max() + ys.min())
        return (float(xs.min()), float(xs.max())), (
            float(ymid - yspan / 6.0),
            float(ymid + yspan / 6.0),
        )

    # -------------------------------------------------- DC Hessian per volt
    def dc_hessian_per_volt(self, point) -> dict[str, np.ndarray]:
        """Hessian of the DC potential per volt at ``point`` [um].

        Returns
        -------
        dict
            ``{dc_name: (3, 3) array}`` with entries
            ``d^2 phi / d r_i d r_j`` in V/um^2 for 1 V on that electrode
            (all others grounded).  Central differences with ``h = 0.1 um``.
            Intended for DC voltage synthesis in
            :mod:`iontrap_mcp.fields.solve`.
        """
        r0 = np.asarray(point, dtype=float)
        h = 0.1  # um
        out: dict[str, np.ndarray] = {}
        for name in self.dc_electrodes:
            lam = self.solver.solve({name: 1.0})

            def phi(r):
                return float(
                    _potential_eval(
                        np.atleast_2d(r), self.solver.centroids, lam
                    )[0]
                )

            f0 = phi(r0)
            H = np.empty((3, 3))
            for i in range(3):
                ei = np.zeros(3)
                ei[i] = h
                H[i, i] = (phi(r0 + ei) - 2.0 * f0 + phi(r0 - ei)) / h**2
                for j in range(i + 1, 3):
                    ej = np.zeros(3)
                    ej[j] = h
                    H[i, j] = H[j, i] = (
                        phi(r0 + ei + ej)
                        - phi(r0 + ei - ej)
                        - phi(r0 - ei + ej)
                        + phi(r0 - ei - ej)
                    ) / (4.0 * h**2)
            out[name] = H
        return out
