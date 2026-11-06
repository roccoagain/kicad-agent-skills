---
name: kicad-library
description: Make and check KiCad 10 symbols and footprints for parts that aren't in KiCad's libraries - stock footprints, the datasheet's land pattern, or IPC-7351 pads computed with the script in this skill's folder; pin 1, courtyard, fab and silk layers, 3D models; symbols with native pin stacks and alternate pin functions; pad-to-pin agreement; project library tables - validated with kicad-cli (fp/sym upgrade as a parse check, SVG renders) and DRC. Use when a part needs a new or modified symbol or footprint, when a library footprint is suspected wrong, or when setting up a project's own libraries.
---

# Symbols and footprints

`K` is `kicad-cli` (see `kicad-view`). Footprint mistakes are the most common reason a first board doesn't work:
a mirrored pinout, a wrong pitch, pin 1 in the wrong corner. Every new footprint gets checked against the datasheet
by number, never by eye alone.

## Where things live

- **Stock libraries:**
  - macOS: `/Applications/KiCad/KiCad.app/Contents/SharedSupport/{symbols,footprints,3dmodels}`
  - Linux: `/usr/share/kicad/...`

  Search those first: `ls <footprints>/Package_SO.pretty | grep -i tssop`, or
  `grep -l 'symbol "TPS6' <symbols>/*.kicad_sym`.
- **Project libraries:** next to the project, e.g. `<project>.pretty/` (one `.kicad_mod` file per footprint) and
  `<project>.kicad_sym` (all symbols in one file). They are listed in the project's `fp-lib-table` and
  `sym-lib-table` with `${KIPRJMOD}` paths (format in `kicad-new-project`).
- **KiCad reads a project's library tables only when the folder has a `.kicad_pro`.** Without one, ERC reports
  "the current configuration does not include the symbol library".
- **Never edit KiCad's stock libraries.** Copy a part into the project library and change the copy.

## Footprints

In order of preference:
1. **A stock footprint** that matches the datasheet's land pattern. KiCad's stock library covers the common
   packages (chip passives, SOIC, SSOP, TSSOP, QFP, QFN, DFN, SOT, TO...) at many sizes.
2. **The closest stock footprint, edited:** same package family, then change what differs.
3. **Written by hand,** for connectors, modules, switches and other odd parts.

Whichever route you take, take the pad sizes from the datasheet's **recommended land pattern** (often called
"recommended footprint" or "PCB layout"), not from the package drawing. Only when the datasheet gives none,
compute them (next section).

### Pad sizes when the datasheet has no land pattern

For a leaded IC in a standard family (gull wing, QFN/DFN), `ipc_land.py` in this skill's folder computes the
IPC-7351B nominal pads the way KiCad's footprint generator does, from the package drawing's min/max dimensions:

```bash
python3 -I <this skill>/ipc_land.py gw 5.80 6.20 0.40 1.27 0.31 0.51   # SOIC-8: span L, lead length T, lead width W
# Z=6.90 G=3.00 X=0.60 -> pad 1.950 x 0.600 mm, pad centres at +/-2.4750 mm from the part's centre
```

- **Families:** `gw` is gull wing with pitch over 0.625 mm, `gw-fine` is gull wing at 0.625 mm or less, `qfn` is
  QFN/DFN. For QFN/DFN, L is the body size.
- **Accuracy:** tested against KiCad's stock footprints. SOIC-8 matched exactly; QFN-16, TSSOP-14 and MSOP-10
  came within 0.1 mm, where KiCad also applies its own rules and dimension tables.
- **Exposed pad:** keep the signal pads at least 0.2 mm from it, and shorten them at the inner end if they're closer.
- **Compare it with a stock footprint** of a similar package (same family and pitch). If a pad differs by more than
  about 0.1 mm, recheck the dimensions you entered.
- **Show the numbers you entered** and their datasheet page, so the user can check them.

Chip passives, crystals and other packages outside these families: use a stock footprint, or the datasheet's
land pattern.

### Writing the file

A footprint file is `(footprint "Name" (version 20260206) (generator "pcbnew") (layer "F.Cu") (descr ...) (tags ...)
(property "Reference" "REF**" ...) (property "Value" "Name" ...) (attr smd|through_hole) ... graphics ... pads ...
(model ...))`. KiCad's conventions (the KiCad Library Convention, KLC):
- **Origin:** the centre of the part for SMD parts, pin 1 for most through-hole parts. Pick-and-place uses the
  origin (`kicad-assembly-export`).
- **Pads:** `(pad "1" smd roundrect (at x y) (size w h) (layers "F.Cu" "F.Paste" "F.Mask") (roundrect_rratio 0.25))`.
  Through-hole pads use `thru_hole` with `(drill d)` and `(layers "*.Cu" "*.Mask")`. A mechanical hole is
  `np_thru_hole` with an empty number. Numbers match the datasheet's pin numbers exactly, including letters
  (`A1`) for BGAs.
- **Exposed pads:** number them as the datasheet does (often the pin count + 1, or the GND pin's number). Split the
  paste into a grid of about 50–70 % coverage. Add thermal vias if the datasheet asks.
- **F.Fab:** the body outline at real size, 0.1 mm lines, a pin 1 mark, and `${REFERENCE}` text.
- **F.SilkS:** the outline, kept 0.2 mm clear of pads, with a pin 1 mark that is still visible after the part is
  placed. KiCad uses 0.12 mm lines; JLC prefers 0.15 mm (`kicad-check`).
- **F.CrtYd:** a closed outline 0.25 mm around body and pads (0.15 mm for parts smaller than 0603), on a 0.01 mm
  grid, 0.05 mm lines.
- **3D model:** `(model "${KICAD10_3DMODEL_DIR}/Package_SO.3dshapes/SOIC-8_3.9x4.9mm_P1.27mm.step" (offset (xyz 0 0 0))
  (scale (xyz 1 1 1)) (rotate (xyz 0 0 0)))`. A project's own models use `${KIPRJMOD}/3dmodels/...`. Check
  alignment in a render.

## Symbols

A symbol in a `.kicad_sym` file:

```
(symbol "LDO_TEST"
	(exclude_from_sim no) (in_bom yes) (on_board yes)
	(property "Reference" "U" (at -5.08 6.35 0) (effects (font (size 1.27 1.27)) (justify left)))
	(property "Value" "LDO_TEST" (at 0 6.35 0) (effects (font (size 1.27 1.27)) (justify left)))
	(property "Footprint" "Package_TO_SOT_SMD:SOT-23-5" (at 0 0 0) (hide yes) (effects (font (size 1.27 1.27))))
	(property "Datasheet" "https://..." (at 0 0 0) (hide yes) (effects (font (size 1.27 1.27))))
	(property "Description" "..." (at 0 0 0) (hide yes) (effects (font (size 1.27 1.27))))
	(symbol "LDO_TEST_0_1"                                   ; graphics shared by all units
		(rectangle (start -5.08 5.08) (end 5.08 -5.08) (stroke (width 0.254) (type default)) (fill (type background))))
	(symbol "LDO_TEST_1_1"                                   ; unit 1's pins
		(pin power_in line (at -7.62 2.54 0) (length 2.54) (name "VIN" (effects (font (size 1.27 1.27))))
			(number "1" (effects (font (size 1.27 1.27)))))
		...)
	(embedded_fonts no))
```

(The `;` notes above are explanations, not file syntax: leave them out.)
- **Coordinates:** library y points up. A pin's `(at x y angle)` is its connection end, and `angle` points from
  that end into the body (0 = body to the right).
- **Grid:** pin ends on the 2.54 mm grid, pin length 2.54 mm (longer for long names).
- **Pin types** drive ERC: `power_in` for supplies, `power_out` for regulator outputs, `input`, `output`,
  `bidirectional`, `passive` for resistors and connectors, `no_connect` for NC pins. Types that are too loose hide
  real errors; types that are too strict make false ones.
- **Units:** a multi-unit part has `Name_1_1`, `Name_2_1`... and shared pins in `Name_0_1`.
- Inputs on the left, outputs on the right, supplies at the top, ground at the bottom, unless the datasheet's
  grouping reads better. NC pins are hidden, type `no_connect`, on the body outline.
- **Several pins with one function** (four GND pins): KiCad 10 stacks them natively, as one pin numbered
  `"[2,5,8,11]"` or `"[1-4]"` (see `Driver_LED:IS31FL3242`). Don't use the old way, several pins on the same spot
  with all but one hidden. KiCad's checker now flags that as a legacy stack.
- **Pins with several functions** (an MCU's PA9 = USART1_TX = TIM1_CH2): give the pin its main name and add the
  others as `(alternate "USART1_TX" bidirectional line)` entries inside the pin, rather than one long name joined
  with slashes. The schematic can then pick the function in use.
- **Name formatting:** `~{RESET}` draws an overbar, `_{x}` a subscript, `^{x}` a superscript.

### Where a pin table can come from

- **The datasheet's pin table** is the source of truth. Copy it as text from the PDF when the PDF has text. When it's
  an image, read it from a rendered page, and have the user confirm the table before building on it.

## Check every new or changed part

1. **It parses.**
   `mkdir -p <scratch>/chk && "$K" fp upgrade --force -o <scratch>/chk <lib>.pretty` and
   `"$K" sym upgrade --force -o <scratch>/chk/x.kicad_sym <lib>.kicad_sym`. Exit 2 and "Unable to load library"
   mean a syntax error. Write to `<scratch>`, not in place: an in-place upgrade reformats and re-sorts the whole
   library.
2. **It looks right.** `"$K" fp export svg --fp <Name> -o <scratch>/svg <lib>.pretty` (the folder must exist), and
   `"$K" sym export svg -o <scratch>/svg <lib>.kicad_sym`. Convert with `rsvg-convert -w 1000 -b white x.svg -o
   x.png` (Homebrew `librsvg`), or `qlmanage -t -s 1000 -o <scratch> x.svg` on macOS. Look at pin 1, the pad
   shapes and the outline.
3. **The numbers match the datasheet.** Read each pad's `(at ...)` and `(size ...)` from the file and compare:
   - pitch;
   - row spacing (pad centre to pad centre across the part);
   - pad size;
   - where pin 1 is;
   - the exposed pad.

   Write the comparison down in a short table.
4. **Pins and pads agree.** The symbol's pin numbers and the footprint's pad numbers must be the same set. KiCad 10
   symbols can stack several pins into one entry numbered `"[20,21]"` or `"[1-4]"`, so expand those before
   comparing:

```python
# <scratch>/pinpad.py   run: python3 <scratch>/pinpad.py <lib>.kicad_sym <Symbol> <lib>.pretty/<Footprint>.kicad_mod
import re, sys
sym_lib, name, fp = sys.argv[1:4]
text = open(sym_lib).read()
start = re.search(r'\n\t\(symbol "%s"\n' % re.escape(name), text).start() + 1
end = text.find("\n\t)\n", start)
numbers = re.findall(r'\(number "([^"]*)"', text[start:end])
pins = set()
for n in numbers:                                   # KiCad 10 native stacks: "[2,5,8]" or "[1-4]"
    m = re.fullmatch(r"\[(.*)\]", n)
    for part in (m.group(1).split(",") if m else [n]):
        part = part.strip(); a = part.split("-")
        if m and len(a) == 2:
            pre = re.match(r"\D*", a[0]).group(0)
            pins.update(pre + str(i) for i in range(int(a[0][len(pre):]), int(a[1][len(pre):]) + 1))
        else:
            pins.add(part)
pads = set(re.findall(r'\(pad "([^"]*)"', open(fp).read())) - {""}   # "" = mechanical hole
print("pins without a pad:", sorted(pins - pads))
print("pads without a pin:", sorted(pads - pins))
```

   Both lists must be empty, unless a pad is deliberately unconnected (say which). Then check the meaning, pin by
   pin, against the datasheet's pinout for this package: the same part in another package often numbers its pins
   differently.
5. **On a board.** After `sch_to_board.py` (`kicad-board-edit`), DRC (`kicad-check`) reports courtyard overlaps,
   clearance problems inside the footprint, and `lib_footprint_mismatch` if the board's copy differs from the
   library.

## After changing a library part that's already in use

- **Schematics** keep their own copy in `lib_symbols`. ERC's `lib_symbol_mismatch` catches moved pins and changed
  graphics but **not renamed pins**. Re-copy the changed symbol into every schematic that uses it
  (`kicad-schematic`), and check the netlist.
- **Boards** keep their own copy of each footprint. DRC reports `lib_footprint_mismatch`. To take the new version,
  delete the part from the board and add it again with `sch_to_board.py`, then re-route its pads.
