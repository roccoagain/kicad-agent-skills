---
name: kicad-board-edit
description: "Edit a KiCad 10 PCB with board.py, a small library in this skill's folder run with KiCad's bundled Python: create the board and outline, bring parts in from the schematic (sync), place and rotate parts, add tracks, vias, pours and holes by pad, change pad nets, place silkscreen references, then refill and DRC on save. Use for any edit to a .kicad_pcb, or after a schematic change. For deciding where parts go or how to route, see kicad-placement and kicad-routing."
---

# Edit a board

Make every change with `board.py` (this skill's folder), from a short script in `<scratch>`. Run it with KiCad's
bundled Python (`KPY`):

| OS | `KPY` |
|---|---|
| macOS | `/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3` |
| Linux | the system `python3` that can `import pcbnew` |
| Windows | `C:\Program Files\KiCad\10.0\bin\python.exe` |

Run scripts as `"$KPY" -I script.py`. Ignore the "create wxApp" assertion and the swig "memory leak" lines; they're
harmless.

```python
import sys; sys.path.insert(0, "<skill dir>")
from board import Board

b = Board("board.kicad_pcb")                      # refuses if the board is open in KiCad
b.place("C3", 119.6, 115.35, rot=270)             # mm; degrees CCW; side="B" flips. Keeps 3D models
b.score()                                         # placement metrics after the moves above (no save needed)
b.connect(("C3", "1"), ("U2", "4"))               # net, class width and layer from the pads; one 45° bend per leg
b.connect(("U2", "9"), (115.7, 105.6), ("J1", "2"), first="diagonal")   # through a waypoint; "x"/"y": 90° elbow
b.track("/SDA", [("U2", "11"), (119.0, 112.6), (128.9, 112.6)], layer="B.Cu")   # every corner explicit
P = b.pad                                         # P("U2", "4") -> (x, y), after the moves above
b.via(119.0, 112.6, "/SDA")                       # 0.6 / 0.3 mm
b.gnd_via("C3", "2", dx=0, dy=1.2)                # via plus a stub from the pad
b.zone("GND", ["F.Cu", "B.Cu"], pads="solid")     # pour over the outline; "thermal" (default) for hand soldering
b.set_pad_net("J2", "2", "/NRST")                 # only after the same change in the schematic
b.remove_tracks(nets=["/SDA"], region=(115, 110, 135, 120))   # or nets=["*"]; b.remove_zones()
b.label("C3", 119.6, 113.2)                       # silkscreen reference, upright; b.auto_labels() for all
b.text("SNIFFER rev 2", 121, 103.5, layer="B.SilkS")   # free text; mirrored on the back
b.outline(36, 19, 100, 100, r=1.0); b.add_footprint("H1", "MountingHole:MountingHole_2.2mm_M2", 102.5, 102.5)
b.remove_footprint("J1"); b.remove_outline(); b.remove_texts()   # removals, for replacing or rerunning
b.save()                                          # writes, refills zones, prints DRC with parity
```

Command line, with `KPY`:
- `board.py pads board.kicad_pcb [REF ...]`: each part's position, and every pad's centre, size and net. Plan from
  this.
- `board.py score board.kicad_pcb [--skip GND]`: airwire length per net and per part, airwire crossings, courtyard
  overlaps, parts near or past the edge, and how much of the board the parts cover. Poured nets are skipped.
- `board.py sync board.kicad_pcb`: "Update PCB from Schematic". It adds missing parts below the board, copies
  values, fields and DNP/BOM flags, moves unrouted pads to new nets, and restores lost 3D models. It reports
  footprint changes, routed pads on changed nets, and parts the schematic lacks.
- `board.py new board.kicad_pcb W H --holes M3`: a new board with a rounded W × H outline at (100, 100) and four
  mounting holes.

Lengths are mm in board coordinates (y down). Points are `(x, y)` or a pad `(ref, num)`. Track widths default to
the net's class in the `.kicad_pro`. A two-pad part at 0° has pad 1 on the left; at 90°, pad 1 is below;
at 270°, above.

## Rules

- **One save per process.** In KiCad 10's bindings, objects read after anything is added or removed come back
  broken. So `board.py` queues tracks, vias, zones and removals until `save()`. Read every pad position before
  saving, and start a new process for the next edit. Keep placement and routing in separate scripts.
- **Editor closed.** The editor's next save overwrites the file, so ask the user to save and close the board first.
- **Schematic first.** Anything the schematic owns changes there first, then `board.py sync`: parts, footprints,
  values, fields and pin swaps. Nets come only from the schematic; `board.py` can't invent one.
- **Clean git tree** before each edit, so it's one diff. Never commit edit scripts: replaying one later undoes newer
  work.
- **Rerunnable scripts.** Keep one placement script and one routing script per layout job, each starting with
  the removals that undo its own output: `remove_outline()`, `remove_texts()` and holes for placement;
  `remove_tracks(nets=["*"])` and `remove_zones()` for routing. Then each fix is an edit to the script and a rerun
  of placement, then routing.
- **Footprint changes:** after changing a part's footprint in the schematic, `remove_footprint()` the old part in
  one process, then `board.py sync` adds the new one with its nets.
- **Plan from numbers.** Take positions from `pads`, not from a picture. Keep tracks at 0°/45°/90°, leaving one
  clearance plus half a track width from other copper.

## After each edit

1. Read the DRC summary `save()` prints. While placing, unconnected items are expected; nothing else is.
2. Look at the change: `view.py pcb board.kicad_pcb --around U2` (`kicad-view`).
3. Run the full check before committing (`kicad-check`): ERC, DRC, and JLC's limits.
4. Update the design notes if they describe placement or routing.

If the user wants to watch edits live in an open editor, KiCad's IPC API (`kicad-python`) can make them instead, but
`board.py` doesn't use it. Save and close in the editor, edit with `board.py`, then reopen.
