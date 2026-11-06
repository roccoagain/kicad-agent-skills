---
name: kicad-routing
description: Decide how to route a KiCad 10 board and do it through the IPC API - net classes and design rules in the project file, track width for current (IPC-2221 table), voltage clearance, vias, ground pours and return paths on 2- and 4-layer boards, routing order, decoupling, crystals, switching regulators, differential pairs and impedance at JLC - then check with DRC until nothing is unrouted. Use when routing or re-routing a board, choosing track widths or net classes, adding pours, or reviewing a layout's routing.
---

# Route a board

Routing follows placement (`kicad-placement`): once parts are placed well, most connections are short and obvious.
Edits go through the API (`kicad-board-edit`): tracks are `Track`, vias `Via`, pours `Zone`. KiCad has no
command-line autorouter, so route by computing coordinates from pad positions, a few nets at a time, with DRC after
each batch.

## 1. Rules first: net classes, widths, vias

Net classes and board minimums live in the `.kicad_pro` (JSON). Edit them with the PCB editor closed: an open
editor writes its own copy back on save.
- **Net classes:** `net_settings.classes` holds one object per class. Copy `Default` and change `name`,
  `track_width`, `clearance`, `via_diameter`, `via_drill`, and `priority` (lower wins).
- **Which nets belong to a class:** `net_settings.netclass_patterns`, a list of
  `{"netclass": "Power", "pattern": "+5V"}`. Patterns match net names exactly as the board has them (`/VBUS`,
  `GND`) and accept wildcards (`/USB_D*`).
- **Board minimums:** `board.design_settings.rules` holds `min_clearance`, `min_track_width`, `min_via_diameter`,
  `min_through_hole_diameter`, `min_via_annular_width`, `min_copper_edge_clearance` and others. Set them at or
  above the fab's limits (`kicad-check`).
- **Width and via choices:** `board.design_settings.track_widths` and `via_dimensions` are the lists the editor
  offers. The first entry, 0, means "use the net class".

Check the assignment with `get_netclass_for_nets(...)` through the API after reopening the board.

DRC enforces a class's clearance, but **not its track width**: the width is only the editor's default, and a
0.2 mm track in a 0.5 mm class passes DRC. Where width matters (current, voltage drop), add a rule to the
project's `<board>.kicad_dru`, comments on their own lines:

```
(version 1)
# Power tracks at least as wide as their class: DRC doesn't enforce class widths by itself.
(rule "Power track width"
	(condition "A.NetClass == 'Power'")
	(constraint track_width (min 0.5mm)))
```

## 2. Track width for current

IPC-2221, outer layer, 1 oz (35 µm) copper, 10 °C rise above ambient. Computed from the standard's formula
`I = 0.048 · ΔT^0.44 · A^0.725`, with A in mil²:

| Current | Width (1 oz outer) | Width (2 oz outer) |
|---|---|---|
| 0.5 A | 0.15 mm (use your signal width) | 0.1 mm |
| 1 A | 0.3 mm | 0.15 mm |
| 2 A | 0.8 mm | 0.4 mm |
| 3 A | 1.4 mm | 0.7 mm |
| 5 A | 2.8 mm | 1.4 mm |

- A 20 °C rise allows about two thirds of these widths.
- IPC-2221's internal-layer figures are about 2.5× wider. JLC's inner layers are 0.5 oz by default, so carry
  current on outer layers or on pours, not on inner tracks.
- For long or high-current paths, the voltage drop matters as much as heating. 1 oz copper is about 0.5 mΩ per
  square, so a 0.3 mm × 30 mm track is about 50 mΩ.
- **Vias carry current too.** As a rule of thumb, a 0.3 mm via carries about 1 A. Use at least two per layer change
  on a power path, and several for a pour connection.

## 3. Clearance for voltage

Below about 30 V, the fab minimum (JLC: 0.1 mm) is enough electrically. Above that, IPC-2221 (table 6-1, B2:
external, uncoated, below 3050 m) asks for:

| Between conductors at | Clearance |
|---|---|
| 31–150 V | 0.6 mm |
| 151–300 V | 1.25 mm |
| 301–500 V | 2.5 mm |

Mains-connected circuits follow their safety standard's creepage and clearance (IEC 62368-1 and similar), not this
table. Ask the user which applies. Put such nets in their own net class with that clearance, so DRC enforces it.

## 4. Ground and return paths

Every signal's current comes back through ground, directly under the track when it can. A gap in the ground under a
signal forces the return around it: a loop that radiates, picks up noise and adds inductance.
- **4 layers:** layer 2 (In1) solid GND, unbroken. Route signals on layer 1 over it. Layer 3 is power pours or
  signals, layer 4 more signals. Don't route on layer 2.
- **2 layers:** keep the bottom a nearly unbroken GND pour. Route on top, and drop to the bottom only for short
  hops (a few mm) that cross other tracks. Never run a long track on the bottom across the board: it cuts the pour
  in two. Pour GND on top too, around the routing, and stitch the two pours with vias every 5–10 mm and next to
  each layer change of a signal.
- Give each SMD ground pad its own via to the pour, right at the pad. Don't daisy-chain grounds through tracks.
- Pours: use thermal reliefs for pads that will be hand-soldered (the default), and solid connections only where
  current or heat needs them. Set `min_resolved_spokes` above 1 and look for "starved thermal" in DRC.
- After pouring, look for islands and narrow necks (`kicad-view`, both copper layers, one per PDF). A pour that
  reaches a region only through a thin neck isn't a ground plane there.

## 5. Order of routing

The same order as placement, most sensitive first, while the space is free:
1. **Decoupling:** capacitor to pin, as short and wide as the pads allow. Put the via to ground at the capacitor's
   ground pad, not somewhere along the way.
2. **Switching regulator power loops,** exactly as the datasheet's layout section shows: the hot loop (input cap,
   switch, diode or low-side switch, back to the input cap) smallest, on one layer, without vias. The switch node
   should be short and only as wide as its current needs: it radiates.
3. **Crystals and oscillators:** short, symmetric, on the top layer over unbroken ground, no other signals between
   or under them. Guard with ground pour, not with tracks.
4. **Sensitive analog:** high-impedance inputs, references, feedback dividers. Short, away from switch nodes and
   clocks, with no vias in high-impedance nodes.
5. **Differential pairs and controlled impedance** (USB, Ethernet, LVDS, HDMI): see below.
6. **Power distribution:** wide tracks or pours from the source to each load, sized by section 2.
7. **Everything else.**

## 6. Differential pairs and impedance

- Route the two tracks together at a constant gap, the same length (match to within a fraction of a mm for USB
  full-speed and to tighter tolerances for faster links; the interface spec says), with the same number of vias,
  over unbroken ground.
- The width and gap that give 90 Ω (USB) or 100 Ω depend on the stackup. Use JLC's impedance calculator for the
  stackup the order will use (JLC lists its standard 4- and 6-layer stackups), and set the same stackup in the
  board, so the calculator's numbers apply.
- A 2-layer 1.6 mm board puts ground 1.5 mm below the track, so 90 Ω needs very wide tracks. For USB full-speed
  (12 Mb/s), short and matched is enough. For anything faster, use 4 layers.
- `Track.length` (API) gives each segment's length. Sum it per net to compare a pair's lengths.

## 7. Easy to forget

- **Swap pins in the schematic to untangle the board.** If two nets cross, or need extra vias, only because of which
  pin each landed on, change the pin assignment:
  - the two inputs of a gate or op-amp unit, or two identical units;
  - a GPIO for another with the same function;
  - the pins of a resistor network or connector whose order doesn't matter.

  First confirm the datasheet allows it (an MCU's alternate-function table; which op-amp pins are interchangeable).
  Make the change in the schematic (`kicad-schematic`), then on the board, then confirm with parity. Never swap pins
  with different functions. Tell the user which swaps you made.
- **Remove dead copper.** An island of pour connected to nothing, or a long thin finger joined at one end, acts as an
  antenna. Leave zone island removal set to always (`island_removal_mode 0`). After each fill, look at every copper layer
  and either add a stitching via or trim the pour where a finger or island has appeared.
- **Stitch the ground pours together.** Add vias between the top and bottom ground pours along the board edge, around
  noisy blocks, beside each via where a fast signal changes layer (so its return current can change too), and
  wherever a pour area of more than a few square centimetres has none.
- **Keep pours back from controlled-impedance tracks.** Ground copper close beside a track lowers its impedance. Either
  hold the pour at least three track widths away, or model it as coplanar waveguide in JLC's calculator and keep that
  gap exact.
- **Check that the cables fit.** In a 3D render (`kicad-view`), confirm each connector faces the direction its cable
  leaves, that the plug and any tool have room, and that nothing tall stands in the way.
- **Re-route a tangle from scratch.** When a region has become a mess, delete its tracks and route it again in the order
  of section 5, instead of patching.
- **Autorouting.** KiCad has no built-in autorouter, so route by hand through the API unless the user agrees to
  something else. Freerouting is the usual external one and is worth it only on dense boards with hundreds of
  connections. Route and lock the critical nets first (power loops, crystals, analog, differential pairs), then
  review everything it produces against this skill.

## 8. Doing it through the API

1. List the pads of each net from the board (`get_pads()` gives positions and nets). Plan each path as straight
   runs and 45° bends, at least one clearance plus half a track width away from every other pad and track.
2. Create the `Track` and `Via` items for a few nets per commit (`kicad-board-edit`), refill zones, save.
3. Run DRC (`kicad-check`): `unconnected_items` lists what's left to route, and clearance errors give the exact
   spot. Fix and repeat until DRC has no errors and nothing is unconnected.
4. Look at it (`kicad-view`) after each group: a route that passes DRC can still cut a ground pour or wander.
5. Record in the design notes anything a later change must respect (a keep-out, a matched pair, a current path).

## Checks a routed board must pass

- DRC: no errors, no unconnected items, no parity issues.
- No acute angles between tracks of the same net (acid traps on older processes, and they're usually mistakes).
- Every via used for current is counted: enough for the current.
- The return path of each fast or sensitive signal is visible in the pictures: unbroken copper under it.
