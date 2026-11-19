---
name: iontrap-junction
description: Generate X-junction or T-junction surface ion trap layouts via the iontrapclaw MCP server. Use when the user asks about junctions, ion shuttling between zones, QCCD architectures, or 2D trap arrays.
---

# Junction Trap Generation

Generate X- or T-junction surface traps through the `iontrapclaw` MCP tools.

## Workflow

1. `new_layout(name)`.
2. `generate_trap(layout, trap_type="x_junction" | "t_junction", params={...})`.
   Key parameters (µm): `arm_dc_segments` (6), `dc_width` (50), `dc_gap` (4),
   `rf_width` (25), `rf_gap` (5), `center_width` (15), `dc_length` (80).
3. `render_layout(layout)` — check the junction center: the `RF_CENTER` island
   must be centered and the four (or three) RF arm rails must connect to it
   smoothly; DC segments on each arm must be symmetric.
4. `drc_check(layout, min_gap=...)` — junctions are gap-critical; run this.
5. Save with `save_gds` / `save_layout_json`.

## Notes

- Naming: `RF_CENTER` (junction island), `RF_XP`/`RF_XN`/`RF_YP`/`RF_YN`
  (arm rails, P/N = +/- direction; T-junction lacks one arm),
  `DC_<arm>_<i>` for arm DC segments.
- Junction RF-null topology (whether the ponderomotive tube connects through
  the junction) depends strongly on `rf_width`/`center_width` ratios; always
  follow up with the `iontrap-field-eval` skill if the user cares about
  shuttling through the junction.
- Junctions with identical arm parameters are the safest starting point.
