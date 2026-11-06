---
name: kicad-routing
description: "Plan and route a KiCad 10 board: net classes and rules, track width for current, voltage clearance, vias, ground pours and return paths, routing order, differential pairs and impedance at JLC, then DRC until nothing is unrouted. Use when routing or re-routing, choosing track widths or net classes, adding pours, or reviewing routing. Edits are made with kicad-board-edit."
---

# Route a board

Routing comes after placement (`kicad-placement`). Make the edits with `board.py` (`kicad-board-edit`): `connect`,
`track`, `via`, `gnd_via` and `zone`. Route by hand, net by net: every track is a decision about return paths,
clearance and how the board reads, which an autorouter doesn't make. Run DRC (printed on every save) until nothing
is unconnected.

## 1. Rules: net classes and minimums

These settings live in the `.kicad_pro` JSON. Edit it only while the PCB editor is closed, because an open editor
overwrites the file when it saves.

- **Classes:** `net_settings.classes`. To add one, copy `Default` and set `name`, `track_width`, `clearance`,
  `via_diameter`, `via_drill` and `priority` (lower wins).
- **Assigning nets:** add entries such as `{"netclass": "Power", "pattern": "+5V"}` to `net_settings.netclass_patterns`.
  Patterns match the board's net names exactly (`/VBUS`) and accept wildcards (`/USB_D*`).
- **Minimums:** `board.design_settings.rules` (`min_clearance`, `min_track_width`, `min_via_diameter`, …). Set them at
  or above the fab's limits.
- **Setting them:** `board.py rules` (`kicad-board-edit`) writes JLC-level minimums, the Default class and a Power
  class; `set_rules(pro, classes={...})` adds others.

DRC enforces a class's clearance but not its track width. If width matters, add a rule to `<board>.kicad_dru`, with
comments on their own lines:

```
(version 1)
# DRC doesn't enforce class widths by itself.
(rule "Power track width"
	(condition "A.NetClass == 'Power'")
	(constraint track_width (min 0.5mm)))
```

## 2. Width for current

These widths are for outer layers at a 10 °C rise, from IPC-2221 (`I = 0.048 · ΔT^0.44 · A^0.725`, with A in mil²):

| Current | 1 oz | 2 oz |
|---|---|---|
| 0.5 A | 0.15 mm | 0.1 mm |
| 1 A | 0.3 mm | 0.15 mm |
| 2 A | 0.8 mm | 0.4 mm |
| 3 A | 1.4 mm | 0.7 mm |
| 5 A | 2.8 mm | 1.4 mm |

- **20 °C rise:** about ⅔ of these widths is enough.
- **Inner layers:** these need about 2.5× the width, and JLC's inner copper is 0.5 oz. Carry current on outer layers
  or pours.
- **Voltage drop:** 1 oz copper is about 0.5 mΩ per square, so a track 0.3 mm wide and 30 mm long is about 50 mΩ.
- **Vias:** a 0.3 mm via carries about 1 A. Use at least two vias for each layer change on a power path.

## 3. Clearance for voltage

Below 30 V, the fab minimum is enough (0.1 mm at JLC). Above 30 V, IPC-2221 B2 (external, uncoated) gives:

| Voltage | Clearance |
|---|---|
| 31–150 V | 0.6 mm |
| 151–300 V | 1.25 mm |
| 301–500 V | 2.5 mm |

For mains circuits, ask the user which safety standard applies, such as IEC 62368-1. Put those nets in their own class
so DRC enforces the clearance.

## 4. Ground and return paths

Return current flows directly under its track. A gap in the ground there forces a detour, which makes a loop that
radiates.

- **4 layers:** keep In1 as solid, unbroken GND. Route signals on top. Use In2 for power pours or signals, and the
  bottom for signals.
- **2 layers:**
  - Keep the bottom an almost unbroken GND pour.
  - Route on top, and drop to the bottom only for short hops of a few mm. A long bottom track cuts the pour in two.
  - Pour GND on top as well.
  - Stitch the two pours with a via every 5–10 mm, and beside every layer change a signal makes.
- **Ground pads:** give each SMD ground pad its own via to the pour, at the pad.
- **Thermal reliefs:** keep them on pads that are hand-soldered. Use solid connections only where current or heat
  needs them. Set `min_resolved_spokes` above 1, and watch DRC for "starved thermal".
- **After filling:** look at each copper layer for islands and thin necks. A pour that reaches an area only through a
  neck is not a plane there.

## 5. Order

Route the most sensitive nets first:
1. **Decoupling:** from cap to pin, short and wide, with the ground via at the cap's ground pad.
2. **Switching regulators:** follow the datasheet layout.
   - Keep the hot loop (input cap, switches, back to the input cap) as small as possible, on one layer, with no vias.
   - Keep the switch node short and only as wide as its current needs.
3. **Crystals:** short, symmetric and on top, over unbroken ground, with nothing between or underneath. Guard them with
   pour, not tracks.
4. **Sensitive analog:** short, away from switch nodes and clocks, with no vias on high-impedance nodes.
5. **Differential pairs:** see section 6.
6. **Power:** wide tracks or pours, sized from section 2.
7. **Everything else.**

## 6. Differential pairs and impedance

- **Geometry:** route both tracks together at a constant gap, with equal length, the same vias, and unbroken ground
  underneath. The interface spec sets the length tolerance.
- **Width and gap:** use JLC's impedance calculator for the stackup you will order. Set the same stackup in the board.
- **2-layer 1.6 mm boards:** 90 Ω needs very wide tracks. For USB full-speed, short and matched is enough. Anything
  faster needs 4 layers.
- **Length:** sum `Track.length` per net to compare the two lengths of a pair.
- **Nearby pour:** copper pour lowers a track's impedance. Keep pour at least 3 track widths away, or design the line
  as coplanar waveguide and hold that gap exactly.

## 7. Easy to forget

- **Pin swaps:** if two nets cross only because of their pin assignment, swap the pins:
  - interchangeable op-amp or gate inputs;
  - identical units;
  - same-function GPIOs;
  - order-free resistor-network or connector pins.

  Confirm in the datasheet that the swap is allowed. Change the schematic first, then the board, then check parity.
  Report every swap.
- **Dead copper:** keep island removal set to "always" (`island_removal_mode 0`). Add a via to, or trim, any finger of
  pour that is connected at only one end.
- **Stitching:** add ground vias along the board edge, around noisy blocks, and in any pour area of several cm² that
  has none.
- **Connectors:** in a 3D render, check that each cable can leave its connector and that each plug has room.
- **Tangles:** rip up a tangled region and route it again in order, rather than patching it.

## 8. Doing it with board.py

1. **Plan on paper first.** `board.py pads` gives every pad's centre, size and net. For each net, write the path as
   points with 45° or 90° bends. For each segment, check its distance to other nets' pads and tracks: at least the
   clearance plus half of each width. Escape fine-pitch pins straight out, then turn. Tracks may run under an IC's
   body between its pad rows.
2. **One routing script**, run in a fresh process after placement: `connect` pad to pad (adding a waypoint where the
   path must turn), `track` where every corner matters, vias where a net changes layer, `gnd_via` beside each ground pad, `zone("GND", ...)` last. `save()` prints DRC.
   A "starved thermal" error on a pad boxed in by tracks: connect it with a track, or pour with `pads="solid"` on a
   reflow-assembled board.
3. **Iterate on the script, not the board:** start the routing script with `remove_tracks(nets=["*"]);
   remove_zones()`, so a rerun replaces the whole route. When DRC complains, fix the script and rerun it. Moving a part a few
   tenths of a mm often beats contorting a track; change the placement script and rerun both.
4. **Look** at the result (`view.py pcb`, both sides). A route can pass DRC and still cut a pour into islands.
5. **Record** in the design notes any constraint a later change must respect.

## Done when

- DRC reports no errors, no unconnected items, and no parity issues.
- There are no acute angles between tracks of the same net.
- Every power path has enough vias.
- Every fast or sensitive signal has unbroken copper under it.
