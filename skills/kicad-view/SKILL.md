---
name: kicad-view
description: "See a KiCad 10 schematic or PCB: plot it to PDF or PNG, render the board in 3D, find which net each pin is on from the netlist, and compare two git revisions. Use whenever you need to look at a design, before and after any edit, to check a connection, to review what a commit changed, or when the user asks to see or screenshot a board or schematic."
---

# Look at a KiCad design

Write all output to a scratch folder (`<scratch>`), never into the project.

`K` stands for the path to `kicad-cli`:

| OS | Path |
|---|---|
| macOS | `/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli` (not on PATH) |
| Linux | `kicad-cli` |
| Windows | `C:\Program Files\KiCad\10.0\bin\kicad-cli.exe` |

`"$K" version` must print 10.x. If it doesn't, stop and tell the user. On macOS with Homebrew's fontconfig, every run
prints harmless `Fontconfig warning` lines; send them to `/dev/null`.

## Schematic

```bash
"$K" sch export pdf -o <scratch>/sch.pdf board.kicad_sch
pdftoppm -png -r 100 <scratch>/sch.pdf <scratch>/sch     # sch-1.png, sch-2.png, … (poppler)
```

- **Pages:** you get one page per sheet.
- **Resolution:** 100 dpi is enough for blocks and labels. Raise `-r` for pin numbers, or read them from the netlist.
- **Single pages:** `sips` converts only the first page.

## Which net a pin is on

Use the default netlist format. It keeps KiCad's real net names; `kicadxml` unescapes them, so `A{slash}B` there reads
like a sheet path.

```bash
"$K" sch export netlist -o <scratch>/net.net board.kicad_sch
awk '/^\t\t\(net$/{n=""} /^\t\t\t\(name "/{if(n==""){n=$0; sub(/.*\(name "/,"",n); sub(/"\)$/,"",n)}}
  /^\t\t\t\t\(ref "/{r=$0; sub(/.*\(ref "/,"",r); sub(/"\)$/,"",r)}
  /^\t\t\t\t\(pin "/{p=$0; sub(/.*\(pin "/,"",p); sub(/"\)$/,"",p); print r"."p"\t"n}' \
  <scratch>/net.net | sort -V > <scratch>/pins.tsv
grep '^U2\.' <scratch>/pins.tsv                  # U2's pins and nets
awk -F'\t' '$2=="/VREF"' <scratch>/pins.tsv      # everything on /VREF
```

- **Empty output:** the awk depends on kicad-cli's tab indentation. If it prints nothing, check the file's layout.
- **Broken connections:** a wire that only looks connected shows up as a separate net.
- **Net names to recognise:**
  - unnamed nets look like `Net-(C2-Pad2)`;
  - unconnected pins look like `unconnected-(U1-NC-Pad5)`;
  - `/` in a net name is escaped as `{slash}`.

## Board

```bash
"$K" pcb export pdf -o <scratch>/top.pdf --mode-single --scale 0 -l F.Cu,F.SilkS,F.Mask,Edge.Cuts board.kicad_pcb
"$K" pcb export pdf -o <scratch>/bottom.pdf --mode-single --scale 0 --mirror -l B.Cu,B.SilkS,B.Mask,Edge.Cuts board.kicad_pcb
```

- **Layer names:** kicad-cli wants the canonical names (`F.SilkS`, `F.CrtYd`, `In1.Cu`), not the editor's long ones.
- **Placement:** add `F.Fab` and `F.CrtYd` to see part outlines and courtyards.
- **Single-page mode:** layers draw in a fixed order, so a bottom pour hides top tracks. Plot one copper layer per PDF,
  or use `--mode-multipage`.

For a close-up 3D render (no net names):

```bash
"$K" pcb render -o <scratch>/view.png --side top --quality basic --width 1600 --height 1200 \
  --zoom 4 --pan "X,Y,0" board.kicad_pcb
```

- **Aiming:** `--pan` takes trial and error, so render, look and adjust.
- **Other views:** `--side bottom`, `--perspective` and `--rotate`.
- **Exact numbers:** read them from the `.kicad_pcb`. Footprints have `(at x y rot)`, and pads have `(at dx dy)`
  relative to their footprint.

## Compare two revisions

```bash
mkdir -p <scratch>/old <scratch>/new
git archive <old-rev> | tar -x -C <scratch>/old     # for uncommitted work, use the working tree as "new"
git archive <new-rev> | tar -x -C <scratch>/new
# export each netlist, run the awk above into old.tsv / new.tsv, then:
diff <scratch>/old.tsv <scratch>/new.tsv
```

- **Changed lines:** each one is a pin whose net changed.
- **Auto-named nets:** these rename when their namesake part changes, even if the connection didn't. Treat a renamed
  auto-named net as something to check, not as a change.
- **Values and fields:** diff the BOMs from `"$K" sch export bom --fields 'Reference,Value,Footprint,${DNP}'`.
- **Pictures:** plot the same sheet or layers from both trees and compare them side by side.

## Reading results

- **Coordinates:** board coordinates are in mm, with y increasing downward. Position files and Gerbers flip the sign
  of y.
- **What pictures are for:** use pictures to spot problems. Take measurements from the file, and confirm connections
  with the netlist or DRC.
- **Related skills:**
  - checking a design: `kicad-check`;
  - changing a schematic: `kicad-schematic`;
  - changing a board: `kicad-board-edit`;
  - one footprint or symbol: `kicad-library`.
