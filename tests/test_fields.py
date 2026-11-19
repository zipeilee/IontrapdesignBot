"""Tests for iontrap_mcp.fields (first-kind BEM electrostatics).

Geometries are built directly with :class:`iontrap_mcp.common.Electrode`;
all coordinates in um, voltages in V, fields in V/m.
"""

from __future__ import annotations

import time

import numpy as np
import pytest

from iontrap_mcp.common import Electrode
from iontrap_mcp.fields import (
    BEMSolver,
    TrapAnalyzer,
    discretize,
    shuttle_waveform,
    solve_dc_voltages,
)


# ---------------------------------------------------------------------------
# geometry helpers
# ---------------------------------------------------------------------------
def rect(x0, y0, x1, y1):
    return np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], dtype=float)


def disk(radius, n=128):
    th = np.linspace(0, 2 * np.pi, n, endpoint=False)
    return np.column_stack([radius * np.cos(th), radius * np.sin(th)])


def five_wire_electrodes():
    """Symmetric five-wire surface trap: DC | RF | DC | RF | DC, 600 um long."""
    return [
        Electrode("DC_C", [rect(-7.5, -300, 7.5, 300)], kind="dc"),
        Electrode("RF_L", [rect(-42.5, -300, -12.5, 300)], kind="rf"),
        Electrode("RF_R", [rect(12.5, -300, 42.5, 300)], kind="rf"),
        Electrode("DC_L", [rect(-107.5, -300, -47.5, 300)], kind="dc"),
        Electrode("DC_R", [rect(47.5, -300, 107.5, 300)], kind="dc"),
    ]


@pytest.fixture(scope="module")
def disk_solver():
    return BEMSolver([Electrode("DISK", [disk(100.0)], kind="dc")], max_panel_size=8.0)


@pytest.fixture(scope="module")
def five_wire_solver():
    return BEMSolver(five_wire_electrodes(), max_panel_size=10.0)


@pytest.fixture(scope="module")
def trap_analyzer(five_wire_solver):
    return TrapAnalyzer(
        five_wire_solver,
        rf_electrodes=["RF_L", "RF_R"],
        dc_electrodes=["DC_C", "DC_L", "DC_R"],
        ion_mass_amu=171.0,  # Yb+
        rf_frequency_mhz=30.0,
        rf_voltage=100.0,
    )


# ---------------------------------------------------------------------------
# discretisation
# ---------------------------------------------------------------------------
def test_discretize_panel_count_adapts_to_area():
    el = Electrode("SQ", [rect(0, 0, 100, 100)], kind="dc")
    centroids, areas = discretize(el, max_panel_size=10.0)
    assert centroids.shape == (100, 3)  # ~1 panel per 10x10 um cell
    assert areas.shape == (100,)
    assert np.allclose(areas.sum(), 10000.0)
    assert np.all(centroids[:, 2] == 0.0)
    # finer grid -> more panels
    c2, a2 = discretize(el, max_panel_size=5.0)
    assert len(c2) == 400
    assert np.allclose(a2.sum(), 10000.0)


# ---------------------------------------------------------------------------
# analytic benchmarks
# ---------------------------------------------------------------------------
def test_disk_axis_potential_matches_conducting_disk(disk_solver):
    """On-axis potential of a conducting disk at V: phi = (2V/pi) atan(R/z)."""
    R = 100.0
    for z in (50.0, 100.0, 200.0):
        bem = disk_solver.potential([[0.0, 0.0, z]], {"DISK": 1.0})[0]
        exact = 2.0 / np.pi * np.arctan(R / z)
        assert abs(bem - exact) / exact < 0.10  # spec: 10% tolerance


def test_large_plate_center_potential_vs_strip_formula():
    """200x200 um plate at 1 V; center-axis potential ~ (2/pi) atan(w/z)."""
    solver = BEMSolver(
        [Electrode("PLATE", [rect(-100, -100, 100, 100)], kind="dc")],
        max_panel_size=5.0,
    )
    z = 50.0
    bem = solver.potential([[0.0, 0.0, z]], {"PLATE": 1.0})[0]
    strip = 2.0 / np.pi * np.arctan(100.0 / z)
    assert abs(bem - strip) / strip < 0.10
    # monotonic decay and bounded by the imposed voltage
    seq = solver.potential(
        [[0, 0, 10.0], [0, 0, 50.0], [0, 0, 200.0]], {"PLATE": 1.0}
    )
    assert np.all(seq < 1.0) and seq[0] > seq[1] > seq[2] > 0.0


def test_far_field_coulomb_decay(disk_solver):
    """Far on-axis potential decays as 1/r (and -> 0 at infinity)."""
    p1 = disk_solver.potential([[0, 0, 1000.0]], {"DISK": 1.0})[0]
    p2 = disk_solver.potential([[0, 0, 2000.0]], {"DISK": 1.0})[0]
    assert abs(p1 / p2 - 2.0) / 2.0 < 0.02
    p_far = disk_solver.potential([[0, 0, 1e5]], {"DISK": 1.0})[0]
    assert p_far < 0.01  # decays to zero


def test_disk_capacitance(disk_solver):
    """Isolated-disk capacitance C = 8 eps0 R."""
    C = disk_solver.capacitance_matrix()["DISK"]["DISK"]
    exact = 8.0 * 8.8541878128e-12 * 100e-6
    assert abs(C - exact) / exact < 0.05


# ---------------------------------------------------------------------------
# five-wire symmetry / trap characterisation
# ---------------------------------------------------------------------------
def test_five_wire_rf_null_symmetry(trap_analyzer):
    x0, y0, z0 = trap_analyzer.find_rf_null(50.0, (-30.0, 30.0), (-30.0, 30.0))
    assert abs(x0) < 0.5  # mirror symmetry in x
    assert abs(y0) < 1.0  # translation symmetry (long electrodes)
    assert 5.0 < z0 < 100.0  # above the electrode plane


def test_characterize_reasonable_values(trap_analyzer):
    ch = trap_analyzer.characterize(dc_voltages=None, height=50.0)
    x, y, z = ch["position"]
    assert z > 10.0  # minimum above the electrode plane
    assert abs(x) < 1.0 and abs(y) < 5.0
    freqs = ch["secular_frequencies_mhz"]
    assert len(freqs) == 3
    assert all(f > 0.0 for f in freqs)
    assert ch["rf_null_height_um"] == pytest.approx(z, rel=0.05)
    assert ch["trap_depth_ev"] > 0.0


def test_dc_hessian_satisfies_laplace(trap_analyzer):
    """d2phi/dxi2 traces to ~0 in free space (Laplace equation)."""
    H = trap_analyzer.dc_hessian_per_volt((0.0, 0.0, 22.0))
    assert set(H) == {"DC_C", "DC_L", "DC_R"}
    for name, mat in H.items():
        assert mat.shape == (3, 3)
        scale = np.abs(mat).max()
        assert abs(np.trace(mat)) < 0.02 * scale


# ---------------------------------------------------------------------------
# DC voltage synthesis
# ---------------------------------------------------------------------------
def _quad_pads():
    """Four quadrant pads plus a centre pad (5 DC electrodes)."""
    return [
        Electrode("DC0", [rect(-8, -8, 8, 8)], kind="dc"),
        Electrode("DC1", [rect(10, 10, 50, 50)], kind="dc"),
        Electrode("DC2", [rect(-50, 10, -10, 50)], kind="dc"),
        Electrode("DC3", [rect(-50, -50, -10, -10)], kind="dc"),
        Electrode("DC4", [rect(10, -50, 50, -10)], kind="dc"),
    ]


def test_solve_dc_voltages_field_null_and_potential():
    solver = BEMSolver(_quad_pads(), max_panel_size=10.0)
    names = ["DC0", "DC1", "DC2", "DC3", "DC4"]
    pt = (5.0, 3.0, 40.0)  # off-centre: all 3 field components controllable
    volts = solve_dc_voltages(
        solver,
        names,
        [
            {"point": pt, "type": "field_null", "axes": [0, 1, 2]},
            {"point": pt, "type": "potential", "value": 0.2},
        ],
    )
    assert set(volts) == set(names)
    E = solver.field([pt], volts)[0]
    assert np.linalg.norm(E) < 1e-3  # V/m
    phi = solver.potential([pt], volts)[0]
    assert phi == pytest.approx(0.2, rel=1e-3)


def test_solve_dc_voltages_pure_field_null_normalised():
    solver = BEMSolver(_quad_pads(), max_panel_size=10.0)
    names = ["DC0", "DC1", "DC2", "DC3", "DC4"]
    pt = (5.0, 3.0, 40.0)
    volts = solve_dc_voltages(
        solver, names, [{"point": pt, "type": "field_null", "axes": [0, 1, 2]}]
    )
    assert max(abs(v) for v in volts.values()) == pytest.approx(1.0)
    # far better null than an arbitrary unit voltage pattern
    E_sol = np.linalg.norm(solver.field([pt], volts)[0])
    E_ref = np.linalg.norm(solver.field([pt], {n: 1.0 for n in names})[0])
    assert E_sol < 1e-6 * E_ref


def test_shuttle_waveform():
    solver = BEMSolver(_quad_pads(), max_panel_size=10.0)
    names = ["DC0", "DC1", "DC2", "DC3", "DC4"]
    positions = [(0, 0, 40), (5, 0, 40), (10, 0, 40)]
    wf = shuttle_waveform(solver, names, positions, vmax=10.0)
    assert len(wf) == 3
    for step in wf:
        assert set(step) == set(names)
        assert all(abs(v) <= 10.0 + 1e-12 for v in step.values())


# ---------------------------------------------------------------------------
# junction RF null (regression: arms need grounded centre strips)
# ---------------------------------------------------------------------------
def _arm_e_profile(es, zs):
    """|E| (V/m) for 1 V RF, scanned along z above the +x arm midline."""
    solver = BEMSolver(list(es.electrodes), max_panel_size=15.0)
    rf = {e.name: 1.0 for e in es.by_kind("rf")}
    pts = np.column_stack([np.full_like(zs, 250.0), np.zeros_like(zs), zs])
    return np.linalg.norm(solver.field(pts, rf), axis=1)


def test_x_junction_arm_rf_null_requires_center_strip():
    """Without grounded centre strips the two same-potential RF rails act
    as one wide conductor and |E| decays monotonically (no RF null); with
    the strips a clear null appears above each arm."""
    from iontrap_mcp.electrodes import x_junction

    zs = np.linspace(5.0, 60.0, 23)
    with_strip = _arm_e_profile(x_junction(arm_dc_segments=3), zs)
    without_strip = _arm_e_profile(
        x_junction(arm_dc_segments=3, center_strip=False), zs
    )
    # with strips: deep interior null (dip to a small fraction of the max)
    assert with_strip.min() < 0.15 * with_strip.max()
    assert 0 < int(np.argmin(with_strip)) < len(zs) - 1
    # without strips: no null — field stays high and decays monotonically
    assert without_strip.min() > 0.3 * without_strip.max()
    assert int(np.argmin(without_strip)) == len(zs) - 1


# ---------------------------------------------------------------------------
# performance
# ---------------------------------------------------------------------------
def test_performance_solve_and_potential():
    solver = BEMSolver(five_wire_electrodes(), max_panel_size=7.0)
    assert solver.n_panels < 20000
    volts = {"RF_L": 100.0, "RF_R": 100.0, "DC_C": 2.5}

    t0 = time.perf_counter()
    solver.solve(volts)
    assert time.perf_counter() - t0 < 1.0

    rng = np.random.default_rng(0)
    pts = rng.random((1000, 3)) * [200.0, 200.0, 100.0] + [0.0, 0.0, 5.0]
    t0 = time.perf_counter()
    phi = solver.potential(pts, volts)
    assert time.perf_counter() - t0 < 1.0
    assert phi.shape == (1000,)
