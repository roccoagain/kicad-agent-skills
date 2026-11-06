---
name: kicad-schematic
description: Change a KiCad 10 schematic (.kicad_sch) safely as text and keep it readable - values and part fields (MPN, LCSC and distributor numbers, voltage, dielectric), new symbols (copying and flattening library symbols, native pin stacks, pin coordinates under rotation and mirroring), wiring, labels, power flags, annotation and hierarchical sheets, then subcircuit blocks, small passives, power-symbol conventions and zoomed visual checks - verified against KiCad's own netlist and ERC, then carried to the board and the project's documents. Use before and after any schematic change, when drawing a new schematic, or when the user asks to change a part, value or connection.
---

# Change a schematic

The user doesn't open KiCad, so you edit the `.kicad_sch` file, and KiCad's own tools check the result. Look before
and after with the `kicad-view` skill. Confirm connections with the netlist, not the picture.

## Before

- The schematic must not be open in KiCad's schematic editor, or its next save would overwrite yours. An open sheet
  has `~<name>.kicad_sch.lck` beside it; if that exists, ask the user to close it. (KiCad 10.0's API edits boards,
  not schematics, so the file is the only way in.)
- Start from a clean git tree, so the change is its own diff. Only one session edits a schematic at a time:
  `.kicad_sch` files merge badly.
- Save the pin list (`kicad-view` skill) for the parts you'll touch, to compare with afterwards.
- Write any generator or edit script in `<scratch>`, never in the project, and don't commit it.

## Field and value changes (safe as text edits)

Each placed symbol is a top-level `(symbol (lib_id ...) (at ...) ... (property "Reference" "C2" ...) (property
"Value" ...) ...)` block.
- Find it by its Reference property and change properties inside that block only.
- A new field is another `(property "Name" "value" (at x y 0) (hide yes) (effects (font (size 1.27 1.27))))`.
- Keep the project's field set consistent (e.g. MPN, Manufacturer, distributor part number, LCSC for JLC assembly,
  Datasheet on every part).
- Keep any per-part order or BOM file in step: the schematic is the source, so never edit the order alone.
- `(dnp yes)`, `(in_bom no)` and `(in_pos_files no)` on the symbol are DNP, "exclude from BOM" and "exclude from
  position files".

## New symbols

A placed symbol needs four things in the file:

1. **Its library definition in `(lib_symbols ...)`**, named `"Library:Name"`.
   - Copy it from the library's `.kicad_sym`: the stock ones are in
     `/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols/` on macOS (`/usr/share/kicad/symbols` on
     Linux), and project ones are listed in `sym-lib-table`.
   - Rename only the top-level name. The unit sub-symbols keep the bare name: `(symbol "R_0_1" ...)`.
   - **Derived symbols must be flattened.** About 12,000 stock symbols say `(extends "Parent")` and hold only
     properties. Copied as they are, they load with no pins: ERC reports dangling labels, unconnected pins and a
     library mismatch. To flatten one:
     1. Take the parent's block.
     2. Replace its properties with the child's.
     3. Name it `"Library:Child"`.
     4. Rename the parent's unit sub-symbols `"Parent_1_1"` → `"Child_1_1"`.
     5. Drop the `extends`.

     Done this way, ERC reports no `lib_symbol_mismatch`.
2. **The placed block:**
   - `(lib_id "Library:Name")`, `(at x y rot)`, optional `(mirror x)` or `(mirror y)`, `(unit n)`;
   - the flags `(exclude_from_sim no) (in_bom yes) (on_board yes) (dnp no)`;
   - a fresh `(uuid ...)`;
   - the Reference, Value, Footprint and Datasheet properties plus the project's own fields;
   - one `(pin "n" (uuid ...))` per pin of that unit. A KiCad 10 native pin stack (one library pin numbered
     `"[20,21]"` or `"[1-4]"`) gets one entry with that same bracketed number. The netlist then lists each pin
     separately.
3. **Its instance:**
   `(instances (project "<project name>" (path "/<root sheet uuid>" (reference "R12") (unit 1))))`. The project
   name is the `.kicad_pro` file's stem. The root sheet's uuid is the `(uuid ...)` near the top of the root
   `.kicad_sch`. On a sub-sheet, the path is `"/<root uuid>/<sheet uuid>"`, where the sheet uuid is that of the
   `(sheet ...)` block placing it.
4. **A unique reference.** `kicad-cli` can't annotate. Take the next free number for the prefix from the netlist or
   a grep of `(reference "R`. Power and flag symbols are references too (`#PWR012`, `#FLG03`) and must also be
   unique.

Every UUID is new: `python3 -c 'import uuid; print(uuid.uuid4())'`.

### Where a pin ends up

A library pin at `(px, py)` (library y points up) on a symbol at `(X, Y)` with rotation `r` (counter-clockwise on
screen) lands at `(X + dx, Y + dy)`:
1. Flip y: `dx = px`, `dy = -py`.
2. Rotate: `dx, dy = dx·cos r + dy·sin r, −dx·sin r + dy·cos r`. For r = 90 that's `(dy, −dx)`; for 180,
   `(−dx, −dy)`.
3. Mirror after rotating: `(mirror y)` negates `dx`, and `(mirror x)` negates `dy`.

The pin's `(at px py angle)` in the library is its connection end, the one wires attach to. This was checked with
ERC and the netlist for every rotation and mirror on an asymmetric op-amp. Mirroring before rotating puts every pin
in the wrong place once the part is rotated.

## Wiring

- Wires connect end to end, or to a pin end. Keep everything on KiCad's 1.27 mm (50 mil) grid.
- A wire end landing on the middle of another wire connects only with a `(junction (at x y) (diameter 0)
  (color 0 0 0 0) (uuid ...))` at that point. Without one, the netlist keeps them apart and ERC reports an
  unconnected wire end. (The editor adds junctions by itself. Text edits don't.)
- `(label "NAME" (at x y 0) ...)` connects by exact name within its sheet. Its anchor can sit on a wire end, on
  the middle of a wire, or straight on a pin end (no wire needed).
- `(global_label ...)` connects across sheets. Power symbols (`power:GND`, `power:+5V`) are global labels too, and
  their own pin is at their origin, so placing one on a pin end connects it.
- Unused pins get `(no_connect (at x y) (uuid ...))` on the pin end. Otherwise ERC reports them.
- **PWR_FLAG:** a power net fed only from a connector, regulator output or similar (no `power_out` pin) makes ERC
  report "input power pin not driven". Put a `power:PWR_FLAG` on that net once, rather than silencing ERC.
- Prefer labels for long connections and wires for local ones (a decoupling cap to its pin). GND symbols point down,
  supplies up. Put text where it doesn't overlap wires or other labels. Follow the conventions already on the
  sheet.

## Hierarchical sheets

- In the parent, a sub-sheet is a `(sheet (at x y) (size w h) ... (uuid ...) (property "Sheetname" "Input" ...)
  (property "Sheetfile" "input.kicad_sch" ...) (pin "IN" input (at x y 180) (uuid ...) ...) (instances (project
  "<name>" (path "/<root uuid>" (page "2")))))` block.
- Each sheet pin matches a `(hierarchical_label "IN" (shape input) ...)` in the sub-sheet by name.
- The sub-sheet file has its own `(uuid ...)`, `(lib_symbols ...)` for the symbols it uses, and no
  `sheet_instances`. Its symbols' instance paths are `"/<root uuid>/<sheet uuid>"`.
- Local labels on a sub-sheet are prefixed with its path in net names (`/Input/IN`).
- Run ERC on the root file: it loads the whole hierarchy.

## Readable, not just correct

People read a schematic: the reviewer, whoever debugs the board, you in a month. A correct netlist drawn as a tangle
hides mistakes, so the drawing is part of the work.

**Look at what you drew.** A whole sheet at page size is too small to see overlapping text. Plot the PDF, then rasterise
only the region you changed, at a resolution high enough to read 1.27 mm text. Convert schematic millimetres (origin at
the sheet's top-left corner, y down) to pixels with `mm / 25.4 * dpi`:

```bash
DPI=200
mm() { python3 -c "print(round($1 / 25.4 * $DPI))"; }
"$K" sch export pdf -o <scratch>/sch.pdf board.kicad_sch
pdftoppm -png -r $DPI -singlefile -x $(mm 320) -y $(mm 30) -W $(mm 80) -H $(mm 60) <scratch>/sch.pdf <scratch>/zoom
```

Add `-f N -l N` for page N. Fix what you see, plot again, repeat. Before calling a sheet finished, sweep it once more
for text over wires or pins, wires that cross or run long, labels turned the wrong way, and gaps that leave one area
crowded and another empty.

**Layout**
- Group each subcircuit (a supply, an IC and its passives, an input stage) inside a dashed rectangle with a bold title:
  - `(rectangle (start x1 y1) (end x2 y2) (stroke (width 0.254) (type dash)) (fill (type none)) (uuid ...))`
  - `(text "POWER INPUT" (exclude_from_sim no) (at x y 0) (effects (font (size 2 2) (thickness 0.4) (bold yes))
    (justify left bottom)) (uuid ...))`
- Let signals run left to right, inputs at the left edge and outputs at the right.
- Keep the design on one sheet if it stays legible, even on A3 or A2. Use sub-sheets for blocks that repeat, or when a
  single sheet would be too crowded to read.

**Symbols and wiring**
- Choose the compact passives (`Device:R_Small`, `C_Small`, `L_Small`, and `R_Small_US` for US-style) and draw them
  where they do their job.
- Connect decoupling caps, pull-ups and filter parts to their pins with short wires. Reserve net labels for long runs
  between blocks.
- Several decoupling caps on one rail share a single supply symbol and a single ground symbol.
- Ground symbols point down; positive rails point up; negative rails point down.
- Put `PWR_FLAG` at the point where power enters the design.
- Place each test point beside the net it probes.
- Write values with units (`100nF`, `4.7uH`, `10k`), in whatever form the project already uses.
- Name the two nets of a differential pair with a common stem and a `+`/`-` or `P`/`N` suffix, so KiCad can pair them.
- Leave label and field text at the default 1.27 mm, and keep it from overlapping anything.
- Colour a wire only when it helps (for example one bus or one supply domain), with
  `(stroke (width 0) (type default) (color 200 0 0 1))`.

**Symbols you redraw.** Reordering an IC symbol's pins for a cleaner drawing is fine in the project's own library copy,
never in KiCad's. Afterwards prove the symbol still has the same pin numbers, names and electrical types
(`kicad-library`, step 4) and that the netlist is unchanged.

**Reference designs.** Compare each IC's block with the datasheet's application circuit. List every departure, and every
choice the documents left open, in your report as a liberty taken, with the reason.

## Anything you can't place confidently

A dense rework of a sheet, or a symbol whose geometry you can't work out: describe it exactly, with pins and nets
from the netlist, and ask how the user wants it done.

## After

1. **ERC** (`kicad-check` skill): no new errors. Unconnected pins and dangling wires or labels show here.
2. **The netlist** for every touched part: each pin on the net you intended, and nothing else changed. Diff the pin
   lists from before and after (`kicad-view`).
3. **Look** at the area (`kicad-view`).
4. **Carry it to the board** with `sch_to_board.py` (`kicad-board-edit` skill): new parts, values, fields and DNP
   flags. Pad-net and footprint changes need re-routing. Then the board's DRC with `--schematic-parity`
   (`kicad-check`) must show no parity issues.
5. **Update the project's documents:**
   - design notes, when the design or its reasons change;
   - the test plan, when a reading changes (`kicad-bringup`);
   - the parts order or BOM, when a part number changes.
