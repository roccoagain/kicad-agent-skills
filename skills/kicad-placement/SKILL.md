---
name: kicad-placement
description: Plan where parts go on a KiCad 10 PCB before moving any - fixed parts first, then the parts whose connections must be short (decoupling, switching loops, crystals), then the rest - with the physics behind each rule, a pad-clearance check for parts that share a pin row, and a checklist for assembly and hand soldering. Use when planning or reviewing placement or a re-layout, and together with kicad-board-edit when moving parts.
---

# Where parts go

Routing can only connect what placement has put within reach. A decoupling cap two centimetres from its pin, or a
connector on the wrong edge, stays that way however the tracks are drawn. So decide placement from the circuit's
needs, in a fixed order, and write down why.

## What placement controls

1. **Loop area and inductance.** Every current returns to its source. The loop it makes (out on a track, back through
   ground) radiates, picks up interference and has inductance in proportion to its size. Fast edges through a big
   loop show up as ringing and supply droop. Shrinking the loops that carry fast current is the main job of placement.
2. **Track length on sensitive nodes.** A long track on a high-impedance node is an antenna, and on a clock or RF line
   it is a delay or a mismatch. Low-impedance outputs tolerate length; high-impedance inputs don't.
3. **Heat.** Regulators, power resistors and LEDs dissipate heat into copper. Spread them, and keep temperature-
   sensitive parts (references, crystals, electrolytic caps) away from them.
4. **Mechanics.** Connectors, switches, indicators and mounting holes are where the enclosure and the user need them.
5. **Manufacturing.** Reachable pads, clear courtyards, parts inside the pick-and-place margin, a board that can be
   probed and reworked.

When a rule below conflicts with one of these on a particular board, follow the effect and say so in the notes.

## Order of work

1. **Fix the mechanical parts.** Outline, mounting holes, connectors, jacks, switches, LEDs, displays, anything the
   enclosure dictates. Place them, then lock them so later steps can't push them.
2. **Sketch the blocks.** Read the schematic (`kicad-view` and the netlist). Name the blocks (power input, regulator,
   MCU, analog front end, RF, drivers) and give each a region. Put blocks that share many nets next to each other and
   keep each block's noisy parts away from the sensitive ones in other blocks.
3. **Orient the large ICs.** For each, try all four rotations and keep the one that points its pins toward what they
   connect to: connectors, other ICs, the board edge. Take pin positions from the pads in the board file; the schematic
   symbol's pin order says nothing about the package.
4. **Place the short-connection parts**, in this order, while the space around the pins is still free:
   1. a switching regulator's power loop;
   2. crystals and their load capacitors;
   3. decoupling capacitors, at the supply pins they serve;
   4. input filters, series terminations, ESD and protection parts at the pin or connector they protect;
   5. bulk capacitors, pull-ups and other parts that can sit anywhere on their net.
5. **Place the rest** around the blocks, passives next to the pins they serve, and leave lanes for routing.
6. **Check** (see the end), fix, and record the decisions.

Place by computed coordinates (pad positions plus the offsets you want), not by eye: a placement judged by eye is
often 0.3 mm off, and that is half an 0201.

## Rules by part type

**Decoupling capacitors.** The loop that matters runs from the cap's pads through the IC's supply pin, its die and
its ground pin. Put the cap against the supply pin it serves, with its supply pad toward the pin and a ground via
touching its ground pad. If a part has several supply pins and enough caps, give each pin one. With fewer caps than
pins, follow the vendor's layout drawing. Where the vendor orders the values (small cap closest) follow that; without
guidance, put the smallest value nearest the pin. A bulk cap goes behind the small one, on the same supply track.

**Switching regulators.** Find the loop the datasheet marks as critical. For a buck it is the input capacitor, the
high-side switch, the low-side switch (or diode) and back to the input capacitor. For a boost it is the output
capacitor, the switch and the diode. Make that loop as small as the package allows, keep the switch node compact (it
is a large, fast, noisy copper area, so no bigger than the current needs), and keep feedback dividers and the
compensation network on the quiet side of the IC, away from the inductor.

**Crystals and resonators.** Both load capacitors beside the crystal, the crystal beside the two oscillator pins, the
two paths close to equal in length, and nothing routed between the crystal and the chip. Keep noisy tracks out from
under the crystal.

**Analog and reference nodes.** Keep high-impedance nodes (an op-amp input, a reference pin, a feedback node) a few
millimetres long, without vias, and not near switch nodes, clocks or buses. Put a filter or divider at the pin it
serves, not at the source. Let low-impedance outputs run the long distance.

**Protection and termination.** ESD diodes and TVS parts go at the connector, before anything else on that net.
Series termination goes at the driving pin. A ferrite bead or link between two supply domains sits between the caps
of the two domains.

**RF.** Place matching and filter parts in schematic order along a straight line from the chip to its connector or
antenna, with shunt parts branching off at the nodes between series parts and their grounds on the side away from the
line. Follow the vendor's reference layout exactly, including the ground-via pattern, if one exists.

**Noisy and quiet circuits.** Noisy: switch nodes, clocks, digital buses, motor and LED drivers, wiring from external
power. Quiet: analog inputs, references, audio, RF front ends. Keep their copper apart, and place connectors so that
return current has a short way home that doesn't pass under the quiet part.

**Heat.** Leave copper around regulators and power resistors, spread out the biggest dissipators, and keep references
and crystals clear of them. A part with an exposed pad needs its via field, so keep that area free.

## Check the pad space around fine-pitch parts

Two passives at neighbouring pins, each centred on its own pin, fit only if their courtyards, measured along the pin
row, don't overlap: courtyard widths added, no more than twice the pitch. With KiCad's stock courtyards (0.70 mm
across for 0201, 0.92 mm for 0402, 1.46 mm for 0603), two 0402s need a pitch of 0.92 mm or more. They fit on a 1.27 mm
SOIC, not on 0.65 mm TSSOP or 0.5 mm QFN pins. When they don't fit:
- stagger one of them further from the package;
- put one on the opposite side of the pin row, or the other side of the board if the design is two-sided;
- let the part that tolerates distance move, and keep the one that doesn't.

Always leave a route out. Every pad needs room for a track to leave it, and a fine-pitch row needs clear space in
front of it until its tracks can fan out or change layer. If a decoupling cap and an escaping track compete for a spot,
the cap stays and the track goes around.

## Manufacturing and testing

- No courtyard overlaps (DRC reports them).
- Keep parts at least 2.5 mm from the board edge for JLC assembly, or plan rails (`kicad-assembly-export`).
- Prefer one side. Ask before putting parts on the bottom unless the user has already chosen a two-sided board.
- Orient polarised parts and pin-1 marks consistently, so a human can check them quickly.
- Keep test points and programming headers reachable by a probe or cable, with nothing tall beside them.
- For hand soldering, leave at least 1 mm between pads of different blocks for the iron, use 0805 or larger where the
  design allows, and use thermal reliefs on pads that connect to pours.
- Put reference designators where silk can show them after assembly, and out from under tall parts.

## Doing it with the other skills

1. Read the schematic and each IC's datasheet layout section. Treat anything it states as a requirement (ground tied
   to one pin, keep-out, maximum length), and anything it only suggests as advice.
2. Move parts with `kicad-board-edit`: give each part its final position and rotation in one update. If you rotated a
   part, run its `sch_to_board.py` afterwards, because KiCad 10.0's API drops the 3D model of a rotated part.
3. After each block: DRC (`kicad-check`) for courtyards and clearances, and look at the board (`kicad-view`). Measure
   that each part that must be close is within about two body lengths of its pin.
4. Before moving a critical part away from its pin to solve a conflict, try at least two alternatives: another
   rotation, swapping two parts, or moving whichever neighbour can tolerate more distance. Report anything you could
   not satisfy, and why.
5. Put the decisions in the project's design notes: where each block sits and what drove it. The next change then
   starts from the reasons, not from the picture.
6. Routing comes next: `kicad-routing`.
