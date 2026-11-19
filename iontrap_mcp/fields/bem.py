"""First-kind boundary-element electrostatics solver for planar electrodes.

Physics model
-------------
All electrodes live in the ``z = 0`` plane; the ion moves in the ``z > 0``
half-space.  Each electrode is discretised into small planar panels
(:func:`discretize`).  Every panel ``j`` carries a *reduced charge*
``lambda_j`` (units ``V * um``) such that the electrostatic potential is

.. math::

    \\phi(\\mathbf r) = \\sum_j \\frac{\\lambda_j}{4\\pi\\,|\\mathbf r - \\mathbf r_j|}

with all positions in micrometres.  The physical panel charge is recovered as
``Q_j = eps0 * 1e-6 * lambda_j`` (coulombs), because
``1/(4 pi eps0 r_m) = 1e-6 / (4 pi r_um)``; equivalently ``lambda_j`` is the
charge in units where ``4 pi eps0 = 1`` and lengths are in micrometres.

The interaction matrix is assembled in micrometre units as

.. math::

    G_{ij} = \\frac{1}{4\\pi\\,|\\mathbf r_i - \\mathbf r_j|}
    \\quad (i \\neq j), \\qquad
    G_{ii} = \\frac{1}{2\\sqrt{\\pi\\, a_i}}

where the self term is the exact average-self-potential of a uniformly charged
disc of area ``a_i`` (standard replacement for the square-panel self term).

Unit conventions
----------------
* geometry / panel centroids: micrometres (um), ``z = 0`` plane
* voltages: volts (V)
* ``potential``: volts (V)
* ``field``: volts per metre (V/m, SI)
* ``solve`` / ``panel_charges``: reduced charges ``lambda`` in ``V * um``
* ``capacitance_matrix``: farads (F)

The single conversion constant :data:`UM_TO_M` collects the um -> m factor;
:mod:`iontrap_mcp.fields.trap` handles SI conversions for dynamics.
"""

from __future__ import annotations

import numpy as np
import scipy.linalg
from shapely.geometry import box, Polygon
from shapely.ops import unary_union

from ..common import Electrode

# ---------------------------------------------------------------------------
# Module-level unit constants (the only place um <-> SI conversion happens).
# ---------------------------------------------------------------------------
UM_TO_M = 1e-6  # micrometre -> metre
EPS0 = 8.8541878128e-12  # vacuum permittivity, F/m
FOUR_PI = 4.0 * np.pi


# ---------------------------------------------------------------------------
# Panel discretisation
# ---------------------------------------------------------------------------
def discretize(
    electrode: Electrode, max_panel_size: float = 10.0
) -> tuple[np.ndarray, np.ndarray]:
    """Split an electrode into small rectangular panels with a box grid.

    A regular grid of boxes of side ``<= max_panel_size`` covering the
    electrode's bounding box is intersected (via shapely) with the electrode
    polygons.  Each non-empty intersection contributes one panel located at
    its centroid with its true (possibly partial) area.

    Parameters
    ----------
    electrode:
        :class:`~iontrap_mcp.common.Electrode` with polygons in um.
    max_panel_size:
        Maximum panel edge length in um.  The grid uses
        ``ceil(extent / max_panel_size)`` cells per axis, so panels adapt to
        the electrode area: a 100 x 100 um electrode with the default yields
        ~100 panels.

    Returns
    -------
    centroids:
        ``(M, 3)`` array of panel centroids in um with ``z = 0``.
    areas:
        ``(M,)`` array of panel areas in um^2.
    """
    polys = []
    for p in electrode.polygons:
        poly = Polygon(p)
        if not poly.is_valid:
            poly = poly.buffer(0)
        if not poly.is_empty:
            polys.append(poly)
    if not polys:
        return np.empty((0, 3)), np.empty(0)
    geom = unary_union(polys)

    minx, miny, maxx, maxy = geom.bounds
    nx = max(1, int(np.ceil((maxx - minx) / max_panel_size)))
    ny = max(1, int(np.ceil((maxy - miny) / max_panel_size)))
    dx = (maxx - minx) / nx
    dy = (maxy - miny) / ny

    centroids: list[tuple[float, float, float]] = []
    areas: list[float] = []
    for i in range(nx):
        x0 = minx + i * dx
        for j in range(ny):
            y0 = miny + j * dy
            cell = geom.intersection(box(x0, y0, x0 + dx, y0 + dy))
            if cell.is_empty:
                continue
            a = cell.area
            if a <= 1e-12:
                continue
            c = cell.centroid
            centroids.append((c.x, c.y, 0.0))
            areas.append(a)
    return np.asarray(centroids, dtype=float), np.asarray(areas, dtype=float)


# ---------------------------------------------------------------------------
# Low-level evaluation helpers (operate on reduced charges, um units)
# ---------------------------------------------------------------------------
def _potential_eval(
    points: np.ndarray, centroids: np.ndarray, lam: np.ndarray, chunk: int = 512
) -> np.ndarray:
    """phi [V] at ``points`` [um] from reduced charges ``lam`` [V*um]."""
    out = np.empty(len(points))
    for s in range(0, len(points), chunk):
        p = points[s : s + chunk]
        d = p[:, None, :] - centroids[None, :, :]
        r = np.maximum(np.linalg.norm(d, axis=-1), 1e-12)
        out[s : s + len(p)] = (lam[None, :] / (FOUR_PI * r)).sum(axis=-1)
    return out


def _field_eval(
    points: np.ndarray, centroids: np.ndarray, lam: np.ndarray, chunk: int = 512
) -> np.ndarray:
    """E = -grad phi [V/m, SI] at ``points`` [um]."""
    out = np.empty((len(points), 3))
    for s in range(0, len(points), chunk):
        p = points[s : s + chunk]
        d = p[:, None, :] - centroids[None, :, :]  # um
        r = np.maximum(np.linalg.norm(d, axis=-1), 1e-12)
        # d phi / d r [V/um] = -sum lam (r - r_j) / (4 pi |r - r_j|^3)
        e_um = (lam[None, :, None] * d / (FOUR_PI * r[..., None] ** 3)).sum(axis=1)
        out[s : s + len(p)] = e_um / UM_TO_M  # V/um -> V/m
    return out


# ---------------------------------------------------------------------------
# BEM solver
# ---------------------------------------------------------------------------
class BEMSolver:
    """First-kind BEM solver over a set of planar electrodes.

    All electrodes are discretised once; the dense interaction matrix is
    LU-factorised once (:func:`scipy.linalg.lu_factor`), so repeated
    :meth:`solve` calls with different voltage sets only cost a back-substitution.

    Parameters
    ----------
    electrodes:
        List of :class:`~iontrap_mcp.common.Electrode` (z = 0 plane, um).
    max_panel_size:
        Panel edge target in um, see :func:`discretize`.

    Attributes
    ----------
    centroids:
        ``(M, 3)`` panel centroids [um].
    areas:
        ``(M,)`` panel areas [um^2].
    panel_electrode:
        ``(M,)`` int array: index into ``self.names`` owning each panel.
    names:
        Electrode names in assembly order.
    """

    def __init__(self, electrodes: list[Electrode], max_panel_size: float = 10.0):
        self.max_panel_size = float(max_panel_size)
        self.names: list[str] = []
        self.kinds: dict[str, str] = {}
        cents, areas, owner = [], [], []
        for k, el in enumerate(electrodes):
            c, a = discretize(el, self.max_panel_size)
            if len(c) == 0:
                continue
            self.names.append(el.name)
            self.kinds[el.name] = el.kind
            idx = len(self.names) - 1
            cents.append(c)
            areas.append(a)
            owner.append(np.full(len(c), idx, dtype=int))
        if not cents:
            raise ValueError("no panels: electrodes are empty")
        self.centroids = np.vstack(cents)
        self.areas = np.concatenate(areas)
        self.panel_electrode = np.concatenate(owner)
        self.n_panels = len(self.areas)
        self.n_electrodes = len(self.names)
        self._name_to_idx = {n: i for i, n in enumerate(self.names)}

        # ---- assemble interaction matrix G (1/um), chunked over rows ----
        n = self.n_panels
        G = np.empty((n, n))
        chunk = max(1, int(2e7 // max(n, 1)))  # keep distance blocks ~160 MB
        for s in range(0, n, chunk):
            c = self.centroids[s : s + chunk]
            d = c[:, None, :] - self.centroids[None, :, :]
            r = np.linalg.norm(d, axis=-1)
            G[s : s + chunk] = 1.0 / (FOUR_PI * np.maximum(r, 1e-12))
        # self terms: uniformly charged disc of equal area
        G[np.diag_indices_from(G)] = 1.0 / (2.0 * np.sqrt(np.pi * self.areas))
        self._G = G
        self._lu = scipy.linalg.lu_factor(G)

        # small cache: voltages-tuple -> reduced charges
        self._lam_cache: dict[tuple, np.ndarray] = {}

    # ------------------------------------------------------------- solving
    def _voltage_vector(self, voltages: dict[str, float]) -> np.ndarray:
        """Per-panel RHS [V]; electrodes missing from ``voltages`` are 0 V."""
        v = np.zeros(self.n_panels)
        for name, val in voltages.items():
            if name not in self._name_to_idx:
                raise KeyError(f"unknown electrode {name!r}; have {self.names}")
            v[self.panel_electrode == self._name_to_idx[name]] = float(val)
        return v

    def solve(self, voltages: dict[str, float]) -> np.ndarray:
        """Reduced panel charges ``lambda`` [V*um] for the given voltages.

        Because every panel of an electrode shares the same imposed potential,
        the RHS is simply the per-panel voltage vector; panels of electrodes
        not present in ``voltages`` are held at 0 V (ground).  Results are
        cached, so repeated calls with the same voltages are free.
        """
        key = tuple(sorted((k, float(v)) for k, v in voltages.items()))
        lam = self._lam_cache.get(key)
        if lam is None:
            lam = scipy.linalg.lu_solve(self._lu, self._voltage_vector(voltages))
            if len(self._lam_cache) > 64:
                self._lam_cache.clear()
            self._lam_cache[key] = lam
        return lam

    #: Alias for :meth:`solve` (reduced charges, V*um).
    panel_charges = solve

    # ---------------------------------------------------------- evaluation
    @staticmethod
    def _as_points(points) -> np.ndarray:
        pts = np.asarray(points, dtype=float)
        if pts.ndim == 1:
            pts = pts.reshape(1, 3)
        if pts.shape[1] != 3:
            raise ValueError("points must have shape (N, 3)")
        return pts

    def potential(self, points, voltages: dict[str, float]) -> np.ndarray:
        """Electrostatic potential [V] at ``points`` (N, 3) [um]."""
        pts = self._as_points(points)
        return _potential_eval(pts, self.centroids, self.solve(voltages))

    def field(self, points, voltages: dict[str, float]) -> np.ndarray:
        """Electric field E = -grad phi [V/m, SI] at ``points`` (N, 3) [um]."""
        pts = self._as_points(points)
        return _field_eval(pts, self.centroids, self.solve(voltages))

    # ---------------------------------------------------------- capacitance
    def capacitance_matrix(self) -> dict[str, dict[str, float]]:
        """Maxwell capacitance matrix [F] as a nested dict ``C[row][col]``.

        Column ``k`` is obtained by setting electrode ``k`` to 1 V and all
        others to 0 V; entry ``C[l][k]`` is the resulting total physical
        charge on electrode ``l`` (``Q = eps0 * 1e-6 * sum(lambda_l)``).
        """
        C: dict[str, dict[str, float]] = {
            l: {} for l in self.names
        }
        for k, name_k in enumerate(self.names):
            lam = self.solve({name_k: 1.0})
            for l, name_l in enumerate(self.names):
                q = EPS0 * UM_TO_M * lam[self.panel_electrode == l].sum()
                C[name_l][name_k] = float(q)
        return C
