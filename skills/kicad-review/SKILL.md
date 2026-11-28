---
name: kicad-review
description: "Reviews a KiCad design's engineering against datasheets and reports findings worst first, without editing it. Schematic: absolute maximum ratings, connector misuse and ESD, power states, derating, floating inputs. Board layout: decoupling, regulator and crystal loops, return paths, differential pairs, current width, thermal copper, mechanics, silkscreen. Also simulates stages with ngspice (frequency response, gain, clipping, transients, fault currents). Use before ordering, after a design change, to simulate a circuit, or when the user asks whether an input can take a voltage, the design survives a fault or a layout is good. For ERC, DRC and manufacturing limits, use kicad-check."
---

# Review a design

| Task | Read first |
|---|---|
| The circuit: what each part sees electrically | [schematic.md](schematic.md) |
| The board: whether the layout serves the circuit | [layout.md](layout.md) |
| A frequency response, transient, headroom or power figure | [simulate.md](simulate.md) |

A request to review the whole design, or whether it's ready to order, covers both the schematic and the layout.

- **No edits.** The output is a findings table for the user, who chooses the fixes.
- **Numbers** carry their sources, so the user can check them.
