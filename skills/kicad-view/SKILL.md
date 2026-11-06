---
name: kicad-view
description: Look at a KiCad 10 schematic or PCB using only KiCad's own tools - kicad-cli plots it to PDF (or renders the board in 3D) and you look at the result; the netlist export answers "which net is this pin on"; two git revisions can be compared by picture and pin by pin. Use whenever you need to see a schematic or board, before and after any edit, when checking a connection, when reviewing what a commit changed, or when the user asks how part of a design looks.
---

# Look at a KiCad design

Everything here is `kicad-cli`, which ships with KiCad. Write every output to a temporary folder outside the
project (`<scratch>` below), never into the project.

`kicad-cli` is not on PATH on macOS. Below, `K` stands for it:
- macOS: `K=/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli`
- Linux: `K=kicad-cli`
- Windows: `K="C:\Program Files\KiCad\10.0\bin\kicad-cli.exe"`

`"$K" version` must print 10.x. These skills rely on KiCad 10 behaviour, so stop and tell the user if it's older.
On macOS with Homebrew's fontconfig, every `kicad-cli` run prints dozens of `Fontconfig warning` lines on stderr:
they're harmless, so send stderr to `/dev/null` or filter them out.

## Schematic

```bash
"$K" sch export pdf -o <scratch>/sch.pdf board.kicad_sch
```

One page per sheet on a hierarchical design. If your agent can only view images, convert the pages:
`pdftoppm -png -r 100 <scratch>/sch.pdf <scratch>/sch` writes `sch-1.png`, `sch-2.png`... (poppler; `brew install
poppler` or `apt install poppler-utils`). macOS's `sips -s format png` converts only the first page. A whole A3
sheet at 100 dpi is legible for blocks, labels, references and most values. Fine print (pin numbers, small values)
is borderline: raise `-r`, or better, confirm it in the netlist.

## Which net is a pin on (connections, by the netlist, not by eye)

Export KiCad's own netlist, the one the board is updated from. Use the default s-expression format: it keeps
KiCad's real net names. The `kicadxml` format unescapes them, so a label `A/B` reads `/A/B` there, like a sheet
path, while the board calls it `/A{slash}B`.

```bash
"$K" sch export netlist -o <scratch>/net.net board.kicad_sch
awk '/^\t\t\(net$/{n=""} /^\t\t\t\(name "/{if(n==""){n=$0; sub(/.*\(name "/,"",n); sub(/"\)$/,"",n)}}
  /^\t\t\t\t\(ref "/{r=$0; sub(/.*\(ref "/,"",r); sub(/"\)$/,"",r)}
  /^\t\t\t\t\(pin "/{p=$0; sub(/.*\(pin "/,"",p); sub(/"\)$/,"",p); print r"."p"\t"n}' \
  <scratch>/net.net | sort -V > <scratch>/pins.tsv
grep '^U2\.' <scratch>/pins.tsv         # every pin of U2 and its net
awk -F'\t' '$2=="/VREF"' <scratch>/pins.tsv   # every pin on /VREF
```

The awk relies on the layout `kicad-cli` writes: one item per line, tab-indented, nets at two tabs. If it
prints nothing, look at the file's layout first.

A wire that looks connected but isn't (a missing junction, a label one character off, an end a grid step away)
shows up as a separate net. Unnamed nets read like `Net-(C2-Pad2)`, and unconnected pins as
`unconnected-(U1-NC-Pad5)`. Names escape `/` as `{slash}`, and a few other characters the same way.

## Board, whole

```bash
"$K" pcb export pdf -o <scratch>/top.pdf --mode-single --scale 0 \
  -l F.Cu,F.SilkS,F.Mask,Edge.Cuts board.kicad_pcb
"$K" pcb export pdf -o <scratch>/bottom.pdf --mode-single --scale 0 --mirror \
  -l B.Cu,B.SilkS,B.Mask,Edge.Cuts board.kicad_pcb
```

- `--scale 0` fits the board to the page.
- Layer names are KiCad's canonical ones (`F.SilkS`, `B.Fab`, `F.CrtYd`, `In1.Cu`...). The API and the editor
  show the long names (`F.Silkscreen`), but `kicad-cli` wants the canonical ones.
- Add `F.Fab` and `F.CrtYd` for part outlines and courtyards when judging placement.
- In `--mode-single`, layers are drawn in a fixed order, and a bottom pour covers top tracks. Put one copper layer
  in each PDF, or use `--mode-multipage` for one page per layer.
- The board's own colours come from the PCB editor's theme. `--black-and-white` or `--theme` change them.

## Board, close up

```bash
"$K" pcb render -o <scratch>/view.png --side top --quality basic --width 1600 --height 1200 \
  --zoom 4 --pan "X,Y,0" board.kicad_pcb
```

A 3D render: real pads, silkscreen and parts, but no net names or ratsnest.
- `--zoom` multiplies the fit-to-board view.
- `--pan` shifts the camera and is fiddly to aim: render, look, adjust.
- `--side bottom`, `--perspective` and `--rotate` give other views.
- For an exact number (a pad's position, a gap), read the `.kicad_pcb` text instead. Each footprint has
  `(at x y rot)` and each pad `(at dx dy)` relative to it. That beats any picture.

## Compare two revisions

To see what a commit changed (before committing, or when reviewing someone's change), extract both revisions
whole, so library tables and sub-sheets come along, then compare pictures and pin lists:

```bash
mkdir -p <scratch>/old <scratch>/new
git archive <old-rev> | tar -x -C <scratch>/old        # or HEAD; for uncommitted work use the working tree as "new"
git archive <new-rev> | tar -x -C <scratch>/new
for v in old new; do
  "$K" sch export netlist -o <scratch>/$v.net <scratch>/$v/<path>/board.kicad_sch
  # same awk as above -> <scratch>/$v.tsv
done
diff <scratch>/old.tsv <scratch>/new.tsv
```

- Each changed line is a pin whose net changed, appeared or disappeared.
- Auto-named nets (`Net-(C10-Pad2)`) are named after one of their pins, so they rename when that part changes even
  if the connection didn't. Read a renamed unnamed net as "check", not as "changed".
- For the picture, plot the same sheet or layers from both trees and look at them side by side.
- For values and fields, diff the BOMs: `"$K" sch export bom --fields 'Reference,Value,Footprint,${DNP}'`.

## Reading the pictures

- Board coordinates are mm with y growing downwards, the numbers KiCad's editor, DRC and the `.kicad_pcb` use.
  (Position files and Gerbers flip y, so their y values are negative.)
- A picture is for spotting problems. Measure from the file, and confirm connections with the netlist or DRC.
- To check a design, use the `kicad-check` skill. To change one, use `kicad-schematic` or `kicad-board-edit`. To
  look at a single footprint or symbol, use `kicad-library`.
