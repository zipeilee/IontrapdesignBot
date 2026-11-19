---
name: iontrap-surface-trap
description: Generate a segmented-DC surface linear ion trap (five-wire style) layout via the iontrapclaw MCP server. Use when the user asks for a surface trap, linear trap, Hall-bar-like trap geometry, or mentions RF rails and segmented DC electrodes.
---

# Surface Linear Trap Generation

Generate a parameterized segmented-DC surface ion trap through the
`iontrapclaw` MCP tools.

## Workflow

1. `new_layout(name)` — create a session (or reuse an existing empty one).
2. `generate_trap(layout, trap_type="five_wire", params={...})` — generate
   electrodes. Key parameters (µm):
   - `n_dc_segments` (default 11): number of DC segment pairs along the trap axis.
   - `dc_length` (100): x-extent of each DC segment.
   - `dc_width` (60): y-extent of each DC electrode.
   - `dc_gap` (5): along-x gap between adjacent DC segments.
   - `rf_width` (30), `rf_gap` (5): RF rail width and transverse gap between the center strip, RF rails, DC rows, and optional outer rails.
   - `center_width` (20): central DC strip width (ion chain runs above it).
   - `outer_dc` (true): add outer ground/DC rails.
3. `render_layout(layout)` — ALWAYS render and visually check the geometry:
   symmetric RF rails, correct segment count, no overlaps or missing gaps.
4. `drc_check(layout, min_gap=...)` — verify the foundry's minimum gap rule.
5. `save_gds(layout, path)` and/or `save_layout_json(layout, path)`.

## Notes

- Naming: `RF_L`/`RF_R` (RF rails), `CENTER` (central strip),
  `DC<i>_U`/`DC<i>_L` (upper/lower DC segments, i increasing along +x).
- If the user gives ion height instead of geometry: as a rule of thumb the
  RF-null height is comparable to the distance from the trap axis to the RF
  rail center; adjust `rf_gap`, `rf_width`, `center_width` and check with the
  `iontrap-field-eval` skill.
- Use `execute_script` for any manual tweaks the parameters cannot express.
