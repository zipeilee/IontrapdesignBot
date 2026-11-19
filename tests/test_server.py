"""End-to-end test: drive the MCP server over stdio with a real client."""

import asyncio
import json
import sys
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

pytestmark = pytest.mark.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent


def _text(result) -> dict:
    assert not result.isError, result.content
    return json.loads(result.content[0].text)


async def _run(tmp_path):
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "iontrap_mcp.server"],
        cwd=str(ROOT),
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            names = {t.name for t in tools.tools}
            assert {
                "new_layout",
                "generate_trap",
                "render_layout",
                "evaluate_trap",
                "solve_dc_voltages",
                "drc_check",
                "save_gds",
                "execute_script",
            } <= names

            r = _text(await session.call_tool("new_layout", {"name": "t1"}))
            assert r["name"] == "t1"

            r = _text(
                await session.call_tool(
                    "generate_trap",
                    {
                        "layout": "t1",
                        "trap_type": "five_wire",
                        "params": {"n_dc_segments": 5},
                    },
                )
            )
            assert r["summary"]["by_kind"]["rf"] == 2
            n_electrodes = r["summary"]["n_electrodes"]

            # Evaluate, then regenerate with identical names/counts but changed
            # coordinates. The second solve must not reuse the old BEM solver.
            r = _text(
                await session.call_tool(
                    "evaluate_trap",
                    {"layout": "t1", "max_panel_size": 15.0},
                )
            )
            assert "error" not in r, r
            original_null_height = r["rf_null_height_um"]

            r = _text(
                await session.call_tool(
                    "generate_trap",
                    {
                        "layout": "t1",
                        "trap_type": "five_wire",
                        "params": {"n_dc_segments": 5, "center_width": 40.0},
                    },
                )
            )
            assert r["summary"]["n_electrodes"] == n_electrodes

            r = _text(
                await session.call_tool(
                    "evaluate_trap",
                    {"layout": "t1", "max_panel_size": 15.0},
                )
            )
            assert "error" not in r, r
            assert abs(r["rf_null_height_um"] - original_null_height) > 5.0

            r = _text(
                await session.call_tool("drc_check", {"layout": "t1", "min_gap": 3.0})
            )
            assert r["ok"], r["violations"]

            r = _text(await session.call_tool("add_fanout", {"layout": "t1"}))
            assert "error" not in r, r
            n_dc = 13  # 5 segment pairs + CENTER + 2 outer rails
            assert len(r["added"]) == 2 * n_dc  # TRACE_* + PAD_* per DC electrode
            r = _text(await session.call_tool("list_electrodes", {"layout": "t1"}))
            assert len(r["electrodes"]) == 15 + 2 * n_dc

            out = tmp_path / "t1.gds"
            r = _text(
                await session.call_tool(
                    "save_gds", {"layout": "t1", "path": str(out)}
                )
            )
            assert Path(r["saved"]).exists()

            r = _text(
                await session.call_tool(
                    "execute_script",
                    {"layout": "t1", "code": "result = len(es.electrodes)"},
                )
            )
            assert "error" not in r
            assert int(r["result"]) > 4

            img = await session.call_tool("render_layout", {"layout": "t1"})
            assert not img.isError

            r = _text(
                await session.call_tool(
                    "evaluate_trap",
                    {
                        "layout": "t1",
                        "rf_voltage": 80.0,
                        "rf_frequency_mhz": 40.0,
                        "max_panel_size": 15.0,
                    },
                )
            )
            assert "error" not in r, r
            assert r["secular_frequencies_mhz"]
            assert all(f > 0 for f in r["secular_frequencies_mhz"])

            x, y, z = r["position"]
            r = _text(
                await session.call_tool(
                    "solve_dc_voltages",
                    {
                        "layout": "t1",
                        "targets": [
                            {"point": [x, y, z], "type": "field_null"}
                        ],
                        "max_panel_size": 15.0,
                    },
                )
            )
            assert "error" not in r, r
            assert r["voltages"]


def test_mcp_server_end_to_end(tmp_path):
    asyncio.run(_run(tmp_path))


def test_geometry_key_tracks_in_place_coordinate_changes():
    """A script edit with unchanged names/counts must change the cache key."""
    from iontrap_mcp import server
    from iontrap_mcp.electrodes import five_wire

    name = "geometry-key-regression"
    server.SESSIONS.create(name)
    try:
        sess = server.SESSIONS.get(name)
        sess.electrodes = five_wire(n_dc_segments=2)
        before = server._geometry_key(name)
        sess.electrodes.electrodes[0].polygons[0][0, 0] += 1.0
        after = server._geometry_key(name)
        assert after != before
    finally:
        server.SESSIONS.close(name)
        server._BEM_CACHE.pop(name, None)
