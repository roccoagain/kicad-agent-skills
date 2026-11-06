---
name: kicad-board-edit
description: Change a KiCad 10 PCB without the user touching KiCad - move, rotate or flip parts, add or remove tracks, vias, pours and keep-outs, change pad nets, refill zones - through KiCad's official IPC API with the kicad-python library, from a throwaway script kept outside the project; and bring the board in line with the schematic (new parts, values, fields, footprints) with the sch_to_board.py template in this skill's folder. Covers launching the PCB editor yourself, finding its API socket, the API's traps in KiCad 10.0 (duplicated footprints, lost 3D models, zero-size thermals), and checking the result. Use whenever the user asks for placement, routing or part changes on a .kicad_pcb, or after a schematic change that the board must follow.
---

# Edit a KiCad board through its API

Do the edit yourself: the user doesn't open KiCad. Use KiCad's own interfaces only:
- the IPC API, through the official `kicad-python` library, for edits;
- KiCad's bundled `pcbnew` Python module, for what the 10.0 API can't do (adding parts from the schematic);
- `kicad-cli` for checks and zone fills.

Don't edit `.kicad_pcb` text by hand. Each edit is a short script in a temporary folder outside the project
(`<scratch>`), run once. For where parts should go, see `kicad-placement`. For how to route, see `kicad-routing`.

## One-time setup

- **The API server.** KiCad 10 needs it on: Preferences → Plugins → "Enable KiCad API". That's
  `"api": {"enable_server": true}` in `kicad_common.json` (macOS:
  `~/Library/Preferences/kicad/10.0/kicad_common.json`; Linux: `~/.config/kicad/10.0/`; Windows:
  `%APPDATA%\kicad\10.0\`). If it's off, ask the user to turn it on. It's their settings file.
- **`uv`** (or a venv with `pip install kicad-python`). Scripts run as
  `uv run --no-project --with kicad-python python -I <scratch>/edit.py`. Nothing is installed in the project.
  Tested with kicad-python 0.8.0.
- **KiCad's own Python**, for `sch_to_board.py` and other `pcbnew` scripts (`KPY` below):
  - macOS: `/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3`
  - Linux: the system `python3` that can `import pcbnew`
  - Windows: `C:\Program Files\KiCad\10.0\bin\python.exe`

  It prints a harmless "create wxApp before calling this" assertion.

## Each edit

1. **Start from a clean git tree** (commit first), so the edit is one reviewable diff.
2. **Open the board in the PCB editor.** A `~<board>.kicad_pcb.lck` beside the board means it's already open:
   edit that instance (ask the user which one, if unsure), and don't open a second copy. Otherwise:
   - macOS: `open -g -a "/Applications/KiCad/PCB Editor.app" <abs path>/board.kicad_pcb`
   - Linux/Windows: run `pcbnew <board>` in the background.

   It takes a few seconds. Wait until both the lock file and the socket exist.
3. **Find its socket:**
   - macOS/Linux: `/tmp/kicad/`
   - Windows: `%TEMP%\kicad\`
   - Flatpak: `~/.var/app/org.kicad.KiCad/cache/tmp/kicad/`

   If it's the only KiCad running, the socket is `api.sock`. If another KiCad is open, the editor gets
   `api-<pid>.sock` (`pgrep -f pcbnew` gives the pid). A project manager on its own answers `get_version()` but
   has no board: board calls fail with "no handler available".
4. **Run a script** (below).
5. **Save** (`b.save()`) before anything else. Quitting the editor discards unsaved changes without asking. Then
   quit, unless the user wants to watch: `osascript -e 'tell application "PCB Editor" to quit'` on macOS.
6. **If the script rotated or flipped any footprint, or the schematic changed,** run `sch_to_board.py` (below) with
   the editor closed. It puts back the 3D models the API dropped.
7. **Check:** view the change (`kicad-view` skill), run DRC with parity (`kicad-check` skill), and update the
   project's design notes if they describe placement or routing. Then commit.

```python
# <scratch>/edit.py: illustration; refs, nets and coordinates stand for whatever the change needs.
from kipy import KiCad
from kipy.board_types import Track, Via, Zone, ZoneType
from kipy.geometry import Angle, Vector2, PolygonWithHoles, PolyLine, PolyLineNode
from kipy.util.units import from_mm, to_mm
from kipy.proto.board.board_types_pb2 import BoardLayer, ZoneConnectionStyle

k = KiCad(socket_path="ipc:///tmp/kicad/api.sock")      # or api-<pid>.sock
b = k.get_board()
fps = {f.reference_field.text.value: f for f in b.get_footprints()}
nets = {n.name: n for n in b.get_nets()}

for p in fps["U2"].definition.pads:                       # read before deciding: pad positions are absolute
    print(p.number, p.net.name, to_mm(p.position.x), to_mm(p.position.y))

c = b.begin_commit()
r7 = fps["R7"]                                            # every change to one footprint, then ONE update:
r7.position = Vector2.from_xy(from_mm(125.6), from_mm(79.0))   # mm -> KiCad's nm
r7.orientation = Angle.from_degrees(90)                   # (rotating drops the 3D model: see the traps)
r7.definition.pads[0].net = nets["GND"]                   # a pad's net changes through its footprint
b.update_items([r7])

t = Track()
t.start, t.end = Vector2.from_xy(from_mm(102), from_mm(80)), Vector2.from_xy(from_mm(104), from_mm(80))
t.width, t.layer, t.net = from_mm(0.25), BoardLayer.BL_F_Cu, nets["GND"]
v = Via()
v.position, v.net = Vector2.from_xy(from_mm(104), from_mm(80)), nets["GND"]
v.diameter, v.drill_diameter = from_mm(0.6), from_mm(0.3)     # required: a new Via is size 0 otherwise

z = Zone()                                                # a copper pour
z.layers, z.net, z.priority = [BoardLayer.BL_B_Cu], nets["GND"], 1
outline = PolyLine()
for x, y in [(150, 95), (160, 95), (160, 100), (150, 100)]:
    outline.append(PolyLineNode.from_xy(from_mm(x), from_mm(y)))
outline.closed = True
shape = PolygonWithHoles(); shape.outline = outline
z.outline = shape
z.clearance = from_mm(0.3)
conn = z.proto.copper_settings.connection                 # thermal reliefs: a new Zone has 0 mm gap and spokes
conn.zone_connection = ZoneConnectionStyle.ZCS_THERMAL
conn.thermal_spokes.gap.value_nm = from_mm(0.5)
conn.thermal_spokes.width.value_nm = from_mm(0.5)

keepout = Zone()                                          # a keep-out (rule area)
keepout.type = ZoneType.ZT_RULE_AREA
keepout.layers, keepout.name = [BoardLayer.BL_F_Cu, BoardLayer.BL_B_Cu], "no copper under the jack"
keepout.outline = shape
ra = keepout.proto.rule_area_settings
ra.keepout_tracks = ra.keepout_vias = ra.keepout_copper = True

b.create_items([t, v, z, keepout])
b.push_commit(c, "Move R7, GND stub, pour, keep-out")    # one commit = one undo step in the editor

c = b.begin_commit()                                      # removing: pass the items (fresh from a get_*)
old = [tr for tr in b.get_tracks() if tr.net.name == "/OLD_NET"]
b.remove_items(old)
b.push_commit(c, "Remove /OLD_NET tracks")

b.refill_zones()
b.save()                                                  # always: quitting the editor discards unsaved work
```

API notes (kicad-python 0.8, KiCad 10.0):
- Lengths are integer nanometres: `from_mm`/`to_mm`. Coordinates are KiCad board mm with y down, the same as DRC.
- **Reading:** `b.get_tracks()`, `get_vias()`, `get_pads()`, `get_zones()`, `get_shapes()` (board graphics,
  including the Edge.Cuts outline), `get_text()`, `get_items_by_net(...)`, `get_netclass_for_nets(...)`,
  `get_stackup()`, `get_copper_layer_count()`.
- **Writing:** `create_items`, `update_items`, `remove_items` and `flip_items`. `help(...)` on any class shows its
  fields.
- Rotation follows KiCad: +90 is counter-clockwise. A 2-pad part at 0° has pad 1 on the left.
- **Values and fields:** `fp.value_field.text.value = "10k"`, and for a custom field, set `t.text.value` on the item
  in `fp.texts_and_fields` whose `t.name` matches. Change the schematic first, though: the board must match it,
  and `sch_to_board.py` carries schematic values and fields over for you.
- **Board graphics:** `BoardSegment()` with `start`, `end`, `layer` (e.g. `BoardLayer.BL_Edge_Cuts`) and
  `attributes.stroke.width`. An outline must close exactly, end to end.
- Re-read items after a write, rather than reusing old objects.
- The API has no "create net" call. A new net needs a pad to carry it: change the schematic first, then run
  `sch_to_board.py`.
- `get_layer_name()` returns the long names (`F.Silkscreen`). `kicad-cli` wants the canonical ones (`F.SilkS`).

## Traps in KiCad 10.0.5 (all reproduced)

- **One `update_items` per footprint per commit.** Updating the same footprint twice between `begin_commit()` and
  `push_commit()` saves a second copy of it, with the same reference and UUID. That happens even if you re-read it
  in between. Make every change to the footprint first, then update it once, or use separate commits. Tracks and
  zones don't have this problem.
- **Rotating a footprint drops its 3D model.** A move alone keeps it. Run `sch_to_board.py` afterwards, which
  restores models from the library. Never repair a footprint by editing its `definition` items through the API:
  that is what produces duplicates.
- **A new `Zone()` has a 0 mm thermal gap and spoke width.** Set them through `z.proto.copper_settings.connection`,
  as in the example. `z.connection.thermal_spokes` returns a copy, so setting `gap` or `width` on it changes
  nothing.
- **Any footprint update drops its `(units ...)` block** (KiCad 10's pin-to-unit list) from the saved file. It shows
  in the diff and is harmless: DRC, parity and the outputs don't use it.
- **Quitting discards.** `osascript ... quit` closes the editor without a save prompt.

## Bringing the board in line with the schematic (new parts, values, footprints)

KiCad 10.0's API can't load a footprint from a library, and `kicad-cli` can't update a board from its schematic.
`sch_to_board.py`, in this skill's folder, does what the editor's "Update PCB from Schematic" does, with KiCad's
bundled `pcbnew` module:
- it adds missing parts with their nets and symbol links;
- it copies values, fields and DNP/BOM/position-file flags;
- it restores lost 3D models;
- it reports, without changing, footprints that differ, pads on another net, and parts the schematic lacks.

It's tested with KiCad 10.0.5: on a real 58-part board it reproduced the board exactly, with zero parity issues.

1. Put the change in the schematic first (`kicad-schematic` skill).
2. Close the board in the editor (save, then quit).
3. Run it:

```bash
cp <skill dir>/sch_to_board.py <scratch>/                  # <skill dir>: this SKILL.md's folder
"$K" sch export netlist -o <scratch>/net.net board.kicad_sch   # export it fresh, right before
"$KPY" -I <scratch>/sch_to_board.py <abs path>/board.kicad_pcb <scratch>/net.net 20 20   # new parts in a row from (20, 20) mm
```

4. Read its output:
   - **added:** the new parts. Place them (`kicad-placement`, then the API) and route them.
   - **CHECK: … schematic says X, board has Y:** a footprint change. Delete the old part (and its tracks) with the
     API, run the script again to add the new one, then place and route it.
   - **CHECK: … pad n: board net A, schematic B:** a connection change. Re-route that pad: change its net, remove
     the tracks that now connect the wrong nets, add new ones. If a whole net was renamed, the tracks keep the old
     name until you change them.
   - **CHECK: … not in the schematic:** delete the part, or mark it board-only if it's mechanical (mounting
     holes, fiducials, logos): `fp.SetBoardOnly(True)` with `pcbnew`.
5. Run DRC with `--schematic-parity` (`kicad-check`). The parity section must be empty.

Libraries resolve as KiCad does: the project's `fp-lib-table` first, then the user's global one, with `${KIPRJMOD}`
and `${KICAD10_FOOTPRINT_DIR}` expanded. Environment variables override the script's defaults. For a part from a
library the user hasn't installed, see `kicad-library`.

The `pcbnew` module is deprecated in favour of the API. When KiCad adds footprint loading to the API (or a headless
`kicad-cli api-server`), switch to that.

## Rules

- One writer per board: never edit with the API while another process (or the user) is changing the same board,
  and never run `pcbnew` scripts while the board is open in the editor.
- Never commit an edit script. It describes one change, and replaying it later would undo newer work.
- Change the schematic first for anything the schematic owns (parts, footprints, values, fields, pin swaps), then
  the board.
