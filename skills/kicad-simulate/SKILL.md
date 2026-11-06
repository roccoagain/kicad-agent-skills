---
name: kicad-simulate
description: Simulate part of a KiCad 10 schematic with ngspice from the command line - export the SPICE netlist with kicad-cli, replace parts that have no model with sources and vendor models, run operating point, AC (gain, -3 dB frequency, phase) and transient (peaks, clipping, start-up) analyses in batch, and read the numbers back. Covers SPICE's unit traps (M is milli), mapping a vendor .subckt's pin order, and when a hand calculation is enough. Use when a design decision depends on a frequency response, a transient, headroom or a power figure that is hard to work out by hand, or to back up a kicad-design-review finding.
---

# Simulate a circuit

Simulation answers specific questions: what's the -3 dB point of this filter, does this stage clip at the largest
input, how much current flows at start-up. Ask the question first, then simulate only the circuit it needs. A
single RC or a divider is quicker by hand, so show the formula instead. Results are only as good as the models:
state which models were used.

## ngspice

KiCad bundles only the ngspice library, not the command-line program. Install it:
- macOS: `brew install ngspice`
- Linux: `apt install ngspice`
- Windows: the zip from ngspice.sourceforge.io

Check with `ngspice --version` (tested with ngspice 47). Everything runs in batch: `ngspice -b deck.cir`.

## 1. Get the circuit

```bash
"$K" sch export netlist --format spice -o <scratch>/board.cir board.kicad_sch
```

- Passives come out ready to use, e.g. `R2 +5V /VMID 10k`. KiCad converts values to SPICE form (`4k7` → `4.7k`,
  `1M` → `1Meg`).
- Node names are KiCad's net names (`/VMID`, `+5V`). `GND` is treated as ground (node 0) by ngspice.
- Parts without a SPICE model come out as placeholders such as `U1 __U1` and `J1 __J1`. Replace or delete every one.
- Usually you want one stage, not the whole board. Copy the lines for that stage into a new deck (the netlist and
  `kicad-view`'s pin list say which parts are on which nets) and drive its inputs with sources.

## 2. Write the deck

```
* <what this answers>
V1 in 0 DC 0 AC 1 SIN(0 0.1 1k)          ; source at the stage input: AC 1 for frequency response, SIN for transient
VCC vcc 0 5
X1 in fb out vcc 0 OPAMP_MODEL           ; pins in the ORDER of the model's .subckt line
R1 out fb 10k
R2 fb 0 1k
RL out 0 10k                             ; the real load: an input impedance, a headphone, a cable
.include /abs/path/vendor_model.lib      ; or the model text pasted in
.control
ac dec 50 10 10Meg
meas ac gain_lf find vdb(out) at=100
let target = gain_lf - 3
meas ac f3db when vdb(out)=$&target fall=1
wrdata <scratch>/ac.txt vdb(out)
tran 10u 3m
meas tran vpk max v(out) from=1m to=3m
.endc
.end
```

(Strip the `;` notes, or keep them: ngspice treats `;` as an end-of-line comment.)

- **Units:**
  - SPICE ignores letters after a scale factor, and `M` is **milli**. In a deck you write yourself, use `1Meg` for
    1 MΩ, and `4.7k`, never `4k7`: ngspice reads `4k7` as 4 kΩ and `1M` as 1 mΩ, with no warning.
  - Scale factors are `f p n u m k Meg G T`.
- **Vendor models:** take them from the part maker's site, the TI/ADI/Microchip pages for each part. The `.subckt`
  line lists the model's pins in its own order, often with a comment naming them. Map each to the right node.
  This is the most common simulation mistake.
- **A model that won't load:** some vendor models are PSpice-only. Run ngspice in PSpice compatibility mode by
  adding `set ngbehavior=ps` to `.spiceinit` in the working folder (or `~/.spiceinit`).
- **Ideal stand-ins**, when no model exists or the question doesn't need one:
  - a voltage-controlled source with a single pole for an op-amp (gain × bandwidth from the datasheet);
  - a diode model with `IS`, `N` and `RS` fitted to the datasheet's forward curve.

  Say that it's an idealisation.
- **Wrong-terminal and fault cases** (from `kicad-design-review`): add the fault source (e.g. a 12 V source on a
  signal input) and read the current through each protection part with `i(Vx)`. Put a 0 V source in series to
  measure a branch current.

## 3. Run and read

```bash
cd <scratch> && ngspice -b deck.cir 2>&1 | grep -v '^$'
```

- `meas` lines print `name = value`. If one prints "out of interval", the condition never happened in the sweep:
  widen the sweep, or check the circuit. A gain that never falls usually means a model or unit mistake.
- `print v(node)` after `op` gives DC voltages. `i(V1)` is the current into the source's + terminal (negative when
  it delivers current).
- `wrdata file vec` writes columns of numbers. It writes from the current plot, so put it after the analysis it
  belongs to, before the next one (or `setplot ac1` first).
- Sanity-check every result against a hand estimate: the low-frequency gain against the resistor ratio, the -3 dB
  point against GBW ÷ gain or 1/(2πRC). A simulation that disagrees with the estimate is wrong until explained.

## Reporting

Give the question, the circuit simulated (which parts, which models, what was idealised), the numbers with their
conditions (supply, load, input level, temperature 27 °C unless set), and the hand estimate beside them. Keep the
deck in `<scratch>`. If the project wants it kept, put it in a `sim/` folder with a line in the design notes
saying what it shows.
