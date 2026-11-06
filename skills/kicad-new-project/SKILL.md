---
name: kicad-new-project
description: Start a new KiCad 10 project or board without opening KiCad - create the project, schematic and board files, set the layer count, thickness, design rules and net classes for the fab, draw the board outline with rounded corners, place mounting holes and ground pours, set up project libraries, jobsets, .gitignore and design notes - then bring the schematic's parts onto the board for placement. Use when the user wants a new board, a new revision copied from an old one, or a board for a schematic that has no PCB yet.
---

# Start a new project

`K` is `kicad-cli` and `KPY` is KiCad's bundled Python (paths in `kicad-view` and `kicad-board-edit`). Write
helper scripts in `<scratch>`, never in the project. Ask the user, or take from the design notes:
- board size and shape, and whatever fixes it (enclosure, mounting holes, connectors on edges);
- the layer count (2 is cheapest; take 4 for USB high-speed and faster, dense parts, or a solid ground plane under
  sensitive analog);
- the thickness (1.6 mm unless something dictates otherwise);
- the fab (JLC unless told), and hand or JLC assembly.

## 1. Files

A project is a folder holding `<name>.kicad_pro`, `<name>.kicad_sch` and `<name>.kicad_pcb`, all with the same
stem. The stem is the project name used in schematic instances.

```bash
mkdir -p <project dir>
"$KPY" -I -c "import pcbnew, sys; b = pcbnew.NewBoard(sys.argv[1]); b.Save(sys.argv[1])" <abs path>/<name>.kicad_pcb
```

That writes the board, plus a `.kicad_pro` with KiCad's defaults and a `.kicad_prl` (local view state: don't commit
it). An existing `.kicad_pro` is left as it is. Then write the root schematic, with a fresh UUID:

```
(kicad_sch
	(version 20260306)
	(generator "eeschema")
	(generator_version "10.0")
	(uuid "<new uuid>")
	(paper "A4")
	(title_block
		(title "<title>")
		(date "<YYYY-MM-DD>")
		(rev "1")
	)
	(lib_symbols)
	(sheet_instances
		(path "/"
			(page "1")
		)
	)
	(embedded_fonts no)
)
```

`"$K" sch erc` on it must say "0 violations". Draw the circuit with the `kicad-schematic` skill.

For a **new revision** of an existing board, copy the old project folder whole (e.g. `rev1/` → `rev2/`), rename the
three files to a new stem only if the user wants a new name, and record the changes in the project's notes.
Library tables using `${KIPRJMOD}/..` keep working as long as the folder depth stays the same.

## 2. Libraries

KiCad's stock libraries come from the user's global tables. Add project tables only for project libraries, beside
the `.kicad_pro`:

```
(fp_lib_table
  (version 7)
  (lib (name "MyProject")(type "KiCad")(uri "${KIPRJMOD}/MyProject.pretty")(options "")(descr "Project footprints"))
)
```

`sym-lib-table` is the same with `sym_lib_table` and a `.kicad_sym` file. Creating the parts themselves: see
`kicad-library`.

## 3. Layers, thickness, rules, net classes

With the board closed, using KiCad's Python for layers and thickness:

```python
import pcbnew, sys
b = pcbnew.LoadBoard(sys.argv[1])
b.SetCopperLayerCount(4)                                   # 2, 4, 6...
ls = b.GetEnabledLayers(); ls.addLayer(pcbnew.In1_Cu); ls.addLayer(pcbnew.In2_Cu); b.SetEnabledLayers(ls)
b.GetDesignSettings().SetBoardThickness(pcbnew.FromMM(1.6))
b.Save(sys.argv[1])
```

KiCad 10.0's Python can't edit the physical stackup table (dielectric thicknesses, materials). For JLC, the stackup
is picked on the order page. Write the one chosen (for example JLC's standard 4-layer stackup, by its name) into
the design notes, and size impedance-controlled tracks from JLC's calculator for it (`kicad-routing`).

Rules and net classes are JSON in the `.kicad_pro` (`board.design_settings.rules`, `net_settings.classes`,
`net_settings.netclass_patterns`). Set them as `kicad-routing` describes:
- minimums at or above the fab's limits (`kicad-check`);
- a Default class for signals;
- a power class for the supply nets.

Write a `<name>.kicad_dru` for anything Board Setup can't express, comments on their own lines.

## 4. Outline, mounting holes, pours

With the board closed, using KiCad's Python. This example draws a W × H rectangle with corner radius R at (X0, Y0),
four M3 holes 3.5 mm in from the corners, and GND pours on both outer layers:

```python
import pcbnew, sys
path = sys.argv[1]
W, H, X0, Y0, R = 40.0, 30.0, 100.0, 100.0, 1.0           # mm
SHARE = "/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints"   # Linux /usr/share/kicad/footprints
b = pcbnew.LoadBoard(path); mm = pcbnew.FromMM

def seg(a, c):
    s = pcbnew.PCB_SHAPE(b, pcbnew.SHAPE_T_SEGMENT); s.SetLayer(pcbnew.Edge_Cuts); s.SetWidth(mm(0.05))
    s.SetStart(pcbnew.VECTOR2I(mm(a[0]), mm(a[1]))); s.SetEnd(pcbnew.VECTOR2I(mm(c[0]), mm(c[1]))); b.Add(s)

def arc(center, start):                                    # a 90° arc from start, turning clockwise on screen
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
    fp.SetReference(f"H{i}"); fp.SetBoardOnly(True)        # not in the schematic: keeps the parity check quiet
    fp.SetPosition(pcbnew.VECTOR2I(mm(x), mm(y))); b.Add(fp)

gnd = next((p.GetNet() for p in b.GetPads() if p.GetNetname() == "GND"), None)   # needs a part on GND already
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

- **Outline:** it must close exactly, end to end. Use 0.05 mm lines on Edge.Cuts.
- **Arcs:** a positive angle turns clockwise on screen (board y points down). Each corner above starts where the
  straight edge before it (going clockwise round the board) ends. Check the result with DRC: it reports
  `invalid_outline` if the outline doesn't close.
- **Mounting holes, fiducials, logos:** mark them board-only, as above. Pick hole sizes for the screws (M2.5 →
  2.7 mm, M3 → 3.2 mm) and keep copper away from them, or use a `_Pad` variant tied to GND when the chassis should
  be grounded.
- **Pours:** a pour needs its net to exist on the board. Run this after the parts are in (step 5), or add the pours
  later through the API (`kicad-board-edit`). The pour outline can be the board rectangle: the fill keeps its
  edge clearance by itself.
- **Fixed parts:** connectors at the edge and anything the enclosure dictates go in before anything else. Place
  and lock them (`kicad-placement`).

## 5. Parts onto the board

When the schematic is drawn and ERC is clean, run `sch_to_board.py` from the `kicad-board-edit` skill on the empty
board. It adds every part with its nets, in a row at the given position outside the outline. Then:
1. place them (`kicad-placement`);
2. route (`kicad-routing`);
3. check (`kicad-check`): no errors, nothing unconnected, no parity issues.

## 6. Project housekeeping

- **`.gitignore`:**
  ```
  *.kicad_prl
  ~*.lck
  .history/
  *-backups/
  fp-info-cache
  ```
- **Jobsets:** copy `jlc-fab.kicad_jobset` (`kicad-fab-export`) and, for JLC assembly, `jlc-assembly.kicad_jobset`
  (`kicad-assembly-export`) into the project, and set the zip name.
- **Design notes:** start `DESIGN.md` beside the project. It holds:
  - the board's purpose and environment (supplies, what each connector can see: `kicad-design-review` checks
    against it);
  - the layer count, stackup and fab choice;
  - placement and routing decisions with their reasons;
  - decisions the user accepted.
- **Test plan:** start one with `kicad-bringup` once the schematic settles.
- **Agent notes:** if the project has a CLAUDE.md or AGENTS.md, note which skills it uses and the `kicad-cli` path.
