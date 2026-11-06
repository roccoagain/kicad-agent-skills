---
name: kicad-schematic
description: "Edit or draw a KiCad 10 schematic with sch.py, a small Python library in this skill's folder: add symbols, wires, labels, power symbols and no-connects by pin, change values and fields, then check with ERC and carry the change to the board. Use for any schematic change, such as adding a part, connecting nets or changing a value, and when drawing a new schematic. To create a symbol, use kicad-library."
---

# Change a schematic

Make every change with `sch.py` (this skill's folder) from a short script in `<scratch>`. It needs only `python3`.
It handles the parts that go wrong by hand:
- copying and flattening library symbols;
- pin positions under rotation and mirroring;
- instances, references, UUIDs and string escaping;
- junctions;
- running ERC after every save.

It inserts new items and leaves the rest of the file byte for byte, so the diff shows only the change.

```python
import sys; sys.path.insert(0, "<skill dir>")              # this SKILL.md's folder
from sch import Schematic

s = Schematic("board.kicad_sch")                           # refuses if KiCad has the sheet open
s.add("Device:C_Small", "C?", (120.65, 50.8), value="100nF",            # "C?" = next free C; 1.27 mm grid
      footprint="Capacitor_SMD:C_0603_1608Metric", fields={"LCSC": "C14663", "Voltage": "50V"})
s.add("MCU_ST_STM32G0:STM32G030F6Px", "U2", (170.18, 82.55), footprint="Package_SO:TSSOP-20_4.4x6.5mm_P0.65mm")
s.power("C1", "1", "+3V3"); s.power("C1", "2", "GND")     # on the pin, pointing away from the part
s.power("U2", "4", "+3V3", stub=2.54)                      # after a 2.54 mm wire
s.label("U2", "9", "UART_TX")                              # stub + label, text reading away from the part
s.connect(("U2", "4"), ("C1", "1"))                        # wire with at most one bend (first="v" to go vertical first)
s.wire(("D1", "2"), (150, 124.46), ("R3", "1"))            # explicit corners; legs horizontal or vertical
s.nc("U2", "7")
s.set_field("R3", "Value", "1k")                           # existing or new symbol; new fields are hidden
s.remove("J2")                                             # a part plus its stubs, labels and no-connects
s.add("Connector:Conn_ARM_SWD_TagConnect_TC2030-NL", "J2", (196.85, 121.92),
      in_bom=False, in_pos=False)                          # footprint-only part: no BOM line, not placed
s.box(125, 25, 215, 140, "MCU")                            # dashed block outline with a bold title
s.text("Place C1 at U2 pin 4", 135, 50)                    # notes; "\n" for line breaks
s.save()                                                   # writes, adds junctions, prints ERC
```

To plan a placement:
- `python3 sch.py symbol Lib:Name` lists a library symbol's pins: number, name, type and offset.
- `python3 sch.py pins board.kicad_sch U2` lists where a placed symbol's pins land, and which way each points.
- `s.pin(ref, n)` returns `(x, y, out_dx, out_dy)` inside a script.

Coordinates are sheet mm, with y pointing down. Rotation is counter-clockwise, and `mirror="x"|"y"` is applied after
rotating.

## Before

- **Editor closed.** If the sheet is open in KiCad (`~<name>.kicad_sch.lck`), its next save overwrites your edit.
  `Schematic()` refuses to open it, so ask the user to close it.
- **Clean git tree.** Only one session should edit a sheet at a time: `.kicad_sch` files merge badly.
- **Pin lists.** For the parts you'll touch, save `view.py pins` (`kicad-view`) to compare afterwards.
- **Choose MCU pins and header order from the floor plan** (`kicad-placement`) before wiring them.

## Drawing it readably

People read schematics, so a correct netlist drawn as a tangle still hides mistakes. Look at every area you change
(`view.py sch ... --around U2,C3`), fix what's wrong, and look again.

- **Blocks:** one `box()` per subcircuit (power, an IC with its passives, a connector), with signals flowing left to
  right.
- **Sheets:** prefer one sheet you can read at once, even at A3. Use sub-sheets for repeated blocks.
- **Passives:** use the small symbols (`R_Small`, `C_Small`, `L_Small`, `LED_Small`). Wire decoupling caps, pull-ups
  and filters straight to their pins, and use labels for long runs between blocks. Note that `R_Small`/`C_Small`
  pin 1 is the **top** pin at rotation 0.
- **Power symbols:** a group of decoupling caps shares one supply symbol and one ground symbol. Ground points down and
  supplies point up. Put one `PWR_FLAG` where each supply enters (`s.power_at(x, y, "PWR_FLAG")` on its wire). A
  rail fed only by a connector or a regulator output needs one, or ERC reports "input power pin not driven".
- **Units:** values carry them (`100nF`, `10k`), in the project's existing style.
- **Text:** keep it at 1.27 mm, and never overlapping anything. Name differential pairs with `+`/`-` or `P`/`N`.
- **Reference designs:** compare each block with its datasheet's reference circuit. Report every departure, and every
  open choice you made, with its reason.
- **Field positions** come from the library symbol. If a field crowds something, pass `ref_at=` or `value_at=` to
  `add()`.

## Limits of sch.py

- **Multi-sheet designs:** it edits one sheet file at a time and writes root-sheet instance paths. For symbols on a
  sub-sheet, write the instance path `"/<root uuid>/<sheet uuid>"` yourself, or ask.
- **Moving or replacing a part:** use `remove(ref)`, then `add()` it again with its connections. `remove()` takes
  the stub wires, labels, power symbols and no-connects that hang off the part's pins. It stops at branches and at
  other parts' pins, so shared nets survive.
- **Not handled:** editing existing wires, labels and text. Make those as small text edits to the file, and
  confirm with ERC and the netlist.
- **Regenerating:** don't regenerate a whole sheet once a board exists. New symbol UUIDs break the board's links to
  its symbols (parity fails). Edit in place instead.

## After

1. **ERC** prints on every save: no new errors (`kicad-check` for the full run).
2. **Netlist:** check every touched pin is on the intended net and nothing else changed (`view.py pins`, diff with
   before).
3. **Look** at the area (`view.py sch --around`).
4. **Update the board:** run `board.py sync` (`kicad-board-edit`). It adds parts, copies values and fields, and moves
   unrouted pads to new nets. A footprint change, or a routed pad on a changed net, needs re-routing.
5. **Update the documents:** design notes, the test plan (`kicad-bringup`) if a reading changed, and the BOM/order if a
   part number changed.
