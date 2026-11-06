---
name: kicad-schematic
description: Change a KiCad 10 schematic (.kicad_sch) safely as text and keep it readable - values and part fields (MPN, LCSC and distributor numbers, voltage, dielectric), new symbols (copying and flattening library symbols, native pin stacks, pin coordinates under rotation and mirroring), wiring, labels, power flags, annotation and hierarchical sheets, then subcircuit blocks, small passives, power-symbol conventions and zoomed visual checks - verified against KiCad's own netlist and ERC, then carried to the board and the project's documents. Use before and after any schematic change, when drawing a new schematic, or when the user asks to change a part, value or connection.
---

# Change a schematic

KiCad 10.0's API can't edit schematics, so edit the `.kicad_sch` file as text. Check the result with KiCad's netlist
and ERC, not by looking at a picture.

## Before

- **Editor closed.** If `~<name>.kicad_sch.lck` exists, the sheet is open in KiCad, and its next save will overwrite
  your edit. Ask the user to close it.
- **Clean git tree.** Start from a clean tree, and let only one session edit a sheet at a time, because `.kicad_sch`
  files merge badly.
- **Pin list.** Save the pin list (`kicad-view`) for every part you'll touch, so you can compare it afterwards.
- **Scripts.** Keep edit scripts in `<scratch>` and never commit them.

## Fields and values

A placed symbol is a top-level block, `(symbol (lib_id ...) (at ...) ... (property "Reference" "C2" ...) ...)`. Find it
by its Reference, and edit only inside that block.

- **New field:** add `(property "Name" "value" (at x y 0) (hide yes) (effects (font (size 1.27 1.27))))`.
- **Field set:** keep it consistent across parts (MPN, Manufacturer, LCSC or distributor number, Datasheet).
- **Flags:** `(dnp yes)`, `(in_bom no)` and `(in_pos_files no)` mark a part as DNP, excluded from the BOM, and excluded
  from position files.

## New symbols

A placed symbol needs four things.

**1. A definition in `(lib_symbols ...)`, named `"Library:Name"`.**
- Copy it from the `.kicad_sym` file. Stock symbols are in `/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols/`
  on macOS and `/usr/share/kicad/symbols` on Linux. Project libraries are listed in `sym-lib-table`.
- Rename only the top-level symbol. Unit sub-symbols keep the bare name, e.g. `"R_0_1"`.
- Flatten symbols that `(extends "Parent")`. About 12,000 stock symbols do, and copied as-is they load with no pins.
  To flatten:
  1. Take the parent's block.
  2. Replace its properties with the child's.
  3. Name it `"Library:Child"`.
  4. Rename the unit sub-symbols from `Parent_1_1` to `Child_1_1`.
  5. Drop the `extends`.

**2. The placed block.** It contains:
- `(lib_id ...)`, `(at x y rot)`, an optional `(mirror x|y)`, and `(unit n)`;
- `(exclude_from_sim no) (in_bom yes) (on_board yes) (dnp no)`;
- a new `(uuid ...)`;
- the Reference, Value, Footprint and Datasheet properties, plus the project's own fields;
- one `(pin "n" (uuid ...))` for each pin of the unit. A KiCad 10 pin stack (`"[20,21]"`, `"[1-4]"`) gets one entry
  with that bracketed number.

**3. Its instance.** Add
`(instances (project "<.kicad_pro stem>" (path "/<root sheet uuid>" (reference "R12") (unit 1))))`.
- The root sheet's uuid is the one near the top of the root file.
- On a sub-sheet, the path is `"/<root uuid>/<sheet block uuid>"`.

**4. A unique reference.** `kicad-cli` can't annotate. Take the next free number from the netlist, or grep for
`(reference "R`. Power and flag symbols also need unique references (`#PWR012`, `#FLG03`).

Make every UUID new: `python3 -c 'import uuid; print(uuid.uuid4())'`.

### Pin position

A library pin's `(at px py angle)` is its connection end, where wires attach. Library y points up. For a symbol at
`(X, Y)` with rotation `r` (counter-clockwise on screen), the pin lands at `(X + dx, Y + dy)`:
1. Flip y: `dx = px`, `dy = -py`.
2. Rotate: `dx, dy = dx·cos r + dy·sin r, −dx·sin r + dy·cos r`. At 90° that gives `(dy, −dx)`; at 180°, `(−dx, −dy)`.
3. Mirror after rotating: `(mirror y)` negates `dx`, and `(mirror x)` negates `dy`.

Mirroring before rotating puts the pins in the wrong place.

## Wiring

- **Connections:** wires connect end to end, or to a pin end. Stay on the 1.27 mm grid.
- **Junctions:** a wire ending on the middle of another wire connects only through a junction at that point:
  `(junction (at x y) (diameter 0) (color 0 0 0 0) (uuid ...))`. The editor adds junctions automatically, but text
  edits don't.
- **Labels:** `(label "NAME" ...)` connects by name within one sheet. It can sit on a wire end, the middle of a wire,
  or directly on a pin end.
- **Global connections:** `(global_label ...)` connects across sheets. Power symbols act as global labels, with their
  pin at their origin.
- **Unused pins:** put a `(no_connect (at x y) (uuid ...))` on the pin end.
- **PWR_FLAG:** if a rail is fed only by a connector or a regulator output, ERC reports "input power pin not driven".
  Put one `power:PWR_FLAG` on that net instead of silencing ERC.

## Hierarchical sheets

- **Parent:** the parent places the sub-sheet with
  `(sheet (at ...) (size ...) (uuid ...) (property "Sheetname" ...) (property "Sheetfile" "input.kicad_sch")
  (pin "IN" input (at ...) (uuid ...)) (instances (project "<name>" (path "/<root uuid>" (page "2")))))`.
- **Sheet pins:** each pin matches a `(hierarchical_label "IN" ...)` in the sub-sheet.
- **Sub-sheet:** it has its own uuid and `lib_symbols`, and no `sheet_instances`.
- **Net names:** local labels in a sub-sheet get the sheet's path in their net name (`/Input/IN`).
- **ERC:** run it on the root file.

## Readable

**Look at it zoomed in.** Plot the sheet and rasterise only the area you changed. Schematic coordinates are mm from
the top-left, with y pointing down.

```bash
DPI=200; mm() { python3 -c "print(round($1 / 25.4 * $DPI))"; }
"$K" sch export pdf -o <scratch>/sch.pdf board.kicad_sch
pdftoppm -png -r $DPI -singlefile -x $(mm 320) -y $(mm 30) -W $(mm 80) -H $(mm 60) <scratch>/sch.pdf <scratch>/zoom
```

Add `-f N -l N` to pick page N. Fix overlapping text, wires that cross or run long, labels turned the wrong way, and
crowding. Repeat until the area is clean.

**Layout**
- Put each subcircuit in a dashed box with a bold title:
  - `(rectangle (start x1 y1) (end x2 y2) (stroke (width 0.254) (type dash)) (fill (type none)) (uuid ...))`
  - `(text "POWER INPUT" (exclude_from_sim no) (at x y 0) (effects (font (size 2 2) (thickness 0.4) (bold yes))
    (justify left bottom)) (uuid ...))`
- Let signals flow left to right.
- Use one sheet if it stays legible, even at A3 or A2. Use sub-sheets for repeated blocks.

**Symbols and wiring**
- Use small passive symbols (`R_Small`, `C_Small`, `L_Small`) and wire them directly to their pins. Use labels for
  long runs.
- Let a group of decoupling caps share one supply symbol and one ground symbol.
- Point ground symbols down and positive rails up. Place each `PWR_FLAG` where power enters, and each test point by its
  net.
- Give values units (`100nF`, `10k`), following the project's existing style.
- Name differential pairs with a `+`/`-` or `P`/`N` suffix.
- Keep text at 1.27 mm and never overlapping. Use colour only where it means something.

**Redrawn and reference circuits**
- **Redrawn symbols:** reordering an IC symbol's pins is allowed only in the project library's copy. Then prove that the
  pin numbers, names and types are unchanged (`kicad-library` step 4), and that the netlist is unchanged.
- **Reference designs:** compare each block with the datasheet's reference circuit. Report every departure, and every
  open choice you made, with your reasons.

If you can't place something confidently, describe it exactly (pins and nets from the netlist) and ask the user.

## After

1. **ERC** (`kicad-check`): no new errors.
2. **Netlist diff** (`kicad-view`): every touched pin is on the intended net, and nothing else changed.
3. **Look** at the changed area.
4. **Update the board:** run `sch_to_board.py` (`kicad-board-edit`). Changes to pad nets or footprints need
   re-routing. DRC with `--schematic-parity` must come back clean.
5. **Update the documents:**
   - the design notes, if the design or its reasons changed;
   - the test plan, if a reading changed (`kicad-bringup`);
   - the BOM or order, if a part number changed.
