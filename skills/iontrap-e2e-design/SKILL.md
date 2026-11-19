---
name: iontrap-e2e-design
description: End-to-end ion trap design pipeline from a natural-language spec to a verified GDS file — geometry generation, DRC, fanout routing, BEM field evaluation, DC voltage solve, and iteration. Use when the user asks to design a complete trap chip or gives target specs like ion height, trap frequency, or segment count.
---

# End-to-End Ion Trap Design

Full pipeline from a spoken spec to a fabrication-ready GDS. Combines the
`iontrap-surface-trap`, `iontrap-junction` and `iontrap-field-eval` skills.

## Pipeline

1. **Parse the spec.** Extract: trap type (linear / X / T junction),
   ion species (default Yb-171+), target ion height, RF drive (voltage,
   frequency), number of DC segments, foundry design rules (min gap).
   State assumptions explicitly before generating.
2. **Generate.** `new_layout` + `generate_trap` with the chosen parameters.
3. **Inspect.** `render_layout` — show the user the geometry and confirm it
   matches intent before evaluating (BEM solves are the expensive step).
4. **DRC.** `drc_check(layout, min_gap=<foundry rule>)`. Fix violations by
   regenerating with adjusted gap parameters, never by hand-editing.
5. **Evaluate.** `evaluate_trap` with the user's RF parameters. Check:
   RF-null height vs. target, secular frequencies, trap depth.
6. **Iterate.** If the null height or frequencies miss the spec, adjust
   geometry (wider/narrower RF rails shift the height; RF voltage/frequency
   scale the ponderomotive confinement as V²/Ω²) and repeat from step 2.
   Expect 2–4 iterations.
7. **DC solution.** `solve_dc_voltages` for the target well position(s);
   for shuttling, solve a waveform over a grid of axial positions.
8. **Fanout + export.** `add_fanout(layout)` for bonding pads, re-run
   `drc_check`, then `save_gds(layout, "<name>.gds")` and
   `save_layout_json(layout, "<name>.json")` (JSON preserves electrode
   names for later re-evaluation).

## Reporting

Summarize in a table: geometry parameters, null height, secular frequencies,
trap depth, DC voltage extrema. Attach the rendered PNG. Save all artifacts
(GDS + JSON + summary) in the user's working directory.
