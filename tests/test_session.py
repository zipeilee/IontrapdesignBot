"""Tests for session management and rendering (no electrodes/fields deps)."""

import numpy as np
import pytest

from iontrap_mcp.common import Electrode, ElectrodeSet
from iontrap_mcp.session import SessionManager


def make_simple_es() -> ElectrodeSet:
    sq = np.array([[0, 0], [10, 0], [10, 10], [0, 10]], dtype=float)
    sq2 = sq + np.array([20.0, 0.0])
    return ElectrodeSet(
        electrodes=[
            Electrode(name="DC0", polygons=[sq], kind="dc"),
            Electrode(name="RF0", polygons=[sq2], kind="rf"),
        ],
        meta={"test": True},
    )


def test_session_lifecycle():
    sm = SessionManager()
    sess = sm.create("a")
    assert sess.name == "a"
    with pytest.raises(ValueError):
        sm.create("a")
    sess.electrodes = make_simple_es()
    summary = sm.get("a").summary()
    assert summary["n_electrodes"] == 2
    assert summary["by_kind"] == {"dc": 1, "rf": 1}
    sm.close("a")
    with pytest.raises(KeyError):
        sm.get("a")


def test_gds_roundtrip(tmp_path):
    sm = SessionManager()
    sess = sm.create("chip")
    sess.electrodes = make_simple_es()
    out = sm.save_gds("chip", str(tmp_path / "chip.gds"))
    assert out.endswith("chip.gds")
    sess2 = sm.open_gds(str(tmp_path / "chip.gds"), name="chip2")
    assert set(sess2.electrodes.names) == {"DC0", "RF0"}
    kinds = {e.name: e.kind for e in sess2.electrodes.electrodes}
    assert kinds == {"DC0": "dc", "RF0": "rf"}


def test_json_roundtrip(tmp_path):
    es = make_simple_es()
    p = tmp_path / "chip.json"
    es.to_json(p)
    es2 = ElectrodeSet.from_json(p)
    assert es2.names == es.names
    np.testing.assert_allclose(es2.electrodes[0].polygons[0], es.electrodes[0].polygons[0])
    assert es2.meta == {"test": True}


def test_render(tmp_path):
    from iontrap_mcp.render import render

    out = render(make_simple_es(), str(tmp_path / "r.png"), title="test")
    assert out.endswith("r.png")
    with open(out, "rb") as f:
        magic = f.read(8)
    assert magic.startswith(b"\x89PNG")
