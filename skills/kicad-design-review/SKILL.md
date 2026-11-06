---
name: kicad-design-review
description: Review a KiCad schematic's electrical design by hand against datasheets - what every connector can see (normal use, power states, misuse such as a wire on the wrong terminal), absolute maximum ratings, protection and injection current, resistor power, capacitor voltage and derating, dielectrics in signal paths, ESD on exposed pins, floating inputs, interfaces between boards, and whether the bring-up test plan catches likely assembly faults. Use after a schematic change, when adding a part, when the user asks whether an input can take a voltage or whether a design survives a fault, and before ordering a board.
---

# Review a circuit by hand

Read the schematic and netlist (`kicad-view`) and each part's datasheet. Back anything that depends on a frequency
response or transient with `kicad-simulate`. Give every number with its source. The output is a table the user can
check, not a verdict.

## 1. State the environment

Write these down, and confirm any guesses with the user:
- **Rails:** the range of each rail while on (e.g. 5 V ± 5 %).
- **Power states:**
  - on;
  - off with signals still connected;
  - partly powered from another source (e.g. a module on USB with the main supply off);
  - bench bring-up with parts missing;
  - supply reversed.
- **Each connector pin:** what normally drives or loads it (level, source impedance, frequency), and what can happen by
  mistake:
  - a wire on the wrong terminal;
  - a short to a supply;
  - a hot-plug;
  - ESD from a touch;
  - a louder source than intended.

  Misuse may stop the board working, but it must not damage anything.

## 2. Check each case

Take one power state or one misuse at a time, with everything else normal. Find the worst-case voltage at every IC
pin, with tolerances at their worst corner. A coupling cap passes a sine unchanged, but a step can double the swing
behind it.

| Check | Pass when |
|---|---|
| Absolute max, every IC pin | Inside the rating, including relative to its own rails when they're at 0 V |
| Clamp diodes | Current through the series resistance stays under the injection rating. If the datasheet gives no rating, report that as a risk |
| Operating range | Inputs stay inside the common-mode range, and outputs don't clip at the levels the design assumes |
| Resistor power | V²/R at worst case, under the rating (0805 ≈ 0.125 W, 1206 ≈ 0.25 W unless stated) |
| Capacitor voltage | Under the rating. Electrolytics are never reverse-biased by more than ≈ 0.5 V |
| Ceramic DC bias | X5R/X7R run at no more than ~50 % of rated voltage, or the maker's bias curve shows enough capacitance |
| Signal-path dielectric | C0G or film in audio, precision and filter paths. Class-2 dielectrics distort and are microphonic |
| MOSFETs, switches | Vgs and Vds inside ratings, current under the limit, and the gate never floats |
| Output loads | At least the minimum load impedance, and current under the limit, including a shorted connector |
| ESD | Every exposed pin has a TVS or ESD diode at the connector, rated for the signal's swing |
| Floating inputs | Every input has a DC path to a defined level in every power state |
| Board interfaces | Each signal stays within what the other board's notes accept |

If an assumed value decides a pass or fail, report the assumption itself as a finding.

## 3. Test plan and assembly faults

If the project has a bring-up plan (`kicad-bringup`):
- Recompute each expected reading from the schematic, and propose a correction for any that changed.
- Go through the likely assembly faults:
  - bridges between adjacent pins of fine-pitch parts and connectors;
  - a part missing, rotated, or the wrong value;
  - a rail shorted to its neighbour.

  For each fault, does it cause damage at first power, and would an unpowered reading in the plan catch it first? Propose readings for the damaging faults the plan misses.

## 4. Report

- **Findings, worst first.** For each: what happens physically, in which case, the numbers and their sources, and a fix
  (or "accept, because ...") for the user to decide.
- **Passed checks**, closest to their limits first, so the user can see the margins.
- **Design notes.** Record only decisions the user accepted, with the reason. If a number in the notes is wrong, say so,
  and edit the notes only with the user's agreement.
