---
name: kicad-routing
description: "Route a KiCad 10 board by hand with board.py: net classes and rules, track width for current, clearance for voltage, ground pours and return paths, differential pairs and impedance, then DRC until nothing is unrouted. Use when routing or re-routing, choosing track widths or net classes, adding pours, or reviewing routing. Edits are made with kicad-board-edit."
---

# Route a board

Route by hand, net by net, after placement (`kicad-placement`), with `board.py` (`kicad-board-edit`): `connect`,
`track`, `via`, `gnd_via` and `zone`. Run DRC (printed on every save) until nothing is unconnected.

## Rules and net classes

These live in the `.kicad_pro` JSON; edit it only while the PCB editor is closed.

- **Setting them:** `board.py rules` writes the fab's minimums, the Default class and a Power class;
  `set_rules(pro, classes={...})` adds others. `connect` and `track` take their width from the net's class.
- **Classes:** `net_settings.classes`, each with `name`, `track_width`, `clearance`, `via_diameter`, `via_drill`
  and `priority` (lower wins).
- **Assigning nets:** `net_settings.netclass_patterns` entries such as `{"netclass": "Power", "pattern": "+5V"}`.
  Patterns match the board's net names exactly (`/VBUS`) and accept wildcards (`/USB_D*`).
- **Minimums:** `board.design_settings.rules` (`min_clearance`, `min_track_width`, …), at or above the fab's limits.

DRC enforces a class's clearance but not its track width. Where width matters, add a rule to `<board>.kicad_dru`
(comments on their own lines):

```
(version 1)
(rule "Power track width"
	(condition "A.NetClass == 'Power'")
	(constraint track_width (min 0.5mm)))
```

## Width for current

Outer layers at a 10 °C rise, from IPC-2221 (`I = 0.048 · ΔT^0.44 · A^0.725`, A in mil²):

| Current | 1 oz | 2 oz |
|---|---|---|
| 0.5 A | 0.15 mm | 0.1 mm |
| 1 A | 0.3 mm | 0.15 mm |
| 2 A | 0.8 mm | 0.4 mm |
| 3 A | 1.4 mm | 0.7 mm |
| 5 A | 2.8 mm | 1.4 mm |

- **20 °C rise:** about ⅔ of these widths.
- **Inner layers:** about 2.6× the width at the same copper weight. JLC's inner copper is 0.5 oz, so take about 5×
  the 1 oz column.
- **Voltage drop:** 1 oz copper is about 0.5 mΩ per square (0.3 × 30 mm ≈ 50 mΩ).
- **Vias:** a 0.3 mm via carries about 1 A.

## Clearance for voltage

Below 30 V the fab minimum is enough. Above it, IPC-2221 B2 (external, uncoated):

| Voltage | Clearance |
|---|---|
| 31–150 V | 0.6 mm |
| 151–300 V | 1.25 mm |
| 301–500 V | 2.5 mm |

For mains, ask which safety standard applies (such as IEC 62368-1). Put those nets in their own class so DRC enforces
the clearance.

## Pours

- **Pad connections:** thermal reliefs for hand soldering; `zone(..., pads="solid")` for reflow. A "starved
  thermal" error on a pad boxed in by tracks: connect it with a track, or pour solid.
- **Dead copper:** keep island removal on (`island_removal_mode 0`).
- **After filling,** look at each copper layer (`view.py pcb --layers B.Cu`): a route can pass DRC and still cut a
  pour into islands or leave a fast signal without ground under it.

## Differential pairs and impedance

- **Width and gap:** from the fab's impedance calculator for the stackup you will order (JLC has one).
- **2-layer 1.6 mm boards:** 90 Ω needs impractically wide tracks. USB full-speed only needs short and matched;
  anything faster needs 4 layers.
- **Length:** compare a pair by summing `t.GetLength()` (mm via `pcbnew.ToMM`) over each net's tracks, in KiCad's
  Python. Via barrels aren't included.
- **Nearby pour** lowers impedance: keep it 3 track widths away, or design the line as coplanar waveguide.

## Pin swaps

If two nets cross only because of their pin assignment, swap interchangeable pins (op-amp or gate inputs, identical
units, same-function GPIOs, order-free connector pins). Confirm in the datasheet, change the schematic first, then
`board.py sync`, and report each swap.

## Doing it with board.py

1. **Plan from numbers.** `board.py pads` gives every pad's centre, size and net. Centreline to the edge of other
   copper: the clearance plus half the track width. Centreline to centreline of two tracks: the clearance plus half
   of each width.
2. **One routing script**, in a fresh process after placement: `connect` pad to pad (adding waypoints where the path
   must turn), `track` where every corner matters, vias where a net changes layer, `zone(...)` last.
3. **Iterate on the script, not the board:** start it with `remove_tracks(nets=["*"]); remove_zones()`, so a rerun
   replaces the whole route. Moving a part a few tenths of a mm often beats contorting a track: change the placement
   script and rerun both.
4. **Record** in the design notes any constraint a later change must respect.

Done when DRC reports no errors, no unconnected items and no parity issues.
