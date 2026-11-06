---
name: kicad-assembly-export
description: Make the BOM and pick-and-place (CPL) files for JLCPCB's SMT assembly from a KiCad 10 project - a jobset template in this skill's folder writes both with JLC's column names, then the CPL header and per-package rotation corrections are applied - and check the order before it's placed - LCSC part numbers on every placed part, BOM and CPL designators agreeing, parts at least 2.5 mm from the board edge (a DRC rule file in this skill's folder), Economic vs Standard assembly limits, rotations in JLC's preview. Use when the user wants a board assembled by JLC, asks for a BOM or CPL/pick-and-place/centroid file, or adds LCSC numbers.
---

# Export a board for JLCPCB assembly

`K` is `kicad-cli` (see `kicad-view`). Gerbers and drill files come from `kicad-fab-export`. This skill adds the two
files JLC's assembly order asks for, and the checks that keep the order from going wrong.

What JLC asks for (its help center, read 2026-11-05):
- **BOM:** columns `Comment` (value), `Designator`, `Footprint`, and the part number column `JLCPCB Part #`
  (the KiCad guide also calls it "LCSC Part #"). Designators comma-separated, no ranges such as `R1-R8`.
  - Each designator appears once.
  - At most 200 designators per row.
  - csv, xls or xlsx.
- **CPL:** columns `Designator`, `Mid X`, `Mid Y`, `Layer`, `Rotation`; mm; layer `Top`/`Bottom` or `T`/`B`
  (lowercase works too); rotation in degrees, counter-clockwise positive; top and bottom in one file.
- **Both:** only designators present in both files get assembled. Designators must match exactly, including case.
- **Origin:** the CPL and the Gerbers must share one origin. Both jobsets use KiCad's absolute origin, so keep
  `use_drill_place_file_origin` and the Gerber job's `use_drill_origin` the same if you change either.

## Part numbers in the schematic

Give every part JLC should place a symbol field `LCSC` holding its LCSC number (`C` + digits, e.g. `C17414`). Add it
with the `kicad-schematic` skill, then carry it to the board with `sch_to_board.py` (`kicad-board-edit`), so DRC
parity stays clean. If the project already uses another field name (`LCSC Part #`, `JLCPCB`), change
`fields_ordered` in the jobset copy rather than renaming the fields.

Choosing parts (Basic vs Extended, stock, footprint match): see `kicad-part-selection`.

## Set it up once per project

```bash
cp <skill dir>/jlc-assembly.kicad_jobset <project dir>/     # <skill dir>: the folder this SKILL.md is in
```

It writes `fab/assembly/<project>_bom.csv` and `fab/assembly/<project>_cpl-all-pos.csv`. KiCad appends `-all-pos`
to a both-sides position file. Settings, which you can change in the copy:
- **BOM:**
  - DNP parts left out (`exclude_dnp`);
  - parts excluded from the BOM in the schematic left out;
  - grouped by value, footprint and LCSC number;
  - no designator ranges (`ref_range_delimiter: ""`).
- **CPL:**
  - both sides, mm, CSV, absolute origin;
  - DNP parts and footprints marked "exclude from position files" left out (mounting holes and fiducials are
    marked so in KiCad's libraries);
  - through-hole parts kept. Set `exclude_footprints_with_th: true` when JLC won't fit them, so they don't show
    as unplaced.

Commit the jobset with the project.

## Export

After the DRC gate and the Gerber export (`kicad-fab-export`):

```bash
"$K" jobset run --stop-on-error -f jlc-assembly.kicad_jobset board.kicad_pro
```

Then turn KiCad's position file into JLC's CPL. KiCad's header is `Ref,Val,Package,PosX,PosY,Rot,Side`, and the
step below renames it and applies rotation corrections. The corrections file, `jlc-rotations.csv` in the project,
holds lines `Match,Offset`. `Match` is a designator (`U3`) or a package exactly as in the position file's
`Package` column (`SOT-23-5`). A designator line wins over a package line.

```python
# <scratch>/cpl.py   run: python3 <scratch>/cpl.py fab/assembly/<p>_cpl-all-pos.csv fab/assembly/<p>_cpl.csv jlc-rotations.csv
import csv, os, sys
raw, out, corr = sys.argv[1], sys.argv[2], (sys.argv[3] if len(sys.argv) > 3 else "")
offsets = {}
if corr and os.path.exists(corr):
    offsets = {r["Match"]: float(r["Offset"]) for r in csv.DictReader(open(corr, newline=""))}
with open(raw, newline="") as f, open(out, "w", newline="") as g:
    w = csv.writer(g)
    w.writerow(["Designator", "Val", "Package", "Mid X", "Mid Y", "Rotation", "Layer"])
    for r in csv.DictReader(f):
        off = offsets.get(r["Ref"], offsets.get(r["Package"], 0.0))       # a designator row wins over a package row
        rot = (float(r["Rot"]) + off) % 360
        w.writerow([r["Ref"], r["Val"], r["Package"], r["PosX"], r["PosY"], f"{rot:g}", r["Side"]])
os.remove(raw)
```

KiCad's y values are negative (its position files use y up). That's expected, and it matches the Gerbers.

## Check before ordering

1. **BOM against CPL, and part numbers:**

```python
# <scratch>/asmcheck.py   run: python3 <scratch>/asmcheck.py fab/assembly/<p>_bom.csv fab/assembly/<p>_cpl.csv
import csv, re, sys
bom = list(csv.DictReader(open(sys.argv[1], newline="")))
cpl = list(csv.DictReader(open(sys.argv[2], newline="")))
in_bom = {d.strip(): r for r in bom for d in r["Designator"].split(",")}
in_cpl = {r["Designator"]: r for r in cpl}
print("in the BOM, not placed:", sorted(set(in_bom) - set(in_cpl)))
print("placed, not in the BOM:", sorted(set(in_cpl) - set(in_bom)))
print("placed, no LCSC number:", sorted(d for d in in_cpl if d in in_bom and not in_bom[d]["JLCPCB Part #"].strip()))
print("odd LCSC numbers:", sorted({r["JLCPCB Part #"] for r in bom if r["JLCPCB Part #"].strip() and not re.fullmatch(r"C\d+", r["JLCPCB Part #"].strip())}))
print("sides:", sorted({r["Layer"] for r in cpl}))
print("BOM rows over 200 designators:", [r["Comment"] for r in bom if len(r["Designator"].split(",")) > 200])
```

   - A placed part with no LCSC number won't be fitted. Either the user supplies it, or it's hand-soldered later:
     say which.
   - "Sides" with both `top` and `bottom` means Standard assembly (Economic is one side only).
2. **Part-to-edge distance.** JLC wants every part body at least 2.5 mm from the board edge, unless edge rails are
   added. Run DRC with `jlcpcb-assembly.kicad_dru` from this folder, on a copy, as in `kicad-check` step 3. Add the
   references of parts JLC won't place to its exclusion list first.
3. **Economic vs Standard** (JLC's assembly capabilities page):

   | | Economic | Standard |
   |---|---|---|
   | Sides | one | one or both |
   | Board | 10×10 to 470×500 mm, 0.8–1.6 mm thick, 2/4/6 layers | 70×70 to 460×500 mm |
   | Smallest package | 0402 | 01005 |
   | Finest IC pitch | 0.4 mm | 0.35 mm |
   | BGA pitch | 0.5 mm | 0.3 mm |
   | Quantity | 2–50 | 2–80,000 |
   | Rails, fiducials | not needed | needed (JLC adds them by default) |

   Footprints should be IPC-7351B nominal or least density: JLC doesn't support "most" (high-density) land patterns.
4. **Rotations.**
   - JLC's library defines a package's zero angle by how it sits in the tape, and some of KiCad's footprints define
     it differently. A wrong angle places the part rotated: an IC or diode fails, a resistor doesn't care.
   - JLC doesn't publish its convention per package. Tell the user to check every polarised part (ICs, diodes,
     LEDs, electrolytics, transistors, connectors) in the placement preview on JLC's order page before paying.
   - For each one shown wrong, add a line to `jlc-rotations.csv` (by package, so the next board inherits it),
     re-export, and check again. Commit the file.
   - JLC also says its engineers correct rotations from the silkscreen polarity marks during review. That is a
     safety net, not a plan.
   - Community tables of corrections exist, e.g. `cpl_rotations_db.csv` in matthewlai/JLCKicadTools, used by
     Bouni's kicad-jlcpcb-tools. They are not JLC's: use them to guess, then confirm in the preview.
5. **Bottom-side parts.** JLC documents neither the rotation nor the X convention it expects for the bottom side.
   The community plugins leave X as is and report rotation as seen from above. Check every bottom part in the
   preview, and prefer one-sided assembly when the design allows.
6. **Parts whose origin isn't their centre.** JLC places by the centre of the part. Most connector and
   through-hole footprints have their origin on pin 1, and the CPL gives the origin. Check those in the preview,
   and correct their position there or move them by hand.

## Rules

- The schematic is the source of part numbers. Never edit the BOM or CPL by hand, apart from the CPL step above.
  Fix the schematic or `jlc-rotations.csv`, and export again.
- Re-export both files after any change to the board or to part numbers, and commit them with that change if the
  project keeps them.
