---
name: kicad-placement
description: "Decide where parts go on a KiCad 10 PCB: mechanical parts first, then the parts whose connections must be short (decoupling, regulator loops, crystals), with spacing checks for fine-pitch pins and rules for assembly and hand soldering. Use when planning, reviewing or redoing a layout's placement. Moves are made with kicad-board-edit."
---

# Where parts go

Routing can't fix a part in the wrong place. Placement controls:
- **loop area:** fast current through a big loop radiates, picks up noise and rings;
- **length on sensitive nodes:** high-impedance and clock nodes need short tracks;
- **heat;**
- **mechanical fit;**
- **manufacturability.**

If a rule below conflicts with one of these on a particular board, follow the effect and note why.

## Order

1. **Mechanical parts.** Place the outline, holes, connectors, switches, LEDs and anything else the enclosure fixes.
   Lock them.
2. **Blocks.** From the netlist (`kicad-view`), name each block and give it a region. Put blocks that share many nets
   next to each other. Keep noisy blocks away from sensitive ones.
3. **Large ICs.** Try all four rotations, and pick the one that points the pins toward what they connect to. Take pin
   positions from the board's pads, not from the symbol.
4. **Short-connection parts,** while the space around the pins is still free:
   1. the switching regulator's power loop;
   2. crystals and their load caps;
   3. decoupling caps;
   4. filters, terminations and ESD parts;
   5. bulk caps and pull-ups.
5. **The rest.** Leave lanes for routing.

Compute positions from pad coordinates. Placing by eye is often 0.3 mm off, which is half an 0201.

## By part type

- **Decoupling cap:**
  - Place it at its supply pin, supply pad toward the pin, with a ground via touching its ground pad.
  - Give one cap to each supply pin if there are enough caps. Otherwise follow the vendor's grouping.
  - Put the smallest value closest unless the vendor says otherwise. Bulk caps go behind it, on the same track.
- **Switching regulator:**
  - Make the datasheet's critical loop as small as possible. For a buck, that is input cap → high-side switch →
    low-side switch → input cap. For a boost, it is output cap → switch → diode.
  - Keep the switch node compact.
  - Put the feedback and compensation parts on the quiet side, away from the inductor.
- **Crystal:** place the load caps beside it and the crystal beside its pins, with equal path lengths. Route nothing
  between them or underneath.
- **High-impedance nodes** (op-amp inputs, references, feedback): a few mm long, no vias, away from noise. Put filters
  and dividers at the pin they serve. Long runs go on low-impedance outputs.
- **Protection and termination:**
  - ESD and TVS parts go at the connector, first on the net.
  - Series termination goes at the driver.
  - A ferrite between two domains goes between their caps.
- **RF:**
  - Place the series parts in schematic order, in a line from the pin to the port.
  - Shunt parts branch off at the nodes, with their grounds facing away from the line.
  - Follow the vendor's layout exactly.
- **Noisy versus quiet:**
  - Noisy: switch nodes, clocks, buses, drivers, external power.
  - Quiet: analog inputs, references, audio, RF.

  Keep their copper apart. Return currents must not pass under the quiet parts.
- **Heat:** spread out the dissipating parts, and keep references and crystals away from them. Leave room for the
  via field under an exposed pad.

Use only the parts in the schematic. If the vendor's reference design has a part the schematic lacks, report it.
Treat the datasheet's layout constraints as requirements. When the datasheet leaves a choice open, make it and say
that it's your inference.

## Fine-pitch pin rows

Two passives centred on neighbouring pins fit only if the sum of their courtyard widths is no more than twice the
pitch. KiCad's stock courtyard widths are:

| Size | Courtyard width |
|---|---|
| 0201 | 0.70 mm |
| 0402 | 0.92 mm |
| 0603 | 1.46 mm |

So two 0402s fit at 1.27 mm pitch, but not at 0.65 or 0.5 mm. When they don't fit:
- stagger one part outward;
- put one on the other side of the pin row;
- move the part that can tolerate distance.

Every pad needs room for a track to escape. A fine-pitch row needs clear space in front until its tracks fan out. When
a cap and an escaping track compete, the cap stays and the track goes around.

## Manufacturing

- **Courtyards:** no overlaps.
- **JLC assembly:** keep parts 2.5 mm from the edge, or add rails (`kicad-assembly-export`).
- **Board sides:** use one side. Ask before placing parts on the bottom.
- **Polarity:** orient polarised parts and pin-1 marks consistently.
- **Test points and headers:** keep them reachable, with nothing tall beside them.
- **Hand soldering:**
  - leave at least 1 mm between pads of different blocks;
  - use 0805 or larger where possible;
  - use thermal reliefs on pads in pours.
- **Reference designators:** keep them visible after assembly, not under tall parts.

## Doing it

1. **Constraints.** Read each IC's layout section in its datasheet. Treat its constraints as requirements.
2. **Move parts** with `kicad-board-edit`. Set each part's final position and rotation in one update. If you rotated any
   part, run `sch_to_board.py` afterwards, because the 3D models drop.
3. **Check each block.** Run DRC (`kicad-check`), look at the result (`kicad-view`), and confirm that every
   close-coupled part is within about two body lengths of its pin.
4. **Conflicts.** Before you move a critical part away from its pin, try at least two alternatives:
   - another rotation;
   - swapping two parts;
   - moving a neighbour that can tolerate distance.

   Report anything left unsatisfied.
5. **Design notes.** Record where each block sits and why.
6. **Next step:** route with `kicad-routing`.
