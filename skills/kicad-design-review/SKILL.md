---
name: kicad-design-review
description: Review a KiCad schematic's electrical design by hand against datasheets - what every connector can see (normal use, power states, misuse such as a wire on the wrong terminal), absolute maximum ratings, protection and injection current, resistor power, capacitor voltage and derating, dielectrics in signal paths, ESD on exposed pins, floating inputs, interfaces between boards, and whether the bring-up test plan catches likely assembly faults. Use after a schematic change, when adding a part, when the user asks whether an input can take a voltage or whether a design survives a fault, and before ordering a board.
---

# Review a circuit by hand

This is a structured review, done by reading the schematic (`kicad-view` skill: the PDF and the netlist) and each
part's datasheet. When a case turns on a frequency response or a transient that's hard to work out by hand, back it
with a simulation (`kicad-simulate`) and give both numbers. The review's value comes from being systematic and from
stating every number with its source. Write the result as a table the user can check, not as a verdict.

## 1. State the environment first

Before judging anything, write down (and confirm with the user where it's a guess):
- **Rails:** each supply's range while on (e.g. 5 V ± 5 %), and what's at 0 V in each power state.
- **Power states:** on; off with signals still connected (a guitar or phone playing into an unpowered board); powered
  from another source (a module on USB with the main supply off); bench bring-up with parts missing; supply reversed.
- **Every connector pin:** what normally drives or loads it (level, source impedance, frequency range), and what can
  happen by mistake: a wire on the wrong screw terminal, a supply shorted to a signal, a hot-plugged jack, ESD on
  anything a person touches, a louder source than intended. These misuse cases must not damage anything. They
  may stop the board working.

## 2. Check each case

For each power state and each misuse (one at a time, everything else normal), work out the worst-case voltage at every
IC pin, using resistor and part tolerances at their worst corner. A coupling cap passes a sine unchanged, but an
arbitrary waveform with a step can double the swing behind it. Then check:

| Check | Pass when |
|---|---|
| Absolute maximum, every IC pin | Inside the datasheet's absolute maximum, including relative to its own rails when they're at 0 V |
| Protection diodes | Past the rails, the current through the series resistance stays under the datasheet's injection rating (no rating given: say so, it's a risk) |
| Operating range | Inputs inside the common-mode/input range while powered; outputs not clipping at the levels the design assumes |
| Resistor power | V²/R at the worst case, under the rating (0805 ≈ 0.125 W, 1206 ≈ 0.25 W unless the datasheet says) |
| Capacitor voltage | Under the rating; electrolytics never reverse-biased by more than ≈ 0.5 V |
| Ceramic derating | X5R/X7R/Y5V at under ~50 % of rated voltage, or check the maker's DC-bias curve: they lose most of their capacitance near rating |
| Dielectric in signal paths | Audio/precision/filter caps C0G or film: X5R/X7R capacitance moves with voltage (distortion) and they're piezoelectric (microphonics), worst in series with a high-impedance node |
| MOSFETs and switches | Vgs and Vds inside ratings, channel current under the limit, gate never floating |
| Output loads | Each driver's load impedance at least the datasheet's minimum, current under its limit, including a shorted connector |
| ESD | Every exposed pin (jacks, cable connectors) has a TVS/ESD diode at the connector, rated for the signal's swing |
| Floating inputs | Every powered input has a DC path to a defined level in every state (a pull-up/down, a bias resistor) |
| Interfaces | Each signal between boards is inside the range the other board's notes promise, from a source impedance it accepts |

Mark each number with its source (datasheet and section, or "assumed: reason"). An assumed value that decides the
outcome is itself a finding.

## 3. Test plan and assembly faults

If the project has a bring-up test plan (resistance checks unpowered, then voltages powered with parts missing;
`kicad-bringup` writes one if it doesn't):
- Recompute each expected reading from the schematic. A reading that no longer matches is a finding: propose the
  corrected line.
- For likely assembly faults (each solder bridge between adjacent pins of fine-pitch parts and connectors, each part
  missing, rotated or the wrong value, each supply shorted to its neighbour), ask whether it damages anything at first
  power, and whether a reading in the plan would catch it before power is applied. Propose readings for the damaging
  faults the plan misses.

## 4. Report

- Findings first, worst first: what happens physically, in which case, the numbers and their sources, and a fix (a
  series resistor, a clamp, a different part, a firmware rule) or "accept, because..." for the user to decide.
- Then the table of checks that passed, closest to their limits first, so the user can see the margins.
- Decisions the user accepts go into the project's design notes, with the reason. Don't record an acceptance on the
  user's behalf.
- When a number in the design notes turns out wrong, say so. Change the notes only if the user agrees.
