"""IonTrapClaw MCP server.

Standalone MCP server (no KLayout GUI required) exposing ion-trap layout
tools over stdio or HTTP.  Layouts are held in memory as ElectrodeSet
objects; GDS I/O goes through gdstk.

Run:
    iontrapclaw                     # stdio (for Claude Code)
    iontrapclaw --transport http    # streamable HTTP on 127.0.0.1:8765
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import tempfile
import traceback

os.environ.setdefault("MPLCONFIGDIR", "/tmp/mpl-iontrapclaw")

from mcp.server.fastmcp import FastMCP, Image

from .session import SessionManager

mcp = FastMCP("iontrapclaw")
SESSIONS = SessionManager()

# Cache of BEM solvers: layout name -> (geometry fingerprint, panel_size, solver)
_BEM_CACHE: dict[str, tuple] = {}


def _geometry_key(name: str) -> tuple:
    """Fingerprint the actual geometry used by the BEM solver.

    Electrode counts and names are insufficient: a generator may replace a
    layout with different coordinates while preserving both.  Include every
    coordinate and kind so in-place ``execute_script`` edits are also detected.
    """
    es = SESSIONS.get(name).electrodes
    electrodes = sorted(
        (e for e in es.electrodes if e.kind in ("dc", "rf", "ground")),
        key=lambda e: e.name,
    )
    return tuple(
        (
            e.name,
            e.kind,
            tuple(
                tuple((float(x), float(y)) for x, y in polygon)
                for polygon in e.polygons
            ),
        )
        for e in electrodes
    )


def _get_solver(name: str, max_panel_size: float):
    from .fields import BEMSolver

    key = (_geometry_key(name), float(max_panel_size))
    cached = _BEM_CACHE.get(name)
    if cached and cached[:2] == key:
        return cached[2]
    es = SESSIONS.get(name).electrodes
    solver = BEMSolver(
        [e for e in es.electrodes if e.kind in ("dc", "rf", "ground")],
        max_panel_size=max_panel_size,
    )
    _BEM_CACHE[name] = (key[0], key[1], solver)
    return solver


def _err(fn, *a, **kw):
    """Run a tool body, converting exceptions into readable error dicts."""
    try:
        return fn(*a, **kw)
    except Exception as exc:  # noqa: BLE001 - tool boundary
        return {"error": f"{type(exc).__name__}: {exc}", "traceback": traceback.format_exc()}


# ---------------------------------------------------------------------------
# Layout lifecycle
# ---------------------------------------------------------------------------


@mcp.tool()
def new_layout(name: str) -> dict:
    """Create a new empty layout session with the given name."""
    return _err(lambda: SESSIONS.create(name).summary())


@mcp.tool()
def list_layouts() -> list[dict]:
    """List all open layouts with electrode counts and metadata."""
    return SESSIONS.list()


@mcp.tool()
def close_layout(name: str) -> dict:
    """Close (discard) a layout session and invalidate its BEM cache."""
    def go():
        SESSIONS.close(name)
        _BEM_CACHE.pop(name, None)
        return {"closed": name}

    return _err(go)


@mcp.tool()
def list_electrodes(layout: str) -> dict:
    """List electrodes of a layout: names, kinds, layers, polygon counts."""
    def go():
        es = SESSIONS.get(layout).electrodes
        return {
            "layout": layout,
            "electrodes": [
                {
                    "name": e.name,
                    "kind": e.kind,
                    "layer": list(e.layer),
                    "n_polygons": len(e.polygons),
                }
                for e in es.electrodes
            ],
            "meta": es.meta,
        }

    return _err(go)


# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------


@mcp.tool()
def save_gds(layout: str, path: str) -> dict:
    """Save a layout to a GDS file (unit 1 µm)."""
    return _err(lambda: {"saved": SESSIONS.save_gds(layout, path)})


@mcp.tool()
def open_gds(path: str, name: str | None = None) -> dict:
    """Open a GDS file into a new layout session."""
    return _err(lambda: SESSIONS.open_gds(path, name).summary())


@mcp.tool()
def save_layout_json(layout: str, path: str) -> dict:
    """Save a layout to IonTrapClaw JSON (keeps electrode names/kinds)."""
    return _err(lambda: {"saved": SESSIONS.save_json(layout, path)})


@mcp.tool()
def open_layout_json(path: str, name: str | None = None) -> dict:
    """Open an IonTrapClaw JSON layout file."""
    return _err(lambda: SESSIONS.open_json(path, name).summary())


# ---------------------------------------------------------------------------
# Geometry generation
# ---------------------------------------------------------------------------


def _generators() -> dict:
    from . import electrodes as gen

    return {
        "five_wire": gen.five_wire,
        "x_junction": gen.x_junction,
        "t_junction": gen.t_junction,
        "two_layer": gen.two_layer,
        "racetrack": gen.racetrack,
    }


@mcp.tool()
def generate_trap(layout: str, trap_type: str, params: dict | None = None) -> dict:
    """Generate a parameterized ion-trap electrode geometry into a layout.

    trap_type: "five_wire" (segmented-DC surface linear trap),
    "x_junction", "t_junction", "two_layer", or "racetrack" (H2-like
    closed loop with optimizable bends).
    params: generator parameters, e.g. {"n_dc_segments": 11, "rf_width": 30}.
    All dimensions in micrometres. Replaces existing electrodes.
    """
    def go():
        dispatch = _generators()
        if trap_type not in dispatch:
            raise ValueError(
                f"unknown trap_type {trap_type!r}; choose from {sorted(dispatch)}"
            )
        es = dispatch[trap_type](**(params or {}))
        sess = SESSIONS.get(layout)
        sess.electrodes = es
        _BEM_CACHE.pop(layout, None)
        return {"layout": layout, "trap_type": trap_type, "summary": sess.summary()}

    return _err(go)


@mcp.tool()
def optimize_trap(
    layout: str,
    trap_type: str,
    param_names: list[str],
    p0: list[float],
    objectives: list[dict],
    fixed_params: dict | None = None,
    min_gap: float | None = None,
    panel_size: float = 8.0,
    ion_mass_amu: float = 171.0,
    rf_frequency_mhz: float = 30.0,
    rf_voltage: float = 100.0,
    max_evals: int = 300,
) -> dict:
    """Optimize a generator's parameters against BEM field objectives.

    Runs a Nelder-Mead loop: each evaluation rebuilds the geometry with
    ``builder(**{name: value, **fixed_params})``, solves the electrostatics,
    and scores the objectives:

    - ``{"type": "null_height", "region": {"x_range": [a,b], "y_range": [c,d],
      "z_guess": z}, "target": height_um, "weight": w}``
    — penalises (null_z − target)².
    - ``{"type": "null_uniform", "regions": [region, ...], "weight": w}``
    — penalises the spread of null heights across regions, plus in-plane
    deviation for regions with a ``"nominal": [x, y]`` anchor.
    - ``{"type": "bump", "path": [[x, y], ...], "weight": w}`` — penalises
    the max pseudopotential (meV) along the path, at height ``"z"`` or the
    null found by objective ``"z_from"`` (index).

    ``min_gap`` (µm) is a hard electrode-spacing constraint (penalty per µm
    of violation).  ``panel_size`` must be ≤ the smallest electrode gap.

    On success the best geometry replaces the layout's electrodes (render /
    evaluate / save it directly).  Returns best params, metrics, cost,
    evaluation count and wall time.  Long runs: prefer many cheap evals
    (coarser panel_size) and verify the winner with evaluate_trap at fine
    panels.
    """
    def go():
        from .optimize import optimize_geometry

        dispatch = _generators()
        if trap_type not in dispatch:
            raise ValueError(
                f"unknown trap_type {trap_type!r}; choose from {sorted(dispatch)}"
            )
        gen = dispatch[trap_type]
        fixed = dict(fixed_params or {})

        def builder(**kw):
            return gen(**{**fixed, **kw})

        result = optimize_geometry(
            builder, param_names, p0, objectives,
            min_gap=min_gap, panel_size=panel_size,
            ion_mass_amu=ion_mass_amu, rf_frequency_mhz=rf_frequency_mhz,
            rf_voltage=rf_voltage, max_evals=max_evals,
        )
        result_es = result.pop("electrodes")
        if result_es is None:
            raise RuntimeError("optimizer never produced a valid geometry")
        sess = SESSIONS.get(layout)
        sess.electrodes = result_es
        _BEM_CACHE.pop(layout, None)
        result["layout"] = layout
        result["trap_type"] = trap_type
        # keep the payload small: drop per-eval history params beyond summary
        hist = result.pop("history")
        result["history_summary"] = {
            "first_cost": hist[0].get("cost"),
            "best_cost": result["best_cost"],
            "n_evals": result["n_evals"],
        }
        return result

    return _err(go)


@mcp.tool()
def add_fanout(layout: str, pad_pitch: float = 150.0, pad_size: float = 100.0) -> dict:
    """Route every DC electrode to a bonding pad at the chip edge (traces on GDS layer 5)."""
    def go():
        from .electrodes import fanout

        sess = SESSIONS.get(layout)
        before = set(sess.electrodes.names)
        routed = fanout(sess.electrodes, pad_pitch=pad_pitch, pad_size=pad_size)
        sess.electrodes = routed
        _BEM_CACHE.pop(layout, None)
        added = [n for n in routed.names if n not in before]
        return {"layout": layout, "added": added}

    return _err(go)


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


@mcp.tool()
def render_layout(
    layout: str,
    labels: bool = True,
    xlim: list[float] | None = None,
    ylim: list[float] | None = None,
) -> Image:
    """Render the layout to a PNG image and return it for visual inspection."""
    from .render import render

    sess = SESSIONS.get(layout)
    out = os.path.join(tempfile.gettempdir(), f"iontrapclaw_{layout}.png")
    render(
        sess.electrodes,
        out,
        labels=labels,
        title=f"layout: {layout}",
        xlim=tuple(xlim) if xlim else None,
        ylim=tuple(ylim) if ylim else None,
    )
    return Image(path=out)


# ---------------------------------------------------------------------------
# Field evaluation
# ---------------------------------------------------------------------------


@mcp.tool()
def evaluate_trap(
    layout: str,
    rf_voltage: float = 100.0,
    rf_frequency_mhz: float = 30.0,
    ion_mass_amu: float = 171.0,
    max_panel_size: float = 10.0,
    dc_voltages: dict | None = None,
    height_guess: float | None = None,
) -> dict:
    """Characterize the trap with a BEM electrostatic solve.

    Returns trap position, depth (eV), secular frequencies (MHz) and the
    RF-null height.  dc_voltages: optional {electrode: volts}; missing
    electrodes are grounded.  rf_voltage is the 0-peak amplitude.
    """
    def go():
        from .fields import TrapAnalyzer

        sess = SESSIONS.get(layout)
        solver = _get_solver(layout, max_panel_size)
        rf = [e.name for e in sess.electrodes.by_kind("rf")]
        dc = [e.name for e in sess.electrodes.by_kind("dc")]
        if not rf:
            raise ValueError("layout has no RF electrodes (kind='rf')")
        analyzer = TrapAnalyzer(
            solver,
            rf_electrodes=rf,
            dc_electrodes=dc,
            ion_mass_amu=ion_mass_amu,
            rf_frequency_mhz=rf_frequency_mhz,
            rf_voltage=rf_voltage,
        )
        return analyzer.characterize(dc_voltages=dc_voltages, height=height_guess)

    return _err(go)


@mcp.tool()
def solve_dc_voltages(
    layout: str,
    targets: list[dict],
    max_panel_size: float = 10.0,
) -> dict:
    """Least-squares solve DC voltages that satisfy field/potential targets.

    Each target: {"point": [x, y, z] (µm), "type": "field_null"} or
    {"point": [...], "type": "potential", "value": volts}.
    Returns {electrode: volts}.
    """
    def go():
        from .fields import solve_dc_voltages as _solve

        sess = SESSIONS.get(layout)
        solver = _get_solver(layout, max_panel_size)
        dc = [e.name for e in sess.electrodes.by_kind("dc")]
        volts = _solve(solver, dc, targets)
        return {"voltages": volts, "dc_electrodes": dc}

    return _err(go)


# ---------------------------------------------------------------------------
# DRC
# ---------------------------------------------------------------------------


@mcp.tool()
def drc_check(layout: str, min_gap: float = 3.0) -> dict:
    """Check minimum spacing between all pairs of electrodes (µm)."""
    def go():
        from shapely.geometry import Polygon
        from shapely.ops import unary_union

        es = SESSIONS.get(layout).electrodes
        shapes = {
            e.name: unary_union([Polygon(p) for p in e.polygons])
            for e in es.electrodes
        }
        violations = []
        names = sorted(shapes)
        for i, a in enumerate(names):
            for b in names[i + 1 :]:
                d = shapes[a].distance(shapes[b])
                if d < min_gap:
                    violations.append({"a": a, "b": b, "gap": round(d, 4)})
        return {"min_gap": min_gap, "ok": not violations, "violations": violations}

    return _err(go)


# ---------------------------------------------------------------------------
# Escape hatch
# ---------------------------------------------------------------------------


@mcp.tool()
def execute_script(layout: str, code: str) -> dict:
    """Run Python against a layout's ElectrodeSet (variable `es`).

    Namespace also provides: np, gdstk, shapely, common (Electrode,
    ElectrodeSet).  Assign a value to `result` to return it.  Printed
    output is captured.  Use this for anything the dedicated tools do
    not cover.
    """
    def go():
        import gdstk
        import numpy as np
        import shapely

        from . import common

        sess = SESSIONS.get(layout)
        ns = {
            "es": sess.electrodes,
            "np": np,
            "gdstk": gdstk,
            "shapely": shapely,
            "Electrode": common.Electrode,
            "ElectrodeSet": common.ElectrodeSet,
            "result": None,
        }
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                exec(code, ns)  # noqa: S102 - intentional escape hatch
        finally:
            # Scripts may mutate polygons in place, including before raising.
            _BEM_CACHE.pop(layout, None)
        return {
            "stdout": buf.getvalue(),
            "result": repr(ns.get("result")),
            "n_electrodes": len(sess.electrodes.electrodes),
        }

    return _err(go)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="IonTrapClaw MCP server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default="stdio",
        help="MCP transport (default: stdio)",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    if args.transport == "http":
        mcp.settings.host = args.host
        mcp.settings.port = args.port
        mcp.run(transport="streamable-http")
    else:
        mcp.run()


if __name__ == "__main__":
    main()
