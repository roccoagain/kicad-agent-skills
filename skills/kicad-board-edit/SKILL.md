---
name: kicad-board-edit
description: "Make changes to a KiCad 10 PCB through KiCad's IPC API: move, rotate or flip parts, add or delete tracks, vias, pours and keep-outs, change pad nets, refill zones. Also updates the board from the schematic (new parts, values, footprints). Use for any edit to a .kicad_pcb, or after a schematic change. For deciding where parts go or how to route, see kicad-placement and kicad-routing."
---

# Edit a board through the API

Use KiCad's own interfaces, and never edit `.kicad_pcb` text by hand:
- **IPC API** (`kicad-python`): for edits.
- **Bundled `pcbnew` module:** for what the API can't do, such as adding parts from the schematic.
- **`kicad-cli`:** for checks.

Write each edit as a one-off script in `<scratch>`. For where parts go, see `kicad-placement`. For routing, see
`kicad-routing`.

## Setup

- **API server:** it must be on. Ask the user to turn on Preferences → Plugins → "Enable KiCad API". This sets
  `"api": {"enable_server": true}` in `kicad_common.json`, in `~/Library/Preferences/kicad/10.0/`,
  `~/.config/kicad/10.0/`, or `%APPDATA%\kicad\10.0\`.
- **Running scripts:** `uv run --no-project --with kicad-python python -I <scratch>/edit.py`. Tested with
  kicad-python 0.8.0.
- **`KPY`, KiCad's own Python:**
  - macOS: `/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3`
  - Linux: the system `python3` that can `import pcbnew`
  - Windows: `C:\Program Files\KiCad\10.0\bin\python.exe`

  It prints a harmless "create wxApp" assertion.

## Each edit

1. **Commit first,** so the edit is one diff.
2. **Open the board in the editor.**
   - If `~<board>.kicad_pcb.lck` exists, the board is already open. Use that instance.
   - Otherwise, open it:
     - macOS: `open -g -a "/Applications/KiCad/PCB Editor.app" <abs path>/board.kicad_pcb`
     - Linux and Windows: run `pcbnew <board>` in the background.
   - Wait for both the lock file and the socket to appear.
3. **Find the socket.**
   - Location:
     - macOS and Linux: `/tmp/kicad/`
     - Windows: `%TEMP%\kicad\`
     - Flatpak: `~/.var/app/org.kicad.KiCad/cache/tmp/kicad/`
   - Name: `api.sock` if only one KiCad is running, otherwise `api-<pid>.sock` (get the pid with `pgrep -f pcbnew`).
   - If board calls fail with "no handler available", you've connected to the project manager, not the PCB editor.
4. **Run the script.**
5. **Save with `b.save()`** before anything else. Quitting discards unsaved changes without asking. Then quit, unless
   the user is watching: `osascript -e 'tell application "PCB Editor" to quit'`.
6. **Run `sch_to_board.py`** (editor closed) if you rotated or flipped a part, or if the schematic changed. It restores
   dropped 3D models.
7. **Check.** View the change (`kicad-view`), run DRC with parity (`kicad-check`), update the design notes, and commit.

```python
from kipy import KiCad
from kipy.board_types import Track, Via, Zone, ZoneType
from kipy.geometry import Angle, Vector2, PolygonWithHoles, PolyLine, PolyLineNode
from kipy.util.units import from_mm, to_mm
from kipy.proto.board.board_types_pb2 import BoardLayer, ZoneConnectionStyle

k = KiCad(socket_path="ipc:///tmp/kicad/api.sock")
b = k.get_board()
fps = {f.reference_field.text.value: f for f in b.get_footprints()}
nets = {n.name: n for n in b.get_nets()}

for p in fps["U2"].definition.pads:                       # absolute positions
    print(p.number, p.net.name, to_mm(p.position.x), to_mm(p.position.y))

c = b.begin_commit()
r7 = fps["R7"]                                            # all changes to one footprint, then ONE update
r7.position = Vector2.from_xy(from_mm(125.6), from_mm(79.0))
r7.orientation = Angle.from_degrees(90)
r7.definition.pads[0].net = nets["GND"]
b.update_items([r7])

t = Track()
t.start, t.end = Vector2.from_xy(from_mm(102), from_mm(80)), Vector2.from_xy(from_mm(104), from_mm(80))
t.width, t.layer, t.net = from_mm(0.25), BoardLayer.BL_F_Cu, nets["GND"]
v = Via()
v.position, v.net = Vector2.from_xy(from_mm(104), from_mm(80)), nets["GND"]
v.diameter, v.drill_diameter = from_mm(0.6), from_mm(0.3)     # required: defaults are 0

z = Zone()
z.layers, z.net, z.priority = [BoardLayer.BL_B_Cu], nets["GND"], 1
outline = PolyLine()
for x, y in [(150, 95), (160, 95), (160, 100), (150, 100)]:
    outline.append(PolyLineNode.from_xy(from_mm(x), from_mm(y)))
outline.closed = True
shape = PolygonWithHoles(); shape.outline = outline
z.outline = shape
z.clearance = from_mm(0.3)
conn = z.proto.copper_settings.connection                 # required: thermal gap/spokes default to 0
conn.zone_connection = ZoneConnectionStyle.ZCS_THERMAL
conn.thermal_spokes.gap.value_nm = from_mm(0.5)
conn.thermal_spokes.width.value_nm = from_mm(0.5)

keepout = Zone()
keepout.type = ZoneType.ZT_RULE_AREA
keepout.layers, keepout.name = [BoardLayer.BL_F_Cu, BoardLayer.BL_B_Cu], "no copper under the jack"
keepout.outline = shape
ra = keepout.proto.rule_area_settings
ra.keepout_tracks = ra.keepout_vias = ra.keepout_copper = True

b.create_items([t, v, z, keepout])
b.push_commit(c, "Move R7, GND stub, pour, keep-out")    # one undo step

c = b.begin_commit()
b.remove_items([tr for tr in b.get_tracks() if tr.net.name == "/OLD_NET"])
b.push_commit(c, "Remove /OLD_NET tracks")

b.refill_zones()
b.save()
```

**API notes** (kicad-python 0.8, KiCad 10.0)
- **Units:** lengths are integer nm, so convert with `from_mm` and `to_mm`. y points down.
- **Rotation:** +90 is counter-clockwise. A two-pad part at 0° has pad 1 on the left.
- **Reading:** `get_tracks`, `get_vias`, `get_pads`, `get_zones`, `get_shapes` (includes Edge.Cuts), `get_text`,
  `get_items_by_net`, `get_netclass_for_nets`, `get_stackup`, `get_copper_layer_count`.
- **Writing:** `create_items`, `update_items`, `remove_items`, `flip_items`. After any write, re-read items instead of
  reusing the old objects.
- **Board graphics:** use `BoardSegment()` with `start`, `end`, `layer` and `attributes.stroke.width`.
- **Nets:** the API can't create a net. Add it in the schematic, then run `sch_to_board.py`.
- **Values and fields:** change them in the schematic, then run `sch_to_board.py`.
- **Layer names:** `get_layer_name()` returns long names (`F.Silkscreen`), but `kicad-cli` wants canonical ones
  (`F.SilkS`).

## Traps in KiCad 10.0.5

- **Update each footprint once per commit.** A second `update_items` on the same footprint within one commit saves a
  duplicate copy with the same reference and UUID, even if you re-read it in between.
- **Rotating drops the 3D model.** Moving doesn't. Restore the model with `sch_to_board.py`, and never by editing
  `definition` items.
- **`z.connection.thermal_spokes` returns a copy,** so setting values on it does nothing. Set them through
  `z.proto.copper_settings.connection`.
- **Updating a footprint drops its `(units ...)` block.** This is harmless and shows only in the diff.
- **Quitting discards unsaved work** without a prompt.

## Board from schematic: sch_to_board.py

The API can't load footprints, and `kicad-cli` can't update a board. `sch_to_board.py`, in this skill's folder, does
"Update PCB from Schematic" with `pcbnew`:
- adds missing parts, with their nets;
- copies values, fields and the DNP, BOM and position-file flags;
- restores 3D models;
- reports, without changing anything: footprint changes, pad-net changes, and parts the schematic doesn't have.

It was tested on a 58-part board: zero parity issues.

1. Change the schematic first.
2. Save the board and close the editor.
3. Run it:

   ```bash
   cp <skill dir>/sch_to_board.py <scratch>/
   "$K" sch export netlist -o <scratch>/net.net board.kicad_sch
   "$KPY" -I <scratch>/sch_to_board.py <abs path>/board.kicad_pcb <scratch>/net.net 20 20   # new parts in a row from (20, 20) mm
   ```

4. Act on its output:
   - **added:** place and route the new parts.
   - **CHECK: schematic says X, board has Y:** delete the old part and its tracks with the API, then re-run the script.
   - **CHECK: pad n: board net A, schematic B:** re-route that pad. Renamed nets keep their old name on tracks until you
     change them. On a pad with no tracks yet, fix it with `pcbnew` (editor closed):
     `pad.SetNet(board.FindNet("/NRST"))`, then save.
   - **CHECK: not in the schematic:** delete the part, or call `fp.SetBoardOnly(True)` if it's mechanical.
5. Run DRC with `--schematic-parity`. It should report no parity issues.

Libraries resolve the way KiCad resolves them: the project's `fp-lib-table` first, then the global table. Environment
variables override the script's defaults. When the API gains footprint loading, switch to the API.

## First placement on a new board

Before anything is routed, placing parts with `pcbnew` and the editor closed is simpler than the API, and needs no
socket: `fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)))`, `fp.SetOrientationDegrees(r)`, then
`board.Save(path)`. Rotating this way keeps the 3D models (checked with `sch_to_board.py`, KiCad 10.0.5). Keep the
positions in a JSON file in `<scratch>` and re-run the script while iterating. Print the pad positions afterwards
for the next step. Use the API once the user has the board open, or for routing edits.

## Rules

- **One writer per board.** Never run `pcbnew` scripts while the board is open in the editor.
- **Never commit edit scripts.** Replaying one later would undo newer work.
- **Schematic first.** Anything the schematic owns changes there first: parts, footprints, values, fields and pin swaps.
