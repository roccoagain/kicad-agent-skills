---
name: kicad-bringup
description: Write or update a board's bring-up and test plan (TEST_PLAN.md) from its KiCad schematic - visual inspection, unpowered resistance checks with expected readings computed from the netlist, first power with a current-limited supply and parts left out, then block-by-block functional tests - each step with what a wrong reading means, plus a log to fill in per board. Use when a board is about to be ordered or assembled, when the user asks how to test or bring up a board, or after a schematic change that moves a reading.
---

# Write a bring-up plan

A good plan finds an assembly fault before it destroys anything, and points at the faulty part when a reading is
wrong. Every expected number comes from the schematic and the datasheets, with its working shown, so it can be
recomputed when the design changes. Read the circuit with `kicad-view` (the PDF and the pin list) and the design
notes first.

## Structure (TEST_PLAN.md beside the board, or where the project keeps it)

1. **Header:** board, revision, the schematic file it was computed from, and how to use the plan. Work through the
   stages in order, and stop at the first failure.
2. **Circuit summary:** a table of blocks: parts, what they do, where to probe. A tester reads this first.
3. **Pinouts used below:** each IC, transistor and connector pin the steps refer to, from the netlist (not from
   memory).
4. **Equipment:**
   - current-limited bench supply, DMM, scope;
   - signal source and loads;
   - cables, magnifier, flux, wick.
5. **Stages 0–3** (below), each a table: `# | Measure / do | Expect | A wrong reading means`.
6. **Log:** one copy per board serial: date, who, each step's reading, pass/fail, notes.

## Stage 0: visual (unpowered)

- Every joint under magnification. Name the fine-pitch parts and the pin pairs most likely to bridge.
- Orientation of every polarised part: ICs (pin 1 mark), diodes and LEDs (cathode), electrolytics and tantalums
  (+), transistors (marking).
- Values: spot-check the parts that are easy to swap (same package, different value), naming them.
- Connectors seated, mechanical fit, labels legible.

## Stage 1: unpowered resistance (DMM, no modules fitted)

For each supply rail to GND, and for any pair of nets whose short would do damage, compute what the meter should
read:
- **The DC paths between the two nets:** resistors in series and parallel. Take the pins on each net from the pin
  list, and follow every resistor to where it goes.
- **Capacitors:** the reading starts low and climbs while they charge. Write "rises to > X" with X well below the
  computed DC value, and "never below Y" for the short limit (a few tens of Ω).
- **Semiconductors:** an IC's supply pins often read a few kΩ to a few hundred kΩ, or show a diode drop in diode
  mode. Datasheets rarely say, so write "not a short (> 100 Ω)" rather than a number you can't back up. Put a
  number in only for resistor-only paths.
- **Both polarities** where diodes or protection parts sit across the pair. The reading differs, and the plan should
  say which way the red lead goes.
- **Adjacent pins of fine-pitch parts** that carry different supplies or a supply and ground: these are the bridges
  that destroy parts at power-on.

Run the assembly-fault pass from `kicad-design-review` (section 3): every likely bridge, missing, rotated or
wrong-value part that does damage at first power must change at least one Stage 1 reading. Add steps until it
does.

## Stage 2: first power, current-limited

- Fit nothing optional yet: modules out of their sockets, jumpers open, loads disconnected. Say exactly what's left
  out.
- **The current limit:** the expected supply current (sum of the quiescent currents from the datasheets, LEDs at
  their computed current, divider currents) plus about 50 %, and never more than the input protection can take.
  Show the sum.
- **The order:**
  1. Ramp the supply slowly, watching the current.
  2. Measure each rail at its decoupling capacitor.
  3. Measure each reference and bias point.
  4. Feel or thermally image the ICs.
- **Expected voltages:** from the regulator datasheet's output accuracy, divider ratios with resistor tolerances
  (e.g. 2.5 V ± 1 % for a 10k/10k divider from 5.00 V with 1 % parts, plus the supply's tolerance), and any load.
- **Then add the modules** one at a time, with the current limit raised by each one's expected draw, and repeat
  the rail checks.

## Stage 3: function, block by block

For each block in the circuit summary: an input to apply, where to measure, and the expected result with its
working. Examples:
- **Gain stages:** a sine at a stated amplitude and frequency in; amplitude out = gain × in, with no clipping up
  to the largest input the design notes promise.
- **Filters:** the level at the passband and at the corner frequency.
- **Digital interfaces:** a loopback or a known command, and what the firmware or logic analyser should show.
- **Detect switches, enables, mutes:** the logic level in each state, with the pull-up/down that sets it.
- **Protection:** for the misuse cases `kicad-design-review` says the board survives (a supply on the wrong
  terminal, a hot-plug), a gentle test with the current limit set low, if the user wants it tested at all. Say
  it's optional and what it risks.

## Keeping it right

- After any schematic change, recompute the readings it touches (`kicad-schematic` step 5). A plan that disagrees
  with the schematic is worse than none.
- Name parts and nets exactly as the schematic does, and prefer probe points the tester can reach: test points,
  capacitor pads, connector pins. Name a part on the same net when a pin is covered.
- Record the computation for each number (a short formula in the row, or a note under the table), so a later
  change can be checked without redoing everything.
