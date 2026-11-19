"""Tests for iontrap_mcp.electrodes geometry generators."""

from __future__ import annotations

import numpy as np
import pytest
import gdstk
from shapely.geometry import Polygon as SPolygon

from iontrap_mcp.common import ElectrodeSet
from iontrap_mcp.electrodes import (
    five_wire,
    x_junction,
    t_junction,
    two_layer,
    racetrack,
    fanout,
)


def _shapes(es: ElectrodeSet) -> dict[str, SPolygon]:
    """One shapely polygon per electrode (first polygon, unary union)."""
    from shapely.ops import unary_union

    out = {}
    for e in es.electrodes:
        polys = [SPolygon(p) for p in e.polygons]
        out[e.name] = unary_union(polys)
    return out


def _min_pairwise_distance(es: ElectrodeSet) -> float:
    shapes = list(_shapes(es).values())
    best = np.inf
    for i in range(len(shapes)):
        for j in range(i + 1, len(shapes)):
            best = min(best, shapes[i].distance(shapes[j]))
    return best


# ---------------------------------------------------------------- five_wire


def test_five_wire_count_and_names():
    n = 11
    es = five_wire(n_dc_segments=n)
    assert isinstance(es, ElectrodeSet)
    # 2 RF + 1 CENTER + 2*n DC segments + 2 outer rails
    assert len(es.electrodes) == 2 + 1 + 2 * n + 2
    names = es.names
    assert "RF_L" in names and "RF_R" in names and "CENTER" in names
    for i in range(n):
        assert f"DC{i}_U" in names
        assert f"DC{i}_L" in names
    assert "DC_OUTER_U" in names and "DC_OUTER_L" in names
    # DC segments ordered along x: segment centroids increase with index
    xs = [es.by_name(f"DC{i}_U").polygons[0][:, 0].mean() for i in range(n)]
    assert np.all(np.diff(xs) > 0)
    # without outer rails
    es2 = five_wire(n_dc_segments=n, outer_dc=False)
    assert len(es2.electrodes) == 2 + 1 + 2 * n


def test_five_wire_no_overlap_and_gaps():
    dc_gap, rf_gap = 5.0, 5.0
    es = five_wire(dc_gap=dc_gap, rf_gap=rf_gap)
    shapes = _shapes(es)
    names = list(shapes)
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            d = shapes[names[i]].distance(shapes[names[j]])
            assert d >= min(dc_gap, rf_gap) - 1e-6, (
                f"{names[i]} vs {names[j]}: distance {d}"
            )
    # exact gaps between specific neighbours
    assert shapes["DC0_U"].distance(shapes["DC1_U"]) == pytest.approx(dc_gap, abs=1e-9)
    assert shapes["CENTER"].distance(shapes["RF_R"]) == pytest.approx(rf_gap, abs=1e-9)
    assert shapes["RF_R"].distance(shapes["DC0_U"]) == pytest.approx(rf_gap, abs=1e-9)
    assert shapes["DC0_U"].distance(shapes["DC_OUTER_U"]) == pytest.approx(
        rf_gap, abs=1e-9
    )


def test_five_wire_rf_length():
    n, dc_length, dc_gap, pad = 11, 100.0, 5.0, 200.0
    es = five_wire(n_dc_segments=n, dc_length=dc_length, dc_gap=dc_gap, length_pad=pad)
    seg_len = n * dc_length + (n - 1) * dc_gap
    rf = es.by_name("RF_R").polygons[0]
    assert rf[:, 0].max() - rf[:, 0].min() == pytest.approx(seg_len + 2 * pad)
    assert es.meta["segmented_length"] == pytest.approx(seg_len)


def test_five_wire_symmetry():
    es = five_wire()
    up = es.by_name("DC3_U").polygons[0]
    lo = es.by_name("DC3_L").polygons[0]
    assert up[:, 0].min() == pytest.approx(lo[:, 0].min())
    assert up[:, 1].min() == pytest.approx(-lo[:, 1].max())


# ---------------------------------------------------------------- roundtrips


def test_json_roundtrip(tmp_path):
    es = five_wire()
    path = tmp_path / "trap.json"
    es.to_json(path)
    es2 = ElectrodeSet.from_json(path)
    assert es2.names == es.names
    assert es2.meta["type"] == "five_wire"
    for e1, e2 in zip(es.electrodes, es2.electrodes):
        assert e1.kind == e2.kind
        assert tuple(e1.layer) == tuple(e2.layer)
        for p1, p2 in zip(e1.polygons, e2.polygons):
            assert np.allclose(p1, p2)


def test_cell_roundtrip_preserves_names():
    es = five_wire()
    lib = gdstk.Library()
    cell = es.to_cell(lib, "TOP")
    es2 = ElectrodeSet.from_cell(cell)
    assert set(es2.names) == set(es.names)
    assert len(es2.electrodes) == len(es.electrodes)


# ---------------------------------------------------------------- junctions


def test_x_junction_center_island():
    es = x_junction()
    island = es.by_name("RF_CENTER").polygons[0]
    c = island.mean(axis=0)
    assert c[0] == pytest.approx(0.0, abs=1e-9)
    assert c[1] == pytest.approx(0.0, abs=1e-9)
    side = island[:, 0].max() - island[:, 0].min()
    expected = 15.0 + 2 * 5.0 + 2 * 25.0  # center_width + 2*rf_gap + 2*rf_width
    assert side == pytest.approx(expected)
    for name in ("RF_XP", "RF_XN", "RF_YP", "RF_YN"):
        assert len(es.by_name(name).polygons) == 2
    for name in ("DC_CORNER_PP", "DC_CORNER_PN", "DC_CORNER_NP", "DC_CORNER_NN"):
        assert name in es.names


def test_x_junction_no_overlap_and_gaps():
    es = x_junction()
    dmin = _min_pairwise_distance(es)
    assert dmin >= min(es.meta["dc_gap"], es.meta["rf_gap"]) - 1e-6
    shapes = _shapes(es)
    # exact gaps around the island and corner electrodes
    assert shapes["RF_CENTER"].distance(shapes["RF_XP"]) == pytest.approx(
        es.meta["rf_gap"], abs=1e-9
    )
    assert shapes["RF_CENTER"].distance(shapes["RF_YN"]) == pytest.approx(
        es.meta["rf_gap"], abs=1e-9
    )
    assert shapes["DC_CORNER_PP"].distance(shapes["DC_XP0_U"]) == pytest.approx(
        es.meta["dc_gap"], abs=1e-9
    )
    assert shapes["DC_CORNER_PP"].distance(shapes["RF_XP"]) == pytest.approx(
        es.meta["rf_gap"], abs=1e-9
    )


def test_t_junction_structure():
    es = t_junction()
    assert "RF_YP" in es.names and "RF_YN" not in es.names
    assert "RF_XP" in es.names and "RF_XN" in es.names
    assert "DC_CORNER_PP" in es.names and "DC_CORNER_NP" in es.names
    assert "DC_CORNER_PN" not in es.names and "DC_CORNER_NN" not in es.names
    island = es.by_name("RF_CENTER").polygons[0]
    assert np.allclose(island.mean(axis=0), [0.0, 0.0])
    dmin = _min_pairwise_distance(es)
    assert dmin >= min(es.meta["dc_gap"], es.meta["rf_gap"]) - 1e-6


def test_x_junction_center_strips():
    es = x_junction()
    assert es.meta["center_strip"] is True
    for name in ("CENTER_XP", "CENTER_XN", "CENTER_YP", "CENTER_YN"):
        assert es.by_name(name).kind == "ground"
    shapes = _shapes(es)
    # exact rf_gap to the island and to the neighbouring rails
    assert shapes["CENTER_XP"].distance(shapes["RF_CENTER"]) == pytest.approx(
        es.meta["rf_gap"], abs=1e-9
    )
    assert shapes["CENTER_XP"].distance(shapes["RF_XP"]) == pytest.approx(
        es.meta["rf_gap"], abs=1e-9
    )
    # strip spans the same extent along the arm as the RF rails, with
    # width equal to center_width
    strip = es.by_name("CENTER_XP").polygons[0]
    rail = es.by_name("RF_XP").polygons[0]
    assert strip[:, 0].min() == pytest.approx(rail[:, 0].min())
    assert strip[:, 0].max() == pytest.approx(rail[:, 0].max())
    assert strip[:, 1].max() - strip[:, 1].min() == pytest.approx(
        es.meta["center_width"]
    )
    # overall spacing rules are still respected with the strips present
    dmin = _min_pairwise_distance(es)
    assert dmin >= min(es.meta["dc_gap"], es.meta["rf_gap"]) - 1e-6
    # opt-out removes them
    es2 = x_junction(center_strip=False)
    assert not any(n.startswith("CENTER_") for n in es2.names)
    assert es2.meta["center_strip"] is False


def test_t_junction_center_strips():
    es = t_junction()
    assert "CENTER_XP" in es.names and "CENTER_XN" in es.names
    assert "CENTER_YP" in es.names and "CENTER_YN" not in es.names
    dmin = _min_pairwise_distance(es)
    assert dmin >= min(es.meta["dc_gap"], es.meta["rf_gap"]) - 1e-6


# ---------------------------------------------------------------- two_layer


def test_two_layer():
    es = two_layer(n_segments=5)
    assert len(es.electrodes) == 10
    for i in range(5):
        e0 = es.by_name(f"L0_DC{i}")
        e1 = es.by_name(f"L1_DC{i}")
        assert tuple(e0.layer) == (1, 0)
        assert tuple(e1.layer) == (4, 0)
    assert es.meta["layer_gap"] == pytest.approx(100.0)


# ---------------------------------------------------------------- racetrack


def test_racetrack_structure_and_gaps():
    es = racetrack()
    # 4 concentric bands + 2 caps + 2 rows × n DC segments
    n = es.meta["n_dc_segments"]
    assert len(es.electrodes) == 4 + 2 + 2 * n
    assert es.by_name("RF_INNER").kind == "rf"
    assert es.by_name("RF_OUTER").kind == "rf"
    assert es.by_name("CENTER").kind == "ground"
    assert es.by_name("GND_MID").kind == "ground"
    # rings are split into two hole-free half-ring polygons
    assert len(es.by_name("RF_INNER").polygons) == 2
    assert len(es.by_name("GND_MID").polygons) == 2
    dmin = _min_pairwise_distance(es)
    assert dmin >= min(es.meta["dc_gap"], es.meta["rf_gap"]) - 1e-6


def test_racetrack_bend_params():
    es = racetrack(bend_shift=2.0, bend_trim=-1.0)
    assert es.meta["bend_shift"] == 2.0
    es2 = racetrack(bend_profile=[3.0, 3.6, -0.5, 3.0, 4.0, -0.3, 9.2])
    assert es2.meta["bend_profile"] == [3.0, 3.6, -0.5, 3.0, 4.0, -0.3, 9.2]
    # tightest bend gap: mid outer edge (86+4=90) to outer-rail inner (94-0.3=93.7)
    dmin = _min_pairwise_distance(es2)
    assert dmin == pytest.approx(3.7, abs=0.05)
    with pytest.raises(ValueError):
        racetrack(bend_profile=[1.0, 2.0])


# ---------------------------------------------------------------- fanout


def test_fanout_pads_and_traces():
    es = five_wire()
    routed = fanout(es, pad_pitch=150.0, pad_size=100.0)
    dc_names = [e.name for e in es.by_kind("dc")]
    pads = [e for e in routed.electrodes if e.name.startswith("PAD_")]
    traces = [e for e in routed.electrodes if e.name.startswith("TRACE_")]
    assert len(pads) == len(dc_names)
    assert len(traces) == len(dc_names)
    for name in dc_names:
        assert f"PAD_{name}" in routed.names
        assert f"TRACE_{name}" in routed.names
    for e in pads + traces:
        assert tuple(e.layer) == (5, 0)
    # original electrodes are preserved
    for name in es.names:
        assert name in routed.names


def test_fanout_pads_do_not_overlap():
    es = five_wire()
    routed = fanout(es)
    pads = {
        e.name: SPolygon(e.polygons[0])
        for e in routed.electrodes
        if e.name.startswith("PAD_")
    }
    names = list(pads)
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            assert pads[names[i]].distance(pads[names[j]]) > 0, (
                f"pads {names[i]} and {names[j]} overlap"
            )
