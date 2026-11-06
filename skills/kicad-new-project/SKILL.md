---
name: kicad-new-project
description: "Create a new KiCad 10 project without opening KiCad, using the scripts in kicad-schematic and kicad-board-edit: schematic and board files, layer count, thickness, design rules and net classes, rounded outline, mounting holes, parts from the schematic, ground pours, libraries, jobsets and .gitignore. Use when the user wants a new board, a new revision of an existing one, or a PCB for a schematic that doesn't have one yet."
---

# Start a new project

`KPY` is KiCad's bundled Python, and `board.py` is in `kicad-board-edit`'s folder (see that skill). `sch.py` is in
`kicad-schematic`'s folder.

Get these from the user or the design notes:
- **Board:** size and shape, and what fixes them (the enclosure, holes, edge connectors).
- **Layers:** 2 by default. Use 4 for USB high-speed or faster links, for dense parts, or when sensitive analog needs a
  solid plane.
- **Thickness:** 1.6 mm unless something requires otherwise.
- **Fab and assembly:** JLC unless told otherwise, and whether assembly is by hand or by JLC.

## Steps

The project name is the shared stem of the `.kicad_pro`, `.kicad_sch` and `.kicad_pcb` files.

1. **Board, project and outline:**

   ```bash
   "$KPY" -I <board-edit dir>/board.py new <dir>/<name>.kicad_pcb 50 30 --holes M3
   ```

   This writes the board with a rounded 50 × 30 mm outline at (100, 100), four M3 holes 3 mm in from the corners
   (board-only, so parity ignores them), and a default `.kicad_pro`. For 4 layers or another thickness, call
   `new_board(path, w, h, layers=4, thickness=1.6, holes="M2.5")` from a script. KiCad 10.0's Python can't edit
   the stackup table, so record JLC's stackup choice (made on the order page) in the design notes.

2. **Rules and net classes:**

   ```bash
   "$KPY" -I <board-edit dir>/board.py rules <dir>/<name>.kicad_pro --power +5V,+3V3,GND --power-width 0.5
   ```

   This sets minimums at or above JLC's limits, a 0.2/0.25 mm Default class, and a Power class. For other classes,
   call `set_rules(pro, classes={...})`. See `kicad-routing` for widths, and for `.kicad_dru` rules (DRC doesn't
   enforce class widths by itself).

3. **Schematic:** `Schematic.new("<dir>/<name>.kicad_sch", title=..., date=...)`, then draw it with
   `kicad-schematic`. ERC must be clean before the next step.

4. **Parts onto the board:** run `"$KPY" -I board.py sync <dir>/<name>.kicad_pcb`. It adds every part, with its
   nets, in a row below the outline.

5. **Place, pour and route:**
   - Place the parts (`kicad-placement`).
   - Add the pours: `b.zone("GND", ["F.Cu", "B.Cu"])`. A pour needs its net on the board, so do this after sync.
   - Route (`kicad-routing`).
   - Check (`kicad-check`).

For a new revision, copy the whole old folder (e.g. `rev1/` to `rev2/`). Library paths that use `${KIPRJMOD}/..` keep
working as long as the folder depth stays the same.

## Libraries

Stock libraries come from the global tables. Add project tables only for the project's own libraries:

```
(fp_lib_table
  (version 7)
  (lib (name "MyProject")(type "KiCad")(uri "${KIPRJMOD}/MyProject.pretty")(options "")(descr "Project footprints"))
)
```

`sym-lib-table` uses the same format, with `sym_lib_table` and a `.kicad_sym` file. Both scripts read the project's
tables first. To make the parts themselves, see `kicad-library`.

## Mechanical choices

- **Holes:** 2.7 mm for M2.5 and 3.2 mm for M3. Use a `_Pad` variant on GND if the chassis should be grounded
  (`b.add_footprint("H1", "MountingHole:MountingHole_3.2mm_M3_Pad", x, y)`).
- **Fixed parts:** place and lock edge connectors and enclosure-dictated parts first (`kicad-placement`).
- **Odd shapes:** for anything other than a rounded rectangle, draw segments and arcs on Edge.Cuts. The outline must
  close exactly, or DRC reports `invalid_outline`.

## Housekeeping

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
- **CLAUDE.md or AGENTS.md:** if the project has one, note the skills it uses and the `KPY` path.
