---
name: iontrap-field-eval
description: Evaluate ion trap RF pseudopotential, trap depth, secular frequencies and RF null via BEM electrostatics through the iontrapclaw MCP server. Use when the user asks whether a trap design works, wants trap frequencies/depth, or needs DC voltages solved for a target well position.
---

# Trap Field Evaluation (BEM)

Characterize a layout's trapping fields with the `iontrapclaw` MCP tools.

## Workflow

1. Ensure a layout exists (`list_layouts`, `list_electrodes`) with RF and DC
   electrodes (kind rf/dc are set automatically by the generators).
2. `evaluate_trap(layout, rf_voltage=..., rf_frequency_mhz=...,
   ion_mass_amu=..., max_panel_size=10, dc_voltages={...} | null)`.
   Returns: trap position (x, y, z µm), trap depth (eV), three secular
   frequencies (MHz), RF-null height.
   - Defaults are Yb-171+, 100 V_0p RF at 30 MHz.
   - `max_panel_size` controls BEM accuracy: 10 µm is fast; 5 µm for final
     numbers. The solver is cached per layout — repeated calls are cheap.
3. To place the DC null / set the well at a specific axial position:
   `solve_dc_voltages(layout, targets=[{"point": [x, y, z], "type": "field_null"}])`
   → returns {electrode: volts}. Pass the result back into `evaluate_trap` as
   `dc_voltages` to verify the combined potential.
4. Sanity-check numbers: surface traps typically give radial frequencies of
   1–10 MHz, depths of 10–1000 meV; if the solver returns nonsense, re-render
   the layout and check for geometry errors first.

## Interpreting results

- The RF-null height should roughly match the design ion height; if not,
  adjust `rf_gap`/`rf_width`/`center_width` (see `iontrap-surface-trap`).
- Very low axial frequency with default (all-ground) DC is normal — axial
  confinement comes from DC voltages; solve them with `solve_dc_voltages`.
- Report units exactly as returned (positions µm, depth eV, frequencies MHz).
