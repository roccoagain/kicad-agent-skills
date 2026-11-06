---
name: kicad-new-project
description: "Create a new KiCad 10 project without opening KiCad: project, schematic and board files, layer count, thickness, design rules and net classes, board outline, mounting holes, ground pours, libraries, jobsets and .gitignore. Use when the user wants a new board, a new revision of an existing one, or a PCB for a schematic that doesn't have one yet."
---

# Start a new project

`K` is `kicad-cli` (see `kicad-view`). `KPY` is KiCad's bundled Python (see `kicad-board-edit`). Keep scripts in
`<scratch>`.

Get these from the user or the design notes:
- **Board:** size and shape, and what fixes them (the enclosure, the holes, edge connectors).
- **Layers:** 2 by default. Use 4 for USB high-speed or faster links, for dense parts, or when sensitive analog needs a
  solid plane.
- **Thickness:** 1.6 mm unless something requires otherwise.
- **Fab and assembly:** JLC unless told otherwise, and whether assembly is by hand or by JLC.

## 1. Files

The `.kicad_pro`, `.kicad_sch` and `.kicad_pcb` share one stem, which is the project name.

```bash
mkdir -p <project dir>
"$KPY" -I -c "import pcbnew, sys; b = pcbnew.NewBoard(sys.argv[1]); b.Save(sys.argv[1])" <abs path>/<name>.kicad_pcb
```

This writes the board, a default `.kicad_pro` (if none exists yet), and a `.kicad_prl`. Don't commit the `.kicad_prl`.

Next, write the root schematic with a new UUID:

```
(kicad_sch
	(version 20260306)
	(generator "eeschema")
	(generator_version "10.0")
	(uuid "<new uuid>")
	(paper "A4")
	(title_block (title "<title>") (date "<YYYY-MM-DD>") (rev "1"))
	(lib_symbols)
	(sheet_instances (path "/" (page "1")))
	(embedded_fonts no)
)
```

`"$K" sch erc` on this file must report 0 violations. Draw the circuit with `kicad-schematic`.

For a new revision, copy the whole old folder (e.g. `rev1/` to `rev2/`). Library paths that use `${KIPRJMOD}/..` keep
working as long as the folder depth stays the same.

## 2. Libraries

Stock libraries come from the global tables. Add project tables only for the project's own libraries:

```
(fp_lib_table
  (version 7)
  (lib (name "MyProject")(type "KiCad")(uri "${KIPRJMOD}/MyProject.pretty")(options "")(descr "Project footprints"))
)
```

`sym-lib-table` uses the same format, with `sym_lib_table` and a `.kicad_sym` file. To make the parts, see
`kicad-library`.

## 3. Layers, thickness, rules

Edit with the board closed:

```python
import pcbnew, sys
b = pcbnew.LoadBoard(sys.argv[1])
b.SetCopperLayerCount(4)
ls = b.GetEnabledLayers(); ls.addLayer(pcbnew.In1_Cu); ls.addLayer(pcbnew.In2_Cu); b.SetEnabledLayers(ls)
b.GetDesignSettings().SetBoardThickness(pcbnew.FromMM(1.6))
b.Save(sys.argv[1])
```

- **Stackup:** KiCad 10.0's Python can't edit the stackup table. JLC's stackup is chosen on the order page, so record
  the chosen stackup in the design notes and size impedance-controlled tracks from JLC's calculator for it.
- **Rules and net classes:** set them in the `.kicad_pro`, as `kicad-routing` section 1 describes. Make the minimums
  at least the fab's limits, and add a Default class and a power class.
- **Other rules:** write anything else in `<name>.kicad_dru`, with comments on their own lines.

## 4. Outline, holes, pours

Edit with the board closed. This example draws a W × H outline with corner radius R, adds four M3 holes 3.5 mm from
the corners, and adds GND pours on both sides:

```python
import pcbnew, sys
path = sys.argv[1]
W, H, X0, Y0, R = 40.0, 30.0, 100.0, 100.0, 1.0
SHARE = "/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints"   # Linux: /usr/share/kicad/footprints
b = pcbnew.LoadBoard(path); mm = pcbnew.FromMM

def seg(a, c):
    s = pcbnew.PCB_SHAPE(b, pcbnew.SHAPE_T_SEGMENT); s.SetLayer(pcbnew.Edge_Cuts); s.SetWidth(mm(0.05))
    s.SetStart(pcbnew.VECTOR2I(mm(a[0]), mm(a[1]))); s.SetEnd(pcbnew.VECTOR2I(mm(c[0]), mm(c[1]))); b.Add(s)

def arc(center, start):                         # 90°, clockwise on screen
    s = pcbnew.PCB_SHAPE(b, pcbnew.SHAPE_T_ARC); s.SetLayer(pcbnew.Edge_Cuts); s.SetWidth(mm(0.05))
    s.SetCenter(pcbnew.VECTOR2I(mm(center[0]), mm(center[1]))); s.SetStart(pcbnew.VECTOR2I(mm(start[0]), mm(start[1])))
    s.SetArcAngleAndEnd(pcbnew.EDA_ANGLE(90, pcbnew.DEGREES_T), True); b.Add(s)

x1, y1, x2, y2 = X0, Y0, X0 + W, Y0 + H
seg((x1 + R, y1), (x2 - R, y1)); seg((x2, y1 + R), (x2, y2 - R))
seg((x2 - R, y2), (x1 + R, y2)); seg((x1, y2 - R), (x1, y1 + R))
arc((x2 - R, y1 + R), (x2 - R, y1)); arc((x2 - R, y2 - R), (x2, y2 - R))
arc((x1 + R, y2 - R), (x1 + R, y2)); arc((x1 + R, y1 + R), (x1, y1 + R))

for i, (x, y) in enumerate([(x1 + 3.5, y1 + 3.5), (x2 - 3.5, y1 + 3.5), (x2 - 3.5, y2 - 3.5), (x1 + 3.5, y2 - 3.5)], 1):
    fp = pcbnew.FootprintLoad(f"{SHARE}/MountingHole.pretty", "MountingHole_3.2mm_M3")
    fp.SetFPID(pcbnew.LIB_ID("MountingHole", "MountingHole_3.2mm_M3"))
    fp.SetReference(f"H{i}"); fp.SetBoardOnly(True)          # board-only: no parity error
    fp.SetPosition(pcbnew.VECTOR2I(mm(x), mm(y))); b.Add(fp)

gnd = next((p.GetNet() for p in b.GetPads() if p.GetNetname() == "GND"), None)   # needs parts on the board
for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
    z = pcbnew.ZONE(b); z.SetLayer(layer); z.SetNet(gnd)
    z.SetLocalClearance(mm(0.3)); z.SetMinThickness(mm(0.25))
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
    z.SetThermalReliefGap(mm(0.5)); z.SetThermalReliefSpokeWidth(mm(0.5))
    ol = z.Outline(); ol.NewOutline()
    for x, y in [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]:
        ol.Append(mm(x), mm(y))
    b.Add(z)

tb = b.GetTitleBlock(); tb.SetTitle("<title>"); tb.SetRevision("1"); tb.SetDate("<YYYY-MM-DD>")
b.Save(path)
```

- **Outline:** it must close exactly. If it doesn't, DRC reports `invalid_outline`. A positive arc angle turns
  clockwise on screen.
- **Holes:**
  - Use 2.7 mm for M2.5 and 3.2 mm for M3.
  - Use a `_Pad` variant on GND if the chassis should be grounded.
  - Mark holes, fiducials and logos as board-only.
- **Pours:** a pour needs its net on the board first, so run the pour code after step 5. The fill keeps its own
  clearance from the edge.
- **Fixed parts:** place and lock edge connectors and enclosure-dictated parts first (`kicad-placement`).

## 5. Parts onto the board

Once ERC is clean, run `sch_to_board.py` (`kicad-board-edit`). It adds every part, with its nets, in a row outside
the outline. Then place them (`kicad-placement`), route (`kicad-routing`), and check (`kicad-check`).

## 6. Housekeeping

- **`.gitignore`:** `*.kicad_prl`, `~*.lck`, `.history/`, `*-backups/`, `fp-info-cache`.
- **Jobsets:** copy in `jlc-fab.kicad_jobset`, plus `jlc-assembly.kicad_jobset` if JLC assembles the board. Set the zip
  name.
- **`DESIGN.md`:** record:
  - the board's purpose;
  - its supplies, and what each connector can see;
  - the layers, stackup and fab;
  - placement and routing decisions, with their reasons;
  - decisions the user has accepted.
- **Test plan:** start one with `kicad-bringup` once the schematic settles.
- **CLAUDE.md or AGENTS.md:** if the project has one, note the skills used and the `kicad-cli` path.
