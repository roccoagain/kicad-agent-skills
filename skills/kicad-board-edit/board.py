"""Edit a KiCad 10 board from a short script, run with KiCad's bundled Python, with the board closed in KiCad.

    import sys; sys.path.insert(0, "<this skill's folder>")
    from board import Board

    b = Board("board.kicad_pcb")
    b.place("C3", 119.6, 115.35, rot=270)                   # mm, degrees CCW; side="B" flips
    print(b.pad("U2", "4"), b.pads("U2"))                    # pad centres (after any place() so far)
    b.connect(("C3", "1"), ("U2", "4"))                     # net, width and layer from the pads; one 45° bend
    b.track("/SDA", [("U2", "9"), (120.4, 115.0), (128.9, 115.0)], layer="B.Cu")   # explicit corners
    b.via(118.75, 117.1, "GND")                              # 0.6 / 0.3 mm by default
    b.gnd_via("C3", "2", dx=-0.9, dy=0)                      # via plus a stub from the pad
    b.zone("GND", ["F.Cu", "B.Cu"])                          # pour over the board outline
    b.set_pad_net("J2", "2", "/NRST")                        # after a pin swap made in the schematic
    b.remove_tracks(nets=["/SDA"], region=(120, 110, 135, 120))
    b.remove_tracks(refs=["R3", "D1"])                       # the copper hanging off these parts' pads
    b.label("C3", 119.6, 113.2)                              # silkscreen reference; or b.auto_labels()
    b.score()                                                # placement metrics, before or instead of saving
    b.save()                                                 # writes, refills zones, runs DRC with parity
    b.save(dry_run=True)                                     # or: the same DRC on a temporary copy, file untouched

Command line, with KiCad's bundled Python ("$KPY" -I board.py ...):
    board.py pads board.kicad_pcb [REF ...]                  # pad positions and nets
    board.py tracks board.kicad_pcb [NET ...]                # every track's ends, layer and width, and every via
    board.py nets board.kicad_pcb                            # per net: length, widths, layers, vias, via-to-GND-via
    board.py score board.kicad_pcb [--skip GND]              # airwires, crossings, overlaps, edge, decoupling
    board.py sync board.kicad_pcb [x y]                      # bring the board in line with the schematic
    board.py new board.kicad_pcb W H [--holes M3]            # new board with a rounded outline at (100, 100)
    board.py rules board.kicad_pro [--power +5V,+3V3,GND] [--power-width 0.5]   # JLC minimums, net classes

drc(board, rules="x.kicad_dru", parity=False) runs DRC on a temporary copy against another rule file.

All lengths are mm in board coordinates (y down). Rotation follows KiCad: +90 is counter-clockwise; a two-pad
part at 0° has pad 1 on the left, at 90° below, at 270° above.

One Board per process: in KiCad 10's bindings, objects read after anything is added to or removed from a board come
back broken, for the rest of the process. So places, field changes and labels apply at once, while every add and
remove is queued and applied in save(). Read everything you need (pad positions) before save(), and start a new
process for the next edit.
"""
import fnmatch
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile

import pcbnew

MM, TOMM = pcbnew.FromMM, pcbnew.ToMM
LAYERS = {"F.Cu": pcbnew.F_Cu, "B.Cu": pcbnew.B_Cu, "In1.Cu": pcbnew.In1_Cu, "In2.Cu": pcbnew.In2_Cu,
          "F.SilkS": pcbnew.F_SilkS, "B.SilkS": pcbnew.B_SilkS, "Edge.Cuts": pcbnew.Edge_Cuts}
SHARE = {"darwin": "/Applications/KiCad/KiCad.app/Contents/SharedSupport",
         "linux": "/usr/share/kicad"}.get(sys.platform, r"C:\Program Files\KiCad\10.0\share\kicad")
CONFIG = {"darwin": "~/Library/Preferences/kicad/10.0", "linux": "~/.config/kicad/10.0"}.get(
    sys.platform, os.path.join(os.environ.get("APPDATA", ""), "kicad", "10.0"))


def kicad_cli():
    for p in (os.environ.get("KICAD_CLI"), "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli",
              r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe"):
        if p and os.path.exists(p):
            return p
    return "kicad-cli"


def V(x, y):
    return pcbnew.VECTOR2I(MM(x), MM(y))


def _check_closed(path):
    lock = os.path.join(os.path.dirname(path), "~" + os.path.basename(path) + ".lck")
    if os.path.exists(lock):
        raise RuntimeError(f"{os.path.basename(path)} is open in KiCad ({lock}). Save and close it first: "
                           "its next save would overwrite this edit")


# ----------------------------------------------------------------------------- footprint libraries
def _expand(uri, proj):
    env = {"KIPRJMOD": proj, "KICAD10_FOOTPRINT_DIR": f"{SHARE}/footprints", "KICAD10_3DMODEL_DIR": f"{SHARE}/3dmodels"}
    return re.sub(r"\$\{(\w+)\}", lambda m: os.environ.get(m.group(1), env.get(m.group(1), m.group(0))), uri)


def footprint_libs(proj):
    libs = {}

    def read(path):
        if not os.path.exists(path):
            return
        for m in re.finditer(r'\(lib \(name "([^"]+)"\)\s*\(type "([^"]+)"\)\s*\(uri "([^"]+)"\)', open(path).read()):
            if m.group(2) == "Table":
                read(_expand(m.group(3), proj))
            else:
                libs.setdefault(m.group(1), _expand(m.group(3), proj))
    read(os.path.join(proj, "fp-lib-table"))
    read(os.path.expanduser(f"{CONFIG}/fp-lib-table"))
    stock = f"{SHARE}/footprints"                           # KiCad's stock libraries, if no table names them
    for d in (os.listdir(stock) if os.path.isdir(stock) else []):
        if d.endswith(".pretty"):
            libs.setdefault(d[:-7], f"{stock}/{d}")
    return libs


def load_footprint(fpid, proj):
    lib, name = fpid.split(":", 1)
    libs = footprint_libs(proj)
    fp = pcbnew.FootprintLoad(libs[lib], name) if lib in libs else None
    if fp is None:
        raise KeyError(f"footprint {fpid} not found")
    fp.SetFPID(pcbnew.LIB_ID(lib, name))
    return fp


def _copy_project(src, dst, skip=None):
    """Copy the project folder into dst (sheets and libraries in subfolders included), leaving out version control,
    backups, lock files, fab output and 3D models, which DRC doesn't read."""
    shutil.copytree(src, dst, dirs_exist_ok=True, ignore=shutil.ignore_patterns(
        ".git", ".history", "*-backups", "fab", "~*.lck", "*.step", "*.stp", "*.wrl", *([skip] if skip else [])))


# ----------------------------------------------------------------------------- DRC
def drc(board_path, refill=True, parity=True, rules=None, show=15):
    """Run KiCad's DRC (refilling and saving zones by default); print a summary; return the JSON report.
    rules: a .kicad_dru to check against instead of the project's own (e.g. the fab's limits)."""
    with tempfile.TemporaryDirectory() as d:
        target = board_path
        if rules:                                           # DRC reads <stem>.kicad_dru beside the board
            stem = os.path.splitext(os.path.basename(board_path))[0]
            for ext in (".kicad_pcb", ".kicad_pro"):
                src = os.path.splitext(board_path)[0] + ext
                if os.path.exists(src):
                    open(os.path.join(d, stem + ext), "w").write(open(src).read())
            open(os.path.join(d, stem + ".kicad_dru"), "w").write(open(rules).read())
            target, refill = os.path.join(d, stem + ".kicad_pcb"), False
        out = os.path.join(d, "drc.json")
        cmd = [kicad_cli(), "pcb", "drc", "--format", "json", "--severity-error", "--severity-warning", "-o", out]
        cmd += ["--refill-zones", "--save-board"] if refill else []
        cmd += ["--schematic-parity"] if parity and not rules else []
        r = subprocess.run(cmd + [target], capture_output=True, text=True)
        if not os.path.exists(out):
            raise RuntimeError("DRC failed:\n" + r.stdout + r.stderr)
        rep = json.load(open(out))
    vs, un, par = rep.get("violations", []), rep.get("unconnected_items", []), rep.get("schematic_parity", [])
    errors = [v for v in vs if v["severity"] == "error"]
    print(f"DRC{' (' + os.path.basename(rules) + ')' if rules else ''}: {len(errors)} errors, "
          f"{len(vs) - len(errors)} warnings, {len(un)} unconnected, {len(par)} parity")
    by_type = {}
    for v in vs + par:
        by_type.setdefault((v["severity"], v["type"]), []).append(v)
    for (sev, typ), items in sorted(by_type.items())[:show]:
        first = "; ".join(i["description"] for i in items[0].get("items", []))
        print(f"  {sev} {typ} x{len(items)}: {first}")
    if un:
        nets = sorted({re.sub(r".*\[(.*?)\].*", r"\1", i["description"]) for u in un for i in u.get("items", [])})
        print(f"  unconnected nets: {', '.join(nets[:30])}{' ...' if len(nets) > 30 else ''}")
    return rep


# ----------------------------------------------------------------------------- the board
class Board:
    def __init__(self, path, check_lock=True):
        self.path = os.path.abspath(path)
        if check_lock:
            _check_closed(self.path)
        self.board = pcbnew.LoadBoard(self.path)
        self.fps = {fp.GetReference(): fp for fp in self.board.GetFootprints()}
        self.nets = {}
        for p in self.board.GetPads():
            self.nets.setdefault(p.GetNetname(), p.GetNet())
        for t in self.board.GetTracks():
            self.nets.setdefault(t.GetNetname(), t.GetNet())
        for z in self.board.Zones():
            self.nets.setdefault(z.GetNetname(), z.GetNet())
        self._tracks, self._vias, self._zones, self._removes, self._net_changes, self._shapes = [], [], [], [], [], []
        self._fp_adds, self._fp_removes, self._texts = [], [], []
        self._saved = False

    # ------------------------------------------------------------------ reading
    def _fp(self, ref):
        if self._saved:
            raise RuntimeError("this Board was saved; edit again from a new process")
        if ref not in self.fps:
            raise KeyError(f"no footprint {ref!r} on the board")
        return self.fps[ref]

    def _pad(self, ref, num):
        for p in self._fp(ref).Pads():
            if p.GetNumber() == str(num):
                return p
        raise KeyError(f"{ref} has no pad {num!r}")

    def pad(self, ref, num):
        """(x, y) of a pad's centre, reflecting place() calls so far."""
        q = self._pad(ref, num).GetPosition()
        return (round(TOMM(q.x), 4), round(TOMM(q.y), 4))

    def pads(self, ref):
        """{number: (x, y, net, (w, h) as placed)} for every pad of a footprint."""
        out = {}
        for p in self._fp(ref).Pads():
            q, bb = p.GetPosition(), p.GetBoundingBox()
            out.setdefault(p.GetNumber(), (round(TOMM(q.x), 4), round(TOMM(q.y), 4), p.GetNetname(),
                                           (round(TOMM(bb.GetWidth()), 3), round(TOMM(bb.GetHeight()), 3))))
        return out

    def position(self, ref):
        fp = self._fp(ref)
        return (TOMM(fp.GetPosition().x), TOMM(fp.GetPosition().y), fp.GetOrientationDegrees())

    def _edge(self):
        """(left, top, right, bottom) of the board outline, including an outline() queued in this edit."""
        segs = [p for kind, a, c, _ in self._shapes if kind == "seg" for p in (a, c)]
        if segs:
            return (min(p[0] for p in segs), min(p[1] for p in segs), max(p[0] for p in segs), max(p[1] for p in segs))
        bb = self.board.GetBoardEdgesBoundingBox()
        return (TOMM(bb.GetLeft()), TOMM(bb.GetTop()), TOMM(bb.GetRight()), TOMM(bb.GetBottom()))

    def _net(self, name):
        if name not in self.nets:
            raise KeyError(f"no net {name!r} on the board. Nets come from the schematic (run `board.py sync`); "
                           f"names look like {sorted(n for n in self.nets if n)[:6]}")
        return self.nets[name]

    def _layer(self, name):
        if name in LAYERS:
            return LAYERS[name]
        lid = self.board.GetLayerID(name)
        if lid < 0:
            raise KeyError(f"no layer {name!r}")
        return lid

    # ------------------------------------------------------------------ immediate edits
    def place(self, ref, x, y, rot=None, side=None):
        """Move a footprint to (x, y) mm; rot in degrees CCW; side "F" or "B" flips it. Keeps its 3D model."""
        fp = self._fp(ref)
        if side and (side == "B") != fp.IsFlipped():
            fp.Flip(fp.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        if rot is not None:
            fp.SetOrientationDegrees(rot)
        fp.SetPosition(V(x, y))

    def set_field(self, ref, name, value):
        """Set Value or another field. Change the schematic too, or parity reports the difference."""
        fp = self._fp(ref)
        if name == "Value":
            fp.SetValue(value)
            return
        new = fp.GetField(name) is None
        fp.SetField(name, value)
        if new:
            fp.GetField(name).SetVisible(False)

    def label(self, ref, x=None, y=None, height=None, thickness=None, visible=True):
        """Put a footprint's silkscreen reference at (x, y), upright; optionally resize it (JLC's legibility
        minimum is 1.0 / 0.15 mm) or hide it (visible=False)."""
        t = self._fp(ref).Reference()
        t.SetVisible(visible)
        t.SetTextAngleDegrees(0)
        t.SetKeepUpright(True)
        if height:
            t.SetTextHeight(MM(height)); t.SetTextWidth(MM(height))
        if thickness:
            t.SetTextThickness(MM(thickness))
        if x is not None:
            t.SetPosition(V(x, y))

    def auto_labels(self, refs=None, gap=0.25):         # gap: label box to courtyard, enough to read as separate
        """Move each reference (default: all visible ones) beside its courtyard, on the first side clear of pads,
        other labels, holes and the board edge. Returns the refs that found no spot (place those with label())."""
        def bb(box, m=0.0):
            return (TOMM(box.GetLeft()) - m, TOMM(box.GetTop()) - m, TOMM(box.GetRight()) + m,
                    TOMM(box.GetBottom()) + m)

        def hit(a, c):
            return a[0] < c[2] and c[0] < a[2] and a[1] < c[3] and c[1] < a[3]
        refs = [r for r in (refs or self.fps) if self.fps[r].Reference().IsVisible()]
        blocks = [bb(p.GetBoundingBox(), 0.15) for fp in self.fps.values() for p in fp.Pads()]   # JLC silk-to-pad
        blocks += [bb(self.fps[r].Reference().GetBoundingBox(), 0.1) for r in self.fps
                   if r not in refs and self.fps[r].Reference().IsVisible()]
        e = self._edge()
        edge = (e[0] + 0.5, e[1] + 0.5, e[2] - 0.5, e[3] - 0.5)   # keep silk clear of the routed edge
        failed = []
        for ref in sorted(refs, key=lambda r: self.position(r)[:2]):
            fp, t = self.fps[ref], self.fps[ref].Reference()
            t.SetTextAngleDegrees(0)
            cy = fp.GetCourtyard(pcbnew.B_CrtYd if fp.IsFlipped() else pcbnew.F_CrtYd)
            l, tp, r, bt = bb(cy.BBox()) if cy.OutlineCount() else bb(fp.GetBoundingBox(False))
            w, h = TOMM(t.GetBoundingBox().GetWidth()), TOMM(t.GetBoundingBox().GetHeight())
            cx, cyy = (l + r) / 2, (tp + bt) / 2
            spots = {"above": (cx, tp - h / 2 - gap), "below": (cx, bt + h / 2 + gap),
                     "right": (r + w / 2 + gap, cyy), "left": (l - w / 2 - gap, cyy)}
            order = ["right", "left", "above", "below"] if (bt - tp) > (r - l) else ["above", "below", "right", "left"]
            for step in (0, 0.4, 0.8, 1.2):                 # then slide outwards, up to ~one text height
                ok = None
                for side in order:
                    x, y = spots[side]
                    dx, dy = {"above": (0, -1), "below": (0, 1), "right": (1, 0), "left": (-1, 0)}[side]
                    x, y = x + dx * step, y + dy * step
                    box = (x - w / 2, y - h / 2, x + w / 2, y + h / 2)
                    inside = edge[0] < box[0] and edge[1] < box[1] and box[2] < edge[2] and box[3] < edge[3]
                    if inside and not any(hit(box, o) for o in blocks):
                        ok = (x, y, box)
                        break
                if ok:
                    break
            if ok:
                t.SetPosition(V(ok[0], ok[1]))
                blocks.append(ok[2])
            else:
                failed.append(ref)
        return failed

    # ------------------------------------------------------------------ queued edits (applied in save)
    def class_width(self, net):
        """The track width of the net's class in the .kicad_pro (explicit assignment, then patterns, then Default)."""
        try:
            ns = json.load(open(os.path.splitext(self.path)[0] + ".kicad_pro"))["net_settings"]
        except (OSError, ValueError, KeyError):
            return 0.25
        classes = {c["name"]: c for c in ns.get("classes", [])}
        names = (ns.get("netclass_assignments") or {}).get(net) or [
            p["netclass"] for p in ns.get("netclass_patterns") or [] if fnmatch.fnmatchcase(net, p["pattern"])]
        names = [names] if isinstance(names, str) else [n for n in names if n in classes]
        if not names:
            return classes.get("Default", {}).get("track_width", 0.25)
        best = min(names, key=lambda n: classes[n].get("priority", 0))   # KiCad: the lowest priority number wins
        return classes[best].get("track_width", classes.get("Default", {}).get("track_width", 0.25))

    def _xy(self, p):
        return self.pad(*p) if isinstance(p[0], str) else (float(p[0]), float(p[1]))

    def track(self, net, points, width=None, layer="F.Cu"):
        """Track segments through points: (x, y) or a pad (ref, num). Width defaults to the net's class. Keep
        bends at 45° or 90°."""
        self._net(net)
        pts = [self._xy(p) for p in points]
        self._tracks.append((net, pts, width or self.class_width(net), self._layer(layer)))
        return pts[-1]

    def connect(self, *points, first="straight", net=None, width=None, layer=None):
        """Track through points, each a pad (ref, num) or (x, y), with one bend per leg: first="straight" runs
        along the longer axis then turns 45° into the end; "diagonal" turns first; "x" or "y" make a 90° elbow,
        horizontal or vertical first. Net comes from the pads, width from its class, layer from SMD pads
        (else F.Cu). Returns the end point."""
        nets, sides = set(), set()
        for p in points:
            if isinstance(p[0], str):
                pad = self._pad(*p)
                nets.add(pad.GetNetname())
                if pad.GetAttribute() == pcbnew.PAD_ATTRIB_SMD:
                    sides.add("B.Cu" if pad.IsOnLayer(pcbnew.B_Cu) else "F.Cu")
        if net is None and len(nets) != 1:
            raise ValueError(f"connect: pads are on nets {sorted(nets) or '(none)'}; they must share one, or pass net=")
        if net and nets - {net}:
            raise ValueError(f"connect: net={net!r} but the pads are on {sorted(nets)}")
        net = net or nets.pop()
        if layer is None:
            if len(sides) > 1:
                raise ValueError("connect: SMD pads on both sides; route to a via() and connect each side")
            layer = sides.pop() if sides else "F.Cu"
        pts = [self._xy(p) for p in points]
        path = [pts[0]]
        for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
            dx, dy = x2 - x1, y2 - y1
            ax, ay = abs(dx), abs(dy)
            sx, sy = math.copysign(1, dx), math.copysign(1, dy)
            if min(ax, ay) > 1e-6 and abs(ax - ay) > 1e-6:
                m = min(ax, ay)
                corner = {"x": (x2, y1), "y": (x1, y2),
                          "diagonal": (x1 + sx * m, y1 + sy * m),
                          "straight": (x2 - sx * m, y1) if ax > ay else (x1, y2 - sy * m)}[first]
                path.append((round(corner[0], 4), round(corner[1], 4)))
            path.append((x2, y2))
        return self.track(net, path, width, layer)

    def via(self, x, y, net, dia=0.6, drill=0.3):
        self._net(net)
        self._vias.append((x, y, net, dia, drill))
        return (x, y)

    def gnd_via(self, ref, num, dx, dy, width=None, net="GND", dia=0.6, drill=0.3, layer="F.Cu"):
        """A via at an offset from a pad, joined by a short stub. Returns the via position."""
        x, y = self.pad(ref, num)
        self.via(x + dx, y + dy, net, dia, drill)
        self.track(net, [(x, y), (x + dx, y + dy)], width, layer)
        return (x + dx, y + dy)

    def zone(self, net, layers=("F.Cu", "B.Cu"), outline=None, clearance=0.3, min_width=0.25, priority=0,
             thermal_gap=0.5, spoke=0.5, pads="thermal"):
        """A copper pour on net, over outline [(x, y), ...] (default: the board outline's bounding box; the fill
        keeps its edge clearance by itself). pads="thermal" (default) uses reliefs; pads="solid" joins pads directly,
        which suits exposed and power pads but tombstones small chip parts and makes through-hole pads hard to solder.
        save() refills it."""
        self._net(net)
        self._zones.append((net, [self._layer(l) for l in layers], outline, clearance, min_width, priority,
                            thermal_gap, spoke, pads))

    def set_pad_net(self, ref, num, net):
        """Move a pad to another existing net (after the same change in the schematic)."""
        self._pad(ref, num)
        self._net(net)
        self._net_changes.append((ref, str(num), net))

    def remove_tracks(self, nets=None, layers=None, region=None, vias=True, tracks=True, refs=None):
        """Remove tracks/vias matching every filter given: nets (names, "*" = all), layers, region (x0, y0, x1, y1)
        with both ends inside. Needs at least one filter. Or refs=["R3", ...]: the tracks and vias hanging off
        those parts' pads, followed along the copper up to the next pad, branch or dead end (so a script that
        routes a few parts on a finished board can undo exactly its own work before a rerun)."""
        if refs:
            for r in refs:
                self._fp(r)
            self._removes.append(("refs", list(refs)))
            return
        if not (nets or layers or region):
            raise ValueError("remove_tracks needs a filter; nets=['*'] means every net")
        self._removes.append((nets, layers, region, vias, tracks))

    def remove_zones(self, net=None):
        self._removes.append(("zones", net))

    def remove_texts(self):
        """Remove every free text on the board (not footprint fields), so a script that adds them can be rerun."""
        self._removes.append(("texts",))

    def remove_outline(self):
        """Remove every Edge.Cuts shape, to draw a new outline() in the same edit."""
        self._removes.append(("outline",))

    def text(self, s, x, y, height=1.0, thickness=0.15, layer="F.SilkS", rot=0, bold=False):
        """Free silkscreen text centred on (x, y): a board name, a pin legend. 1.0 / 0.15 mm is about JLC's
        legibility minimum. Back-side text is mirrored."""
        t = pcbnew.PCB_TEXT(self.board)
        t.SetText(s); t.SetLayer(self._layer(layer))
        t.SetTextHeight(MM(height)); t.SetTextWidth(MM(height)); t.SetTextThickness(MM(thickness))
        t.SetBold(bold); t.SetTextAngleDegrees(rot)
        t.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_CENTER); t.SetVertJustify(pcbnew.GR_TEXT_V_ALIGN_CENTER)
        t.SetMirrored(layer.startswith("B."))
        t.SetPosition(V(x, y))
        self._texts.append(t)

    def add_footprint(self, ref, fpid, x, y, rot=0, board_only=True):
        """A board-only part that's not in the schematic: mounting hole, fiducial, logo."""
        fp = load_footprint(fpid, os.path.dirname(self.path))
        fp.SetReference(ref)
        fp.SetBoardOnly(board_only)
        fp.Reference().SetVisible(False)                    # mechanical parts carry no silkscreen label
        fp.SetOrientationDegrees(rot)
        fp.SetPosition(V(x, y))
        self._fp_adds.append(fp)

    def remove_footprint(self, ref):
        """Remove a part (delete it from the schematic too, unless it's board-only). Its tracks stay: clear them
        with remove_tracks()."""
        self._fp_removes.append(self._fp(ref))

    def outline(self, w, h, x0=100.0, y0=100.0, r=1.0, width=0.05):
        """A w x h mm rectangle with corner radius r on Edge.Cuts, top-left at (x0, y0)."""
        x1, y1, x2, y2 = x0, y0, x0 + w, y0 + h
        for a, c in [((x1 + r, y1), (x2 - r, y1)), ((x2, y1 + r), (x2, y2 - r)),
                     ((x2 - r, y2), (x1 + r, y2)), ((x1, y2 - r), (x1, y1 + r))]:
            self._shapes.append(("seg", a, c, width))
        if r:
            for c, s in [((x2 - r, y1 + r), (x2 - r, y1)), ((x2 - r, y2 - r), (x2, y2 - r)),
                         ((x1 + r, y2 - r), (x1 + r, y2)), ((x1 + r, y1 + r), (x1, y1 + r))]:
                self._shapes.append(("arc", c, s, width))

    # ------------------------------------------------------------------ placement metrics
    def score(self, skip=None, margin=0.5, show=6):     # margin: courtyard-to-edge distance worth reporting
        """Placement metrics from pad centres, reflecting place() calls so far: airwire length (a minimum spanning
        tree per net), airwire crossings between nets, courtyard overlaps, parts within margin of the board edge
        (negative: past it), and how much of the board the courtyards cover. Nets in skip, and nets with a pour,
        are left out. Prints a summary; returns it as a dict. Lower length and zero crossings/overlaps is better."""
        poured = {z.GetNetname() for z in self.board.Zones()}
        skip = set(skip or ()) | poured
        nets = {}
        for ref, fp in self.fps.items():
            for p in fp.Pads():
                n = p.GetNetname()
                if n and n not in skip and not n.startswith("unconnected-"):
                    q = p.GetPosition()
                    nets.setdefault(n, {})[(ref, p.GetNumber())] = (TOMM(q.x), TOMM(q.y))
        wires, per_net, per_part = [], {}, {}
        for n, pads in nets.items():
            keys = list(pads)
            if len(keys) < 2:
                continue
            tree, best = {keys[0]}, {k: (math.dist(pads[keys[0]], pads[k]), keys[0]) for k in keys[1:]}
            while best:                                     # Prim's algorithm
                k = min(best, key=lambda k: best[k][0])
                d, frm = best.pop(k)
                tree.add(k)
                wires.append((n, pads[frm], pads[k]))
                per_net[n] = per_net.get(n, 0) + d
                for r in {frm[0], k[0]}:
                    per_part[r] = per_part.get(r, 0) + d / 2
                for o in best:
                    if math.dist(pads[k], pads[o]) < best[o][0]:
                        best[o] = (math.dist(pads[k], pads[o]), k)

        def cross(a, b, c, d):
            def o(p, q, r):
                return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
            if {a, b} & {c, d}:
                return False
            return o(a, b, c) * o(a, b, d) < -1e-9 and o(c, d, a) * o(c, d, b) < -1e-9
        crossings = []
        for i, (n1, a, b) in enumerate(wires):
            for n2, c, d in wires[i + 1:]:
                if n1 != n2 and cross(a, b, c, d):
                    crossings.append((n1, n2, ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)))

        def courtyard(fp):
            cy = fp.GetCourtyard(pcbnew.B_CrtYd if fp.IsFlipped() else pcbnew.F_CrtYd)
            return cy if cy.OutlineCount() else None
        for fp in self.fps.values():
            fp.BuildCourtyardCaches()                       # place() moved them
        cys = {r: courtyard(fp) for r, fp in self.fps.items()}
        overlaps, refs = [], sorted(r for r in cys if cys[r])
        for i, r1 in enumerate(refs):
            for r2 in refs[i + 1:]:
                if self.fps[r1].IsFlipped() != self.fps[r2].IsFlipped() or \
                        not cys[r1].BBox().Intersects(cys[r2].BBox()):
                    continue
                x = pcbnew.SHAPE_POLY_SET(cys[r1]); x.BooleanIntersection(cys[r2])
                if x.Area() / 1e12 > 0.001:                 # nm² -> mm²; ignore touching edges
                    overlaps.append((r1, r2, round(x.Area() / 1e12, 3)))
        e = self._edge()
        edge = []
        for r, fp in self.fps.items():
            bb = cys[r].BBox() if cys[r] else fp.GetBoundingBox(False)
            d = min(TOMM(bb.GetLeft()) - e[0], TOMM(bb.GetTop()) - e[1], e[2] - TOMM(bb.GetRight()),
                    e[3] - TOMM(bb.GetBottom()))
            if d < margin:
                edge.append((r, round(d, 2)))
        decoupling = self._decoupling()
        area = (e[2] - e[0]) * (e[3] - e[1])
        cover = sum(c.Area() for c in cys.values() if c) / 1e12 / area if area else 0
        total = sum(per_net.values())
        print(f"score: airwires {total:.1f} mm over {len(per_net)} nets, {len(crossings)} crossings, "
              f"{len(overlaps)} courtyard overlaps; board {e[2] - e[0]:g} x {e[3] - e[1]:g} mm, "
              f"courtyards cover {cover:.0%}" + (f"; skipped {', '.join(sorted(skip))}" if skip else ""))
        top = sorted(per_net.items(), key=lambda kv: -kv[1])[:show]
        print("  longest nets: " + ", ".join(f"{n} {d:.1f}" for n, d in top))
        top = sorted(per_part.items(), key=lambda kv: -kv[1])[:show]
        print("  most airwire: " + ", ".join(f"{r} {d:.1f}" for r, d in top))
        if crossings:
            print("  crossings: " + ", ".join(f"{a} x {b} ({x:.1f}, {y:.1f})" for a, b, (x, y) in crossings[:show])
                  + (" ..." if len(crossings) > show else ""))
        if overlaps:
            print("  overlaps: " + ", ".join(f"{a}/{b} {s:g} mm²" for a, b, s in overlaps))
        if edge:
            print(f"  within {margin:g} mm of the edge: " + ", ".join(f"{r} {d:g}" for r, d in sorted(edge)))
        if decoupling:
            print("  decoupling, farthest first (cap pad to nearest IC pad on its rail): " + ", ".join(
                f"{c} {rail} {ic} {d:.1f}" for c, rail, ic, d in decoupling[:show]))
        return dict(airwire=total, nets=per_net, parts=per_part, crossings=crossings, overlaps=overlaps,
                    edge=edge, cover=cover, decoupling=decoupling)

    def net_stats(self, show=True):
        """Per net: routed length, narrowest and widest track, layers, and vias. For each via on a net that isn't
        ground, the distance to the nearest ground via: a signal changing layers needs a ground via nearby for its
        return current. Prints a table (unless show=False); returns {net: dict}."""
        def ground(n):
            return bool(re.search(r"GND|VSS", n.upper()))
        out = {}
        for t in self.board.GetTracks():
            n = out.setdefault(t.GetNetname(), dict(length=0.0, widths=[], layers=set(), vias=[]))
            if t.GetClass() == "PCB_VIA":
                q = t.GetPosition()
                n["vias"].append((TOMM(q.x), TOMM(q.y)))
            else:
                n["length"] += TOMM(t.GetLength())
                n["widths"].append(TOMM(t.GetWidth()))
                n["layers"].add(self.board.GetLayerName(t.GetLayer()))
        gnd_vias = [v for name, n in out.items() if ground(name) for v in n["vias"]]
        for name, n in out.items():
            n["via_to_gnd"] = [] if ground(name) else [
                round(min((math.dist(v, g) for g in gnd_vias), default=float("inf")), 2) for v in n["vias"]]
        if show:
            for name in sorted(out, key=lambda k: (ground(k), k)):
                n = out[name]
                w = f"{min(n['widths']):g}-{max(n['widths']):g}" if n["widths"] else "-"
                g = (f"; nearest GND via {', '.join(f'{d:g}' for d in n['via_to_gnd'])} mm"
                     if n["via_to_gnd"] else "")
                print(f"{name or '(no net)'}\t{n['length']:.1f} mm, width {w}, {','.join(sorted(n['layers'])) or '-'}, "
                      f"{len(n['vias'])} vias{g}")
        return out

    def _decoupling(self):
        """[(cap, rail, "U2.4", mm)] for every capacitor between a ground and another net: the distance from its rail
        pad to the nearest IC pad (U*/IC*) on that rail, farthest first."""
        def ground(n):
            return bool(re.search(r"GND|VSS|^0$", n.upper()))
        ic_pads = {}
        for ref, fp in self.fps.items():
            if re.match(r"(U|IC)\d", ref):
                for p in fp.Pads():
                    q = p.GetPosition()
                    ic_pads.setdefault(p.GetNetname(), []).append((f"{ref}.{p.GetNumber()}", (TOMM(q.x), TOMM(q.y))))
        out = []
        for ref, fp in self.fps.items():
            pads = list(fp.Pads())
            if not re.match(r"C\d", ref) or len(pads) != 2:
                continue
            nets = [p.GetNetname() for p in pads]
            if sum(map(ground, nets)) != 1 or not all(nets):
                continue
            rp = pads[0] if ground(nets[1]) else pads[1]
            q = rp.GetPosition()
            near = [(math.dist((TOMM(q.x), TOMM(q.y)), xy), name) for name, xy in ic_pads.get(rp.GetNetname(), [])]
            if near:
                d, name = min(near)
                out.append((ref, rp.GetNetname(), name, round(d, 2)))
        return sorted(out, key=lambda t: -t[3])

    # ------------------------------------------------------------------ save
    def _selected_removals(self):
        out = []
        for t in self.board.GetTracks():
            is_via = t.GetClass() == "PCB_VIA"
            for rm in self._removes:
                if rm[0] in ("zones", "outline", "texts", "refs"):
                    continue
                nets, layers, region, vias, tracks = rm
                if (is_via and not vias) or (not is_via and not tracks):
                    continue
                if nets and "*" not in nets and t.GetNetname() not in nets:
                    continue
                if layers and (is_via or self.board.GetLayerName(t.GetLayer()) not in layers):
                    continue
                if region:
                    pts = [t.GetPosition()] if is_via else [t.GetStart(), t.GetEnd()]
                    if not all(region[0] <= TOMM(p.x) <= region[2] and region[1] <= TOMM(p.y) <= region[3]
                               for p in pts):
                        continue
                out.append(t)
                break
        for rm in self._removes:
            if rm[0] == "zones":
                out += [z for z in self.board.Zones() if rm[1] in (None, z.GetNetname())]
            elif rm[0] == "outline":
                out += [d for d in self.board.GetDrawings() if d.GetLayer() == pcbnew.Edge_Cuts]
            elif rm[0] == "texts":
                out += [d for d in self.board.GetDrawings() if d.GetClass() == "PCB_TEXT"]
            elif rm[0] == "refs":
                out += [t for t in self._hanging_copper(rm[1]) if all(t is not o for o in out)]
        return out

    def _hanging_copper(self, refs):
        """Tracks and vias reached from the pads of refs, following segment ends and vias, stopping at any pad, at a
        branch (more than one way on) and at dead ends."""
        def key(p):
            return (round(TOMM(p.x), 3), round(TOMM(p.y), 3))
        items = list(self.board.GetTracks())
        segs = [t for t in items if t.GetClass() != "PCB_VIA"]
        vias = [t for t in items if t.GetClass() == "PCB_VIA"]
        pads = list(self.board.GetPads())

        def on_pad(point, layer):
            return any(p.IsOnLayer(layer) and p.HitTest(point) for p in pads)

        def at(k, layer, skip):
            """Items joined at point k: segments on layer (any layer if None) ending there, and vias there."""
            out = [s_ for s_ in segs if (layer is None or s_.GetLayer() == layer)
                   and k in (key(s_.GetStart()), key(s_.GetEnd()))]
            out += [v for v in vias if key(v.GetPosition()) == k]
            return [o for o in out if all(o is not x for x in skip)]
        found, todo = [], []
        for ref in refs:
            for pad in self._fp(ref).Pads():
                for s_ in segs:
                    if all(s_ is not f for f in found) and pad.IsOnLayer(s_.GetLayer()):
                        for end, other in ((s_.GetStart(), s_.GetEnd()), (s_.GetEnd(), s_.GetStart())):
                            if pad.HitTest(end):
                                found.append(s_); todo.append((key(other), s_.GetLayer(), other))
                                break
        while todo:
            k, layer, point = todo.pop()
            if point is not None and on_pad(point, layer):
                continue
            nxt = at(k, layer, found)
            if len(nxt) != 1:
                continue
            item = nxt[0]
            found.append(item)
            if item.GetClass() == "PCB_VIA":
                more = at(k, None, found)
                if len(more) == 1:
                    s_ = more[0]
                    found.append(s_)
                    far = s_.GetEnd() if key(s_.GetStart()) == k else s_.GetStart()
                    todo.append((key(far), s_.GetLayer(), far))
            else:
                far = item.GetEnd() if key(item.GetStart()) == k else item.GetStart()
                todo.append((key(far), item.GetLayer(), far))
        return found

    def save(self, check=True, dry_run=False):
        """Apply the queued adds and removes, write the board, then refill zones and run DRC with schematic
        parity (check=False skips both). Returns the DRC report. dry_run=True writes to a temporary copy of the
        project instead and runs DRC there: the board file is untouched, so a route can be tried and rerun."""
        if self._saved:
            raise RuntimeError("already saved; edit again from a new process")
        b = self.board
        removals = self._selected_removals()               # reads before any mutation
        pads = {(r, n): self._pad(r, n) for r, n, _ in self._net_changes}
        edge = self._edge()
        for (r, n, net) in self._net_changes:
            pads[(r, n)].SetNet(self.nets[net])
        for item in removals:
            b.Remove(item)
        for fp in self._fp_removes:
            b.Remove(fp)
        for fp in self._fp_adds:
            b.Add(fp)
        for t in self._texts:
            b.Add(t)
        for kind, a, c, w in self._shapes:
            s = pcbnew.PCB_SHAPE(b, pcbnew.SHAPE_T_SEGMENT if kind == "seg" else pcbnew.SHAPE_T_ARC)
            s.SetLayer(pcbnew.Edge_Cuts); s.SetWidth(MM(w))
            if kind == "seg":
                s.SetStart(V(*a)); s.SetEnd(V(*c))
            else:
                s.SetCenter(V(*a)); s.SetStart(V(*c))
                s.SetArcAngleAndEnd(pcbnew.EDA_ANGLE(90, pcbnew.DEGREES_T), True)
            b.Add(s)
        for x, y, net, d, h in self._vias:
            v = pcbnew.PCB_VIA(b)
            v.SetPosition(V(x, y)); v.SetWidth(MM(d)); v.SetDrill(MM(h))
            v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); v.SetNet(self.nets[net])
            b.Add(v)
        for net, pts, w, layer in self._tracks:
            for a, c in zip(pts, pts[1:]):
                if a == c:
                    continue
                t = pcbnew.PCB_TRACK(b)
                t.SetStart(V(*a)); t.SetEnd(V(*c)); t.SetWidth(MM(w)); t.SetLayer(layer)
                t.SetNet(self.nets[net])
                b.Add(t)
        for net, layers, outline, clr, minw, prio, gap, spoke, pads in self._zones:
            for layer in layers:
                z = pcbnew.ZONE(b)
                z.SetLayer(layer); z.SetNet(self.nets[net]); z.SetAssignedPriority(prio)
                z.SetLocalClearance(MM(clr)); z.SetMinThickness(MM(minw))
                z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL if pads == "solid" else pcbnew.ZONE_CONNECTION_THERMAL)
                z.SetThermalReliefGap(MM(gap)); z.SetThermalReliefSpokeWidth(MM(spoke))
                ol = z.Outline(); ol.NewOutline()
                pts = outline or [(edge[0], edge[1]), (edge[2], edge[1]), (edge[2], edge[3]), (edge[0], edge[3])]
                for x, y in pts:
                    ol.Append(MM(x), MM(y))
                b.Add(z)
        self._saved = True
        summary = (f"+{sum(len(p) - 1 for _, p, _, _ in self._tracks)} tracks, +{len(self._vias)} vias, "
                   f"+{len(self._zones)} zones, -{len(removals)} removed, {len(self._net_changes)} pad nets changed")
        if not dry_run:
            b.Save(self.path)
            print(f"saved {os.path.basename(self.path)}: {summary}")
            return drc(self.path) if check else None
        with tempfile.TemporaryDirectory() as d:
            target = os.path.join(d, os.path.basename(self.path))
            _copy_project(os.path.dirname(self.path), d, skip=os.path.basename(self.path))
            b.Save(target)
            print(f"dry run, {os.path.basename(self.path)} not written: {summary}")
            return drc(target) if check else None


# ----------------------------------------------------------------------------- sync with the schematic
def _sexpr(text):
    stack = [[]]
    for t in re.findall(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()"]+', text):
        if t == "(":
            stack.append([])
        elif t == ")":
            done = stack.pop(); stack[-1].append(done)
        else:
            stack[-1].append(re.sub(r"\\(.)", r"\1", t[1:-1]) if t[0] == '"' else t)
    return stack[0][0]


def _get(n, key):
    return next((c for c in n[1:] if isinstance(c, list) and c and c[0] == key), None)


def _val(n, key, default=""):
    c = _get(n, key)
    return c[1] if c and len(c) > 1 else default


def sync(board_path, x0=None, y0=None):
    """KiCad's "Update PCB from Schematic": add missing parts (in a row from (x0, y0), default below the board),
    copy values, fields and DNP/BOM/position flags, set pad nets on pads with no copper attached, restore lost 3D
    models. Reports footprint changes, pads with copper on a changed net, and parts the schematic lacks.
    Runs in its own process (it adds footprints)."""
    path = os.path.abspath(board_path)
    _check_closed(path)
    proj = os.path.dirname(path)
    sch = os.path.splitext(path)[0] + ".kicad_sch"
    with tempfile.TemporaryDirectory() as d:
        net = os.path.join(d, "net.net")
        subprocess.run([kicad_cli(), "sch", "export", "netlist", "-o", net, sch], capture_output=True, check=True)
        tree = _sexpr(open(net).read())
    pin_net = {}
    for n in _get(tree, "nets")[1:]:
        for node in (c for c in n[1:] if isinstance(c, list) and c[0] == "node"):
            pin_net[(_val(node, "ref"), _val(node, "pin"))] = _val(n, "name")
    board = pcbnew.LoadBoard(path)
    on_board = {fp.GetReference(): fp for fp in board.GetFootprints()}
    nets = {p.GetNetname(): p.GetNet() for p in board.GetPads()}
    for name in set(pin_net.values()) - set(nets):           # nets that so far exist only on tracks or pours
        found = board.FindNet(name)
        if found:
            nets[name] = found
    routed = set()
    for t in board.GetTracks():
        for pad in board.GetPads():
            if pad.IsOnLayer(t.GetLayer()) and (pad.HitTest(t.GetStart()) or pad.HitTest(t.GetEnd())):
                routed.add((pad.GetParentFootprint().GetReference(), pad.GetNumber()))
    if x0 is None:
        bb = board.GetBoardEdgesBoundingBox()
        x0, y0 = TOMM(bb.GetLeft()), TOMM(bb.GetBottom()) + 10   # 10 mm below the outline, off the board
    x, seen, added, changed, renetted, restored, problems = x0, set(), [], [], [], [], []
    for comp in _get(tree, "components")[1:]:
        ref = _val(comp, "ref"); seen.add(ref)
        props = {_val(p, "name"): _val(p, "value") for p in comp[1:] if isinstance(p, list) and p[0] == "property"}
        fields = [(_val(f, "name"), f[2] if len(f) > 2 else "") for f in (_get(comp, "fields") or ["fields"])[1:]]
        fpid = _val(comp, "footprint")
        fp = on_board.get(ref)
        if fp is None:
            if not fpid:
                problems.append(f"{ref}: no footprint in the schematic"); continue
            try:
                fp = load_footprint(fpid, proj)
            except KeyError as e:
                problems.append(f"{ref}: {e}"); continue
            fp.SetReference(ref)
            sp = _get(comp, "sheetpath")
            fp.SetPath(pcbnew.KIID_PATH(_val(sp, "tstamps") + _val(comp, "tstamps")))
            fp.SetSheetname(_val(sp, "names")); fp.SetSheetfile(props.get("Sheetfile", ""))
            fp.SetPosition(V(x, y0)); x += 8                # 8 mm apart: a row that's easy to pick from
            for p in fp.Pads():
                name = pin_net.get((ref, p.GetNumber()))
                if name is not None:
                    if name not in nets:
                        item = pcbnew.NETINFO_ITEM(board, name); board.Add(item); nets[name] = item
                    p.SetNet(nets[name])
            added.append((ref, fp))
        else:
            if fpid and fp.GetFPID().GetUniStringLibId() != fpid:
                problems.append(f"{ref}: schematic footprint {fpid}, board {fp.GetFPID().GetUniStringLibId()}: "
                                "remove_footprint() it and its tracks, sync again, then place and route it")
            for p in fp.Pads():
                want = pin_net.get((ref, p.GetNumber()))
                if want is None or p.GetNetname() == want:
                    continue
                if (ref, p.GetNumber()) in routed:
                    problems.append(f"{ref} pad {p.GetNumber()}: has copper on {p.GetNetname()}, schematic says "
                                    f"{want}: remove those tracks, then sync again")
                    continue
                if want not in nets:
                    item = pcbnew.NETINFO_ITEM(board, want); board.Add(item); nets[want] = item
                p.SetNet(nets[want])
                renetted.append(f"{ref}.{p.GetNumber()}->{want}")
        before = (fp.GetValue(), sorted((f.GetName(), f.GetText()) for f in fp.GetFields()), fp.IsDNP())
        fp.SetValue(_val(comp, "value"))
        for fname, ftext in fields:
            if fname == "Footprint":
                continue
            new = fp.GetField(fname) is None
            fp.SetField(fname, ftext)
            if new:
                f = fp.GetField(fname); f.SetVisible(False)
                f.SetLayer(pcbnew.B_Fab if fp.IsFlipped() else pcbnew.F_Fab)
        fp.SetDNP("dnp" in props)
        fp.SetExcludedFromBOM("exclude_from_bom" in props)
        fp.SetExcludedFromPosFiles("exclude_from_pos_files" in props)
        if ref in on_board and before != (fp.GetValue(), sorted((f.GetName(), f.GetText()) for f in fp.GetFields()),
                                          fp.IsDNP()):
            changed.append(ref)
        if ref in on_board and not len(fp.Models()):
            try:
                src = load_footprint(fp.GetFPID().GetUniStringLibId(), proj)
                for m in src.Models():
                    fp.Models().push_back(m)
                if len(src.Models()):
                    restored.append(ref)
            except KeyError:
                pass
    for ref, fp in on_board.items():
        if ref not in seen and not fp.IsBoardOnly():
            problems.append(f"{ref}: on the board but not in the schematic (remove it, or it's board-only)")
    for _, fp in added:
        board.Add(fp)
    board.Save(path)
    print(f"sync: added {[r for r, _ in added]}, updated {changed}, pad nets {renetted}, 3D models {restored}")
    for p in problems:
        print("CHECK:", p)
    return problems


def new_board(path, w, h, x0=100.0, y0=100.0, r=1.0, holes=None, inset=4.0, layers=2, thickness=1.6):
    """Create a board with a rounded w x h outline and optional mounting holes ("M2", "M2.5" or "M3") inset from the
    corners (4 mm keeps an M3 hole's courtyard inside the board). Run sync() next to bring the parts in."""
    path = os.path.abspath(path)
    if os.path.exists(path) and os.path.getsize(path) > 200:
        raise FileExistsError(path)
    b = pcbnew.NewBoard(path)
    b.SetCopperLayerCount(layers)
    ls = b.GetEnabledLayers()
    for i in range(1, layers - 1):
        ls.addLayer(getattr(pcbnew, f"In{i}_Cu"))
    b.SetEnabledLayers(ls)
    b.GetDesignSettings().SetBoardThickness(MM(thickness))
    b.Save(path)
    bd = Board(path)
    bd.outline(w, h, x0, y0, r)
    if holes:
        name = {"M2": "MountingHole_2.2mm_M2", "M2.5": "MountingHole_2.7mm_M2.5", "M3": "MountingHole_3.2mm_M3"}[holes]
        for i, (x, y) in enumerate([(x0 + inset, y0 + inset), (x0 + w - inset, y0 + inset),
                                    (x0 + w - inset, y0 + h - inset), (x0 + inset, y0 + h - inset)], 1):
            bd.add_footprint(f"H{i}", f"MountingHole:{name}", x, y)
    bd.save(check=False)


def set_rules(pro_path, clearance=0.2, track=0.25, via=(0.6, 0.3), classes=None):
    """Set board minimums (JLC 2-layer standard process, with a little margin) and net classes in the .kicad_pro.
    classes: {"Power": {"track_width": 0.5, "nets": ["+5V", "GND"]}, ...}; patterns accept wildcards ("/USB_D*").
    The editor must be closed. DRC enforces a class's clearance, not its width (see kicad-routing)."""
    _check_closed(pro_path)
    d = json.load(open(pro_path))
    ds = d.setdefault("board", {}).setdefault("design_settings", {})
    ds.setdefault("rules", {}).update({
        "min_clearance": 0.15, "min_track_width": 0.15, "min_via_diameter": 0.5, "min_via_annular_width": 0.1,
        "min_through_hole_diameter": 0.3, "min_hole_to_hole": 0.25, "min_hole_clearance": 0.25,
        "min_copper_edge_clearance": 0.3})
    ns = d.setdefault("net_settings", {})
    default = next(c for c in ns["classes"] if c["name"] == "Default")
    default.update(clearance=clearance, track_width=track, via_diameter=via[0], via_drill=via[1])
    pats = [p for p in ns.get("netclass_patterns") or [] if p["netclass"] not in (classes or {})]
    for i, (name, spec) in enumerate((classes or {}).items()):
        c = dict(default, name=name, priority=i)
        c.update({k: v for k, v in spec.items() if k != "nets"})
        ns["classes"] = [x for x in ns["classes"] if x["name"] != name] + [c]
        pats += [{"netclass": name, "pattern": n} for n in spec.get("nets", [])]
    ns["netclass_patterns"] = pats
    json.dump(d, open(pro_path, "w"), indent=2)
    print(f"rules: clearance {clearance}, track {track}, via {via[0]}/{via[1]}; classes "
          f"{ {n: s.get('nets', []) for n, s in (classes or {}).items()} }")


def main(argv):
    if len(argv) >= 2 and argv[0] == "score":
        Board(argv[1], check_lock=False).score(argv[argv.index("--skip") + 1].split(",") if "--skip" in argv else None)
    elif len(argv) >= 2 and argv[0] == "pads":
        b = Board(argv[1], check_lock=False)
        for ref in argv[2:] or sorted(b.fps, key=lambda r: [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", r)]):
            x, y, rot = b.position(ref)
            print(f"{ref} at ({x:g}, {y:g}) rot {rot:g}{' bottom' if b.fps[ref].IsFlipped() else ''}")
            for num, (px, py, net, (w, h)) in sorted(b.pads(ref).items(),
                                                     key=lambda kv: [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", kv[0])]):
                print(f"  {num or '-':>4} ({px:g}, {py:g}) {w:g}x{h:g}  {net}")
    elif len(argv) >= 2 and argv[0] == "nets":
        Board(argv[1], check_lock=False).net_stats()
    elif len(argv) >= 2 and argv[0] == "tracks":
        b = Board(argv[1], check_lock=False)
        for t in sorted(b.board.GetTracks(), key=lambda t: (t.GetNetname(), t.GetClass())):
            if argv[2:] and t.GetNetname() not in argv[2:]:
                continue
            if t.GetClass() == "PCB_VIA":
                q = t.GetPosition()
                print(f"{t.GetNetname()}\tvia ({TOMM(q.x):g}, {TOMM(q.y):g}) {TOMM(t.GetWidth(pcbnew.F_Cu)):g}/"
                      f"{TOMM(t.GetDrillValue()):g}")
            else:
                a, c = t.GetStart(), t.GetEnd()
                print(f"{t.GetNetname()}\t{b.board.GetLayerName(t.GetLayer())} ({TOMM(a.x):g}, {TOMM(a.y):g}) -> "
                      f"({TOMM(c.x):g}, {TOMM(c.y):g}) w {TOMM(t.GetWidth()):g}")
    elif len(argv) in (2, 4) and argv[0] == "sync":
        sync(argv[1], *(float(v) for v in argv[2:4]))
    elif len(argv) >= 4 and argv[0] == "new":
        holes = argv[argv.index("--holes") + 1] if "--holes" in argv else None
        new_board(argv[1], float(argv[2]), float(argv[3]), holes=holes)
    elif len(argv) >= 2 and argv[0] == "rules":
        power = argv[argv.index("--power") + 1].split(",") if "--power" in argv else []
        width = float(argv[argv.index("--power-width") + 1]) if "--power-width" in argv else 0.5
        set_rules(argv[1], classes={"Power": {"track_width": width, "nets": power}} if power else None)
    else:
        print(__doc__)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
