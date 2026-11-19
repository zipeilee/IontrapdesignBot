"""Tests for iontrap_mcp.optimize (generic geometry optimization)."""

from __future__ import annotations

import numpy as np
import pytest

from iontrap_mcp.electrodes import five_wire
from iontrap_mcp.optimize import optimize_geometry


def test_optimize_null_height_one_param():
    """Drive five_wire's center_width until the RF null hits a target height.

    The null height of a five-wire trap grows monotonically with the centre
    strip width (22.3 µm at width 15, 38.7 µm at width 40), so Nelder-Mead
    should get within ~10% of the target.
    """
    def builder(center_width):
        return five_wire(n_dc_segments=3, center_width=center_width,
                         length_pad=100.0)

    result = optimize_geometry(
        builder,
        param_names=["center_width"],
        p0=[15.0],
        objectives=[
            {
                "type": "null_height",
                "region": {"x_range": [-60, 60], "y_range": [-10, 10],
                           "z_guess": 25.0},
                "target": 30.0,
                "weight": 10.0,
            }
        ],
        panel_size=15.0,
        max_evals=40,
    )
    assert result["n_evals"] <= 41  # +1 for the final re-evaluation
    best_z = result["best_metrics"]["obj0_null_z"]
    assert best_z == pytest.approx(30.0, rel=0.10)
    assert result["electrodes"] is not None
    assert result["best_params"]["center_width"] != pytest.approx(15.0, rel=1e-3)


def test_optimize_respects_min_gap_constraint():
    """A builder that violates min_gap must be penalised, never crash."""

    def bad_builder(rf_gap):
        return five_wire(n_dc_segments=2, rf_gap=rf_gap)

    result = optimize_geometry(
        bad_builder,
        param_names=["rf_gap"],
        p0=[5.0],
        objectives=[
            {
                "type": "null_height",
                "region": {"x_range": [-60, 60], "y_range": [-10, 10],
                           "z_guess": 25.0},
                "target": 25.0,
                "weight": 1.0,
            }
        ],
        min_gap=4.0,
        panel_size=15.0,
        max_evals=30,
    )
    # best geometry must satisfy the constraint
    assert result["electrodes"] is not None
    from iontrap_mcp.optimize import _min_electrode_gap

    assert _min_electrode_gap(result["electrodes"]) >= 4.0 - 1e-6
