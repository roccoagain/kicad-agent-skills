---
name: kicad-bringup
description: Write or update a board's bring-up and test plan (TEST_PLAN.md) from its KiCad schematic - visual inspection, unpowered resistance checks with expected readings computed from the netlist, first power with a current-limited supply and parts left out, then block-by-block functional tests - each step with what a wrong reading means, plus a log to fill in per board. Use when a board is about to be ordered or assembled, when the user asks how to test or bring up a board, or after a schematic change that moves a reading.
---

# Write a bring-up plan

The plan should catch an assembly fault before it destroys anything, and point to the faulty part when a reading is
wrong. Compute every expected number from the schematic and datasheets, and show the working so the number can be
recomputed after a change. Read the circuit (`kicad-view`: the PDF and the pin list) and the design notes first.

## TEST_PLAN.md layout

1. **Header:** the board, its revision, and the schematic the numbers come from. Run the stages in order and stop at
   the first failure.
2. **Circuit summary:** a table of blocks, giving the parts, what each block does, and where to probe it.
3. **Pinouts:** every pin the steps refer to, taken from the netlist.
4. **Equipment:**
   - a current-limited supply, a DMM and a scope;
   - a signal source and loads;
   - a magnifier, flux and wick.
5. **Stages 0–3:** one table per stage, with the columns `# | Measure / do | Expect | A wrong reading means`.
6. **Log:** one copy per board serial, recording the date, who tested, each reading, pass or fail, and notes.

## Stage 0: visual, unpowered

- **Joints:** inspect every joint under magnification. Name the fine-pitch parts and the pin pairs most likely to
  bridge.
- **Polarity:** check the orientation of each polarised part:
  - ICs by the pin-1 mark;
  - diodes and LEDs by the cathode;
  - electrolytic and tantalum capacitors by the + mark;
  - transistors by the marking.
- **Values:** spot-check parts that are easy to swap (same package, different value), and name them.
- **Mechanical:** connectors are seated and the board fits.

## Stage 1: unpowered resistance, no modules fitted

Check each rail to GND, and each pair of nets whose short would cause damage. Include adjacent fine-pitch pins that
carry two different supplies, or a supply and ground. For each pair:
- **Resistor-only paths:** give the number. Find it by following every resistor from each net's pins in the pin
  list.
- **Capacitors:** the reading starts low and climbs. Write "rises to > X" and "never below Y". X is well below the DC
  value. Y is the short limit, a few tens of Ω.
- **IC supply pins:** datasheets rarely give the resistance, so write "not a short (> 100 Ω)" instead of a number you
  can't support.
- **Diodes or clamps across the pair:** give both polarities, and say where the red lead goes.

Run the assembly-fault pass from `kicad-design-review` section 3. Each bridge, missing part, rotated part or
wrong-value part that would cause damage at first power must change at least one Stage 1 reading. Add steps until it
does.

## Stage 2: first power, current-limited

- **What's left out:** fit nothing optional yet. List exactly what stays out: modules, jumpers and loads.
- **Current limit:** add up the expected draw (quiescent currents, LEDs, divider currents) and add about 50 %. Show the
  sum. Keep the limit within what the input protection can take.
- **Order:**
  1. Ramp the supply slowly while watching the current.
  2. Measure each rail at its decoupling cap.
  3. Measure each reference and bias point.
  4. Check the ICs for heat.
- **Expected voltages:** include the regulator's accuracy and the resistor and supply tolerances. For example, a
  10k/10k divider of 1 % parts on 5.00 V gives 2.5 V ± 1 %, plus the supply's own tolerance.
- **Modules:** add them one at a time. Raise the limit by each module's draw, then repeat the rail checks.

## Stage 3: function, block by block

For each block, give the input to apply, the probe point, and the expected result with its working:
- **Gain stages:** a stated sine in; out = gain × in, with no clipping up to the largest input the notes promise.
- **Filters:** the level in the passband and at the corner frequency.
- **Digital links:** a loopback or a known command, and what the firmware or logic analyser should show.
- **Switches, enables, mutes:** the logic level in each state, and the pull-up or pull-down that sets it.
- **Protection (optional):** a gentle test, at a low current limit, of each misuse case that `kicad-design-review` says
  the board survives. Say what the test risks.

## Keeping it right

- **Recompute after changes.** After a schematic change, recompute every reading it touches. A plan that disagrees with
  the schematic is worse than none.
- **Names and probe points.** Use the schematic's part and net names. Choose probe points a tester can reach: test
  points, capacitor pads and connector pins.
- **Working.** Keep the working for each number in its row, or in a note under the table.
