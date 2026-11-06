#!/usr/bin/env python3
"""Edit a KiCad 10 schematic from a short script, with plain python3 (no KiCad Python needed).

    import sys; sys.path.insert(0, "<this skill's folder>")
    from sch import Schematic

    s = Schematic("board.kicad_sch")                      # or Schematic.new("board.kicad_sch", title="...")
    s.add("Device:C_Small", "C?", (120.65, 50.8), value="100nF",
          footprint="Capacitor_SMD:C_0603_1608Metric", fields={"LCSC": "C14663"})   # "C?" -> next free C
    s.power("C5", "1", "+3V3")                            # power symbol on pin 1, pointing away from the part
    s.power("C5", "2", "GND")
    s.label("U2", "9", "UART_TX")                         # 2.54 mm stub, then a net label
    s.connect(("U2", "4"), ("C5", "1"))                   # wire, one bend if needed
    s.nc("U2", "7")
    s.set_field("R3", "Value", "1k")                      # existing or new part
    s.box(20, 25, 120, 85, "POWER INPUT")
    s.save()                                              # writes, adds junctions, runs ERC, prints a summary

Coordinates are schematic mm, y down, on the 1.27 mm grid. Rotation is counter-clockwise on screen, mirror is
applied after rotation (as KiCad does). Every pin end comes from the library symbol, so wires always land on pins.

Handled for you: copying the library symbol into lib_symbols (flattening `extends`), instances, unique references
(`C?`, `#PWR`), UUIDs, string escaping (newlines in text), field positions from the library, and junctions where a
wire end, pin or label lands on the middle of a wire (or three or more ends meet). New items are inserted into the
file; existing text is left byte for byte, so the diff shows only the change.

Command line:
    python3 sch.py symbol Device:R_Small          # a library symbol's pins: number, name, type, offset
    python3 sch.py pins board.kicad_sch U2        # a placed symbol's pin ends on the sheet
"""
import glob
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import uuid

GRID = 1.27


# ----------------------------------------------------------------------------- KiCad paths
def kicad_cli():
    for p in (os.environ.get("KICAD_CLI"), "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli",
              r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe"):
        if p and os.path.exists(p):
            return p
    return "kicad-cli"


def symbol_dirs():
    out = [os.environ.get("KICAD10_SYMBOL_DIR"), "/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols",
           "/usr/share/kicad/symbols", r"C:\Program Files\KiCad\10.0\share\kicad\symbols"]
    return [p for p in out if p and os.path.isdir(p)]


# ----------------------------------------------------------------------------- s-expressions
_TOK = re.compile(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()"]+')


def parse(text):
    stack = [[]]
    for t in _TOK.findall(text):
        if t == "(":
            stack.append([])
        elif t == ")":
            done = stack.pop()
            stack[-1].append(done)
        else:
            stack[-1].append(t)
    return stack[0][0]


def ser(n, ind=1):
    if not isinstance(n, list):
        return n
    if all(not isinstance(c, list) for c in n):
        return "(" + " ".join(n) + ")"
    out = "(" + " ".join(c for c in n if not isinstance(c, list))
    for c in n:
        if isinstance(c, list):
            out += "\n" + "\t" * ind + ser(c, ind + 1)
    return out + ")"


def q(s):
    """A KiCad string literal: escapes backslashes, quotes and line breaks."""
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def uq(tok):
    if tok.startswith('"'):
        return tok[1:-1].replace("\\n", "\n").replace('\\"', '"').replace("\\\\", "\\")
    return tok


def child(n, key):
    return next((c for c in n[1:] if isinstance(c, list) and c and c[0] == key), None)


def children(n, key):
    return [c for c in n[1:] if isinstance(c, list) and c and c[0] == key]


def top_spans(text):
    """(start, end, head) of each child of the root expression, by character offset."""
    spans, depth, i, start, n = [], 0, 0, None, len(text)
    while i < n:
        c = text[i]
        if c == '"':
            i += 1
            while text[i] != '"':
                i += 2 if text[i] == "\\" else 1
        elif c == "(":
            depth += 1
            if depth == 2:
                start = i
        elif c == ")":
            if depth == 2:
                head = re.match(r"\(([^\s()]+)", text[start:start + 40]).group(1)
                spans.append((start, i + 1, head))
            depth -= 1
        i += 1
    return spans


def fmt(v):
    return f"{round(v, 4):g}"


def U():
    return str(uuid.uuid4())


# ----------------------------------------------------------------------------- geometry
def xf(dx, dy, rot, mirror):
    """Library offset (y up) -> sheet offset (y down) for a symbol rotated rot° CCW, then mirrored."""
    dy = -dy
    r = math.radians(rot)
    dx, dy = dx * math.cos(r) + dy * math.sin(r), -dx * math.sin(r) + dy * math.cos(r)
    if mirror == "y":
        dx = -dx
    if mirror == "x":
        dy = -dy
    return round(dx, 4), round(dy, 4)


def snap(v):
    return round(round(v / GRID) * GRID, 4)


# ----------------------------------------------------------------------------- libraries
class Libraries:
    def __init__(self, project_dir):
        self.tables = {}
        table = os.path.join(project_dir, "sym-lib-table")
        if os.path.exists(table):
            for m in re.finditer(r'\(name "([^"]+)"\)\s*\(type "[^"]+"\)\s*\(uri "([^"]+)"\)', open(table).read()):
                self.tables[m.group(1)] = m.group(2).replace("${KIPRJMOD}", project_dir)
        self.cache = {}

    def file(self, lib):
        if lib in self.tables:
            return self.tables[lib]
        for d in symbol_dirs():
            p = os.path.join(d, lib + ".kicad_sym")
            if os.path.exists(p):
                return p
        raise KeyError(f"no symbol library {lib!r} (project sym-lib-table or KiCad's symbols folder)")

    def symbols(self, lib):
        if lib not in self.cache:
            tree = parse(open(self.file(lib)).read())
            self.cache[lib] = {uq(c[1]): c for c in children(tree, "symbol")}
        return self.cache[lib]

    def flat(self, lib, name):
        """A copy of lib:name ready for lib_symbols: renamed "lib:name", `extends` flattened."""
        syms = self.symbols(lib)
        if name not in syms:
            close = [k for k in syms if name.lower() in k.lower()][:8]
            raise KeyError(f"no symbol {name!r} in {lib}" + (f"; similar: {close}" if close else ""))
        s = syms[name]
        ext = child(s, "extends")
        if not ext:
            return [s[0], q(f"{lib}:{name}")] + s[2:]
        parent = self.flat(lib, uq(ext[1]))
        pname = uq(parent[1]).split(":", 1)[1]
        out = [parent[0], q(f"{lib}:{name}")]
        for c in parent[2:]:
            if isinstance(c, list) and c[0] == "property":
                continue
            if isinstance(c, list) and c[0] == "symbol":
                c = [c[0], c[1].replace(f'"{pname}_', f'"{name}_')] + c[2:]
            out.append(c)
        at = next(i for i, c in enumerate(out) if isinstance(c, list) and c[0] == "symbol")
        out[at:at] = children(s, "property")
        return out


def lib_pins(sym, unit=1):
    """[(number, name, type, px, py, angle)] for one unit of a flattened library symbol."""
    base = uq(sym[1]).split(":", 1)[-1]
    out = []
    for sub in children(sym, "symbol"):
        m = re.match(re.escape(base) + r"_(\d+)_(\d+)$", uq(sub[1]))
        if m and int(m.group(1)) not in (0, unit):
            continue
        for p in children(sub, "pin"):
            at = child(p, "at")
            out.append((uq(child(p, "number")[1]), uq(child(p, "name")[1]), p[1],
                        float(at[1]), float(at[2]), float(at[3]) if len(at) > 3 else 0.0))
    return out


# ----------------------------------------------------------------------------- the schematic
class Schematic:
    def __init__(self, path, check_lock=True):
        self.path = os.path.abspath(path)
        lock = os.path.join(os.path.dirname(self.path), "~" + os.path.basename(self.path) + ".lck")
        if check_lock and os.path.exists(lock):
            raise RuntimeError(f"{os.path.basename(self.path)} is open in KiCad ({lock}); close it first, "
                               "or its next save overwrites this edit")
        self._src = open(self.path).read()
        tree = parse(self._src)
        self.root_uuid = uq(child(tree, "uuid")[1])
        self.libs = Libraries(os.path.dirname(self.path))
        self.lib_defs = {uq(c[1]): c for c in children(child(tree, "lib_symbols") or ["lib_symbols"], "symbol")}
        self.new_libs = []
        self.project = None
        self.placed = {}            # ref -> {lib_id, x, y, rot, mirror, unit}
        self.wires, self.points, self.junctions = [], [], set()
        for n in children(tree, "symbol"):
            ref = None
            inst = child(n, "instances")
            if inst:
                proj = child(inst, "project")
                self.project = self.project or uq(proj[1])
                path_ = child(proj, "path")
                ref = uq(child(path_, "reference")[1])
            if ref is None:
                ref = next(uq(p[2]) for p in children(n, "property") if uq(p[1]) == "Reference")
            at = child(n, "at")
            mir = child(n, "mirror")
            unit = child(n, "unit")
            self.placed[ref] = dict(lib_id=uq(child(n, "lib_id")[1]), x=float(at[1]), y=float(at[2]),
                                    rot=float(at[3]) if len(at) > 3 else 0, mirror=mir[1] if mir else None,
                                    unit=int(unit[1]) if unit else 1)
        for w in children(tree, "wire"):
            pts = [(float(p[1]), float(p[2])) for p in children(child(w, "pts"), "xy")]
            self.wires.append((pts[0], pts[1]))
        for kind in ("label", "global_label", "hierarchical_label"):
            for lb in children(tree, kind):
                at = child(lb, "at")
                self.points.append((float(at[1]), float(at[2])))
        for j in children(tree, "junction"):
            at = child(j, "at")
            self.junctions.add((round(float(at[1]), 3), round(float(at[2]), 3)))
        self.project = self.project or self._project_name()
        self.items = []             # new top-level s-expressions, as text
        self.new_syms = {}          # ref -> dict for symbols added in this edit
        self.field_edits = []       # (ref, name, value)
        self.removals = []          # refs to remove with their stubs

    def _project_name(self):
        pros = glob.glob(os.path.join(os.path.dirname(self.path), "*.kicad_pro"))
        return os.path.splitext(os.path.basename(pros[0] if pros else self.path))[0]

    @classmethod
    def new(cls, path, title="", rev="1", date="", paper="A4"):
        """Write an empty root sheet (refuses to overwrite one) and open it."""
        if os.path.exists(path):
            raise FileExistsError(path)
        with open(path, "w") as f:
            f.write(f'(kicad_sch\n\t(version 20260306)\n\t(generator "eeschema")\n\t(generator_version "10.0")\n'
                    f'\t(uuid "{U()}")\n\t(paper {q(paper)})\n\t(title_block\n\t\t(title {q(title)})\n'
                    f'\t\t(date {q(date)})\n\t\t(rev {q(rev)})\n\t)\n\t(lib_symbols\n\t)\n'
                    f'\t(sheet_instances\n\t\t(path "/"\n\t\t\t(page "1")\n\t\t)\n\t)\n\t(embedded_fonts no)\n)\n')
        return cls(path)

    # ------------------------------------------------------------------ reading
    def _lib(self, lib_id):
        if lib_id not in self.lib_defs:
            lib, name = lib_id.split(":", 1)
            d = self.libs.flat(lib, name)
            self.lib_defs[lib_id] = d
            self.new_libs.append(d)
        return self.lib_defs[lib_id]

    def _sym(self, ref):
        s = self.new_syms.get(ref) or self.placed.get(ref)
        if s is None:
            raise KeyError(f"no symbol {ref!r} on {os.path.basename(self.path)}")
        return s

    def pins(self, ref):
        """{number: (x, y, out_dx, out_dy)}: each pin's end on the sheet and the direction pointing away from the
        body. Stacked pins (same number in several places) report the first."""
        s = self._sym(ref)
        out = {}
        for num, name, typ, px, py, ang in lib_pins(self._lib(s["lib_id"]), s["unit"]):
            dx, dy = xf(px, py, s["rot"], s["mirror"])
            ox, oy = xf(math.cos(math.radians(ang)), math.sin(math.radians(ang)), s["rot"], s["mirror"])
            out.setdefault(num, (round(s["x"] + dx, 3), round(s["y"] + dy, 3), -round(ox), -round(oy)))
        return out

    def pin(self, ref, num):
        p = self.pins(ref)
        if str(num) not in p:
            raise KeyError(f"{ref} has no pin {num!r}; pins: {sorted(p, key=_natural)}")
        return p[str(num)]

    def next_ref(self, prefix):
        used = set(self.placed) | set(self.new_syms)
        n = 1
        while f"{prefix}{n}" in used:
            n += 1
        return f"{prefix}{n}"

    # ------------------------------------------------------------------ symbols
    def add(self, lib_id, ref, at, rot=0, mirror=None, value=None, footprint="", datasheet="~", fields=None,
            unit=1, ref_at=None, value_at=None, power=False, in_bom=True, in_pos=True, dnp=False):
        """Place lib_id ("Library:Name") with its origin at `at` (mm). ref "R?" takes the next free number.
        Fields are added hidden. in_bom/in_pos/dnp: BOM, position-file and do-not-populate flags (a Tag-Connect
        footprint or test pad is in_bom=False, in_pos=False). Returns the reference."""
        if ref.endswith("?"):
            ref = self.next_ref(ref[:-1])
        if ref in self.placed or ref in self.new_syms:
            raise ValueError(f"{ref} already exists")
        sym = self._lib(lib_id)
        x, y = at
        if abs(x / GRID - round(x / GRID)) > 1e-3 or abs(y / GRID - round(y / GRID)) > 1e-3:
            raise ValueError(f"{ref} at {at}: put symbols on the {GRID} mm grid ({snap(x)}, {snap(y)})")
        lib_props = {uq(p[1]): p for p in children(sym, "property")}
        props = []

        def prop(name, val, default_hide, where=None):
            lp = lib_props.get(name)
            if where is None and lp is not None:
                lat = child(lp, "at")
                dx, dy = xf(float(lat[1]), float(lat[2]), rot, mirror)
                where = (x + dx, y + dy)
                ang = (float(lat[3]) + rot) % 180 if len(lat) > 3 else 0
            else:
                where = where or (x, y)
                ang = 0
            hide = default_hide
            eff = '(effects (font (size 1.27 1.27)))'
            if lp is not None:
                hide = default_hide or any(isinstance(c, list) and c[:2] == ["hide", "yes"] for c in lp)
                e = child(lp, "effects")
                if e is not None:
                    e = [c for c in e if not (isinstance(c, list) and c[0] == "hide")]
                    eff = ser(e, 3).replace("\n", " ").replace("\t", "")
            return (f'(property {q(name)} {q(val)} (at {fmt(where[0])} {fmt(where[1])} {fmt(ang)})'
                    f'{" (hide yes)" if hide else ""} {eff})')

        name = lib_id.split(":", 1)[1]
        props.append(prop("Reference", ref, power, ref_at))
        props.append(prop("Value", value if value is not None else name, False, value_at))
        props.append(prop("Footprint", footprint, True))
        props.append(prop("Datasheet", datasheet, True))
        props.append(prop("Description", "", True))
        for k, v in (fields or {}).items():
            props.append(prop(k, v, True, (x, y)))
        nums = sorted({p[0] for p in lib_pins(sym, unit)}, key=_natural)
        pins = " ".join(f"(pin {q(n)} (uuid {q(U())}))" for n in nums)
        flags = ("(in_bom no) (on_board no)" if power else
                 f"(in_bom {'yes' if in_bom else 'no'}) (in_pos_files {'yes' if in_pos else 'no'}) (on_board yes)")
        flags += f" (dnp {'yes' if dnp else 'no'})"
        self.new_syms[ref] = dict(lib_id=lib_id, x=x, y=y, rot=rot, mirror=mirror, unit=unit, props=props,
                                  text=None, pins=pins, flags=flags)
        return ref

    def remove(self, ref):
        """Remove an existing symbol together with what hangs off its pins: no-connect flags, and each stub of wires
        up to a label or power symbol. A stub stops at a branch, a junction with other wires, or another part's pin,
        so shared nets stay intact. Applied in save(); place the replacement with add() in the same script."""
        if ref not in self.placed:
            raise KeyError(f"{ref} isn't on the sheet" + (" (added in this edit)" if ref in self.new_syms else ""))
        self.removals.append((ref, list(self.pins(ref).values())))
        del self.placed[ref]                                # the reference is free for a replacement

    def set_field(self, ref, name, value):
        """Set a field (Value, Footprint, MPN, LCSC...) on an existing or new symbol; new fields are hidden."""
        if name == "Reference":
            raise ValueError("references are renamed in KiCad (annotation), not here")
        s = self._sym(ref)
        if ref in self.new_syms:
            for i, p in enumerate(s["props"]):
                if p.startswith(f"(property {q(name)} "):
                    s["props"][i] = re.sub(r'^\(property "(?:[^"\\]|\\.)*" "(?:[^"\\]|\\.)*"',
                                           lambda m: f"(property {q(name)} {q(value)}", p)
                    return
            s["props"].append(f'(property {q(name)} {q(value)} (at {fmt(s["x"])} {fmt(s["y"])} 0) (hide yes) '
                              f'(effects (font (size 1.27 1.27))))')
        else:
            self.field_edits.append((ref, name, value))

    # ------------------------------------------------------------------ wiring
    def _xy(self, p):
        if isinstance(p[0], str):
            x, y, *_ = self.pin(*p)
            return x, y
        return p

    def wire(self, *points):
        """Wire through points: (x, y) or (ref, pin). Each leg must be horizontal or vertical."""
        pts = [self._xy(p) for p in points]
        for a, b in zip(pts, pts[1:]):
            if abs(a[0] - b[0]) > 1e-6 and abs(a[1] - b[1]) > 1e-6:
                raise ValueError(f"wire {a} -> {b} is diagonal; add a corner point or use connect()")
            self.wires.append((a, b))
            self.items.append(f'(wire (pts (xy {fmt(a[0])} {fmt(a[1])}) (xy {fmt(b[0])} {fmt(b[1])})) '
                              f'(stroke (width 0) (type default)) (uuid {q(U())}))')

    def connect(self, a, b, first="h"):
        """Wire a to b ((x, y) or (ref, pin)) with at most one bend: horizontal first (first="h") or vertical."""
        (x1, y1), (x2, y2) = self._xy(a), self._xy(b)
        if x1 == x2 or y1 == y2:
            self.wire((x1, y1), (x2, y2))
        elif first == "h":
            self.wire((x1, y1), (x2, y1), (x2, y2))
        else:
            self.wire((x1, y1), (x1, y2), (x2, y2))

    def _stub(self, ref, pin, stub):
        x, y, ox, oy = self.pin(ref, pin)
        if stub:
            ex, ey = round(x + ox * stub, 4), round(y + oy * stub, 4)
            self.wire((x, y), (ex, ey))
            return ex, ey, ox, oy
        return x, y, ox, oy

    def label(self, ref, pin, name, stub=2.54, kind="label"):
        """A net label at the end of a stub from the pin (stub=0: on the pin). kind="global_label" for a
        global one. The text reads away from the part."""
        x, y, ox, oy = self._stub(ref, pin, stub)
        self.label_at(x, y, name, {(1, 0): 0, (-1, 0): 180, (0, -1): 90, (0, 1): 270}[(ox, oy)], kind)

    def label_at(self, x, y, name, angle=0, kind="label"):
        just = "left" if angle in (0, 90) else "right"
        shape = " (shape bidirectional)" if kind == "global_label" else ""
        self.points.append((x, y))
        self.items.append(f'({kind} {q(name)}{shape} (at {fmt(x)} {fmt(y)} {angle}) (effects (font (size 1.27 1.27)) '
                          f'(justify {just} bottom)) (uuid {q(U())}))')

    def power(self, ref, pin, net, stub=0, lib="power"):
        """A power symbol (GND, +3V3, +5V, PWR_FLAG, ... from the power library) on a pin, after an optional
        stub, drawn pointing away from the part. Returns its reference."""
        x, y, ox, oy = self._stub(ref, pin, stub)
        return self.power_at(x, y, net, (ox, oy), lib)

    def power_at(self, x, y, net, direction=None, lib="power"):
        """A power symbol whose pin is at (x, y). direction (dx, dy) is where its graphic points; default:
        down for ground-like nets, up for the rest."""
        down = net.upper().startswith(("GND", "VSS", "AGND", "DGND", "-")) or net == "Earth"
        d = tuple(direction) if direction else ((0, 1) if down else (0, -1))
        if down:
            rot = {(0, 1): 0, (1, 0): 90, (0, -1): 180, (-1, 0): 270}[d]
        else:
            rot = {(0, -1): 0, (-1, 0): 90, (0, 1): 180, (1, 0): 270}[d]
        prefix = "#FLG" if net == "PWR_FLAG" else "#PWR"
        return self.add(f"{lib}:{net}", prefix + "?", (x, y), rot, value=net, datasheet="", power=True)

    def nc(self, ref, pin):
        x, y, *_ = self.pin(ref, pin)
        self.items.append(f'(no_connect (at {fmt(x)} {fmt(y)}) (uuid {q(U())}))')

    def junction(self, x, y):
        key = (round(x, 3), round(y, 3))
        if key not in self.junctions:
            self.junctions.add(key)
            self.items.append(f'(junction (at {fmt(x)} {fmt(y)}) (diameter 0) (color 0 0 0 0) (uuid {q(U())}))')

    # ------------------------------------------------------------------ drawing
    def text(self, s, x, y, size=1.27, bold=False):
        th = f" (thickness {0.2 * size / 1.27:.2f}) (bold yes)" if bold else ""
        self.items.append(f'(text {q(s)} (exclude_from_sim no) (at {fmt(x)} {fmt(y)} 0) (effects (font (size {size} '
                          f'{size}){th}) (justify left bottom)) (uuid {q(U())}))')

    def box(self, x1, y1, x2, y2, title=None):
        """A dashed block outline, with a bold title inside its top-left corner."""
        self.items.append(f'(rectangle (start {fmt(x1)} {fmt(y1)}) (end {fmt(x2)} {fmt(y2)}) (stroke (width 0.254) '
                          f'(type dash)) (fill (type none)) (uuid {q(U())}))')
        if title:
            self.text(title, x1 + 2, y1 + 5, 2, bold=True)

    # ------------------------------------------------------------------ save
    def _auto_junctions(self):
        ends = {}
        for a, b in self.wires:
            for p in (a, b):
                k = (round(p[0], 3), round(p[1], 3))
                ends[k] = ends.get(k, 0) + 1
        pin_ends = []
        for ref in list(self.placed) + list(self.new_syms):
            try:
                pin_ends += [(round(x, 3), round(y, 3)) for x, y, _, _ in self.pins(ref).values()]
            except KeyError:
                pass
        taps = set(ends) | set(pin_ends) | {(round(x, 3), round(y, 3)) for x, y in self.points}
        for p in taps:
            mid = 0
            for a, b in self.wires:
                (x1, y1), (x2, y2) = a, b
                if abs(x1 - x2) < 1e-6 and abs(p[0] - x1) < 1e-3 and min(y1, y2) + 1e-3 < p[1] < max(y1, y2) - 1e-3:
                    mid += 1
                elif abs(y1 - y2) < 1e-6 and abs(p[1] - y1) < 1e-3 and min(x1, x2) + 1e-3 < p[0] < max(x1, x2) - 1e-3:
                    mid += 1
            n = ends.get(p, 0) + pin_ends.count(p)
            if mid and (n or p in self.points) or n >= 3:
                self.junction(*p)

    def _apply_removals(self, text):
        def key(x, y):
            return (round(float(x), 3), round(float(y), 3))
        items = []                                          # (start, end, kind, points, ref)
        for st, en, head in top_spans(text):
            if head not in ("symbol", "wire", "label", "global_label", "no_connect", "junction"):
                continue
            n = parse(text[st:en])
            if head == "wire":
                pts = [key(p[1], p[2]) for p in children(child(n, "pts"), "xy")]
            else:
                at = child(n, "at")
                pts = [key(at[1], at[2])]
            ref = None
            if head == "symbol":
                ref = next((uq(p[2]) for p in children(n, "property") if uq(p[1]) == "Reference"), None)
                if uq(child(n, "lib_id")[1]).startswith("power:"):
                    head = "power"
            items.append([st, en, head, pts, ref])
        gone = set()
        pin_at = {}
        for r in self.placed:
            if r.startswith("#"):
                continue
            try:
                for x, y, _, _ in self.pins(r).values():
                    pin_at.setdefault(key(x, y), set()).add(r)
            except KeyError:
                pass
        for ref, pins in self.removals:
            gone |= {i for i, it in enumerate(items) if it[2] == "symbol" and it[4] == ref}
            for x, y, _, _ in pins:
                cur, visited = key(x, y), set()
                while cur not in visited:
                    visited.add(cur)
                    here = [i for i, it in enumerate(items) if i not in gone and cur in it[3]]
                    wires = [i for i in here if items[i][2] == "wire"]
                    ends = [i for i in here if items[i][2] in ("label", "global_label", "power", "no_connect")]
                    mid = any(it[2] == "wire" and i not in gone and _on_wire(cur, it[3]) for i, it in enumerate(items))
                    if mid or pin_at.get(cur):
                        break
                    gone |= {i for i in here if items[i][2] == "junction"}
                    if not wires:
                        gone |= set(ends)
                        break
                    if len(wires) > 1 or ends:
                        break
                    w = items[wires[0]]
                    gone.add(wires[0])
                    cur = w[3][1] if w[3][0] == cur else w[3][0]
        for i in sorted(gone, key=lambda i: -items[i][0]):
            st, en = items[i][0], items[i][1]
            while st > 0 and text[st - 1] in " \t":
                st -= 1
            if text[en:en + 1] == "\n":
                en += 1
            text = text[:st] + text[en:]
        removed_refs = {items[i][4] for i in gone if items[i][4]}
        for r in removed_refs:
            self.placed.pop(r, None)
        tree = parse(text)                                  # re-read what's left for the junction pass
        self.wires = [tuple((float(p[1]), float(p[2])) for p in children(child(w, "pts"), "xy"))
                      for w in children(tree, "wire")]
        self.points = [(float(child(lb, "at")[1]), float(child(lb, "at")[2]))
                       for k in ("label", "global_label", "hierarchical_label") for lb in children(tree, k)]
        self.junctions = {(round(float(child(j, "at")[1]), 3), round(float(child(j, "at")[2]), 3))
                          for j in children(tree, "junction")}
        print(f"removed {', '.join(sorted(r for r, _ in self.removals))}: {len(gone)} items")
        self.removals = []
        return text

    def save(self, erc=True):
        """Write the file (adds junctions first) and, by default, run ERC and print its summary.
        Returns the ERC violations as a list of dicts."""
        text = self._apply_removals(self._src) if self.removals else self._src
        self._auto_junctions()
        # field edits on existing symbols, inside their own blocks only
        for ref, name, value in self.field_edits:
            spans = [s for s in top_spans(text) if s[2] == "symbol"]
            for st, en, _ in spans:
                block = text[st:en]
                if not re.search(r'\(property "Reference" ' + re.escape(q(ref)) + r'[\s)]', block) and \
                        f"(reference {q(ref)})" not in block:
                    continue
                pat = re.compile(r'(\(property ' + re.escape(q(name)) + r' )"(?:[^"\\]|\\.)*"')
                if pat.search(block):
                    block = pat.sub(lambda m: m.group(1) + q(value), block, count=1)
                else:
                    s = self.placed[ref]
                    new = (f'\n\t\t(property {q(name)} {q(value)}\n\t\t\t(at {fmt(s["x"])} {fmt(s["y"])} 0)\n'
                           f'\t\t\t(hide yes)\n\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size 1.27 1.27)\n'
                           f'\t\t\t\t)\n\t\t\t)\n\t\t)')
                    m = re.search(r'\n\t\t\(pin ', block) or re.search(r'\n\t\t\(instances', block)
                    block = block[:m.start()] + new + block[m.start():]
                text = text[:st] + block + text[en:]
                break
            else:
                raise KeyError(f"set_field: {ref} not found")
        for ref, s in self.new_syms.items():
            m = f" (mirror {s['mirror']})" if s["mirror"] else ""
            self.items.append(
                f'(symbol (lib_id {q(s["lib_id"])}) (at {fmt(s["x"])} {fmt(s["y"])} {fmt(s["rot"])}){m} '
                f'(unit {s["unit"]}) (exclude_from_sim no) {s["flags"]} (uuid {q(U())})\n\t\t'
                + "\n\t\t".join(s["props"]) + f"\n\t\t{s['pins']}\n\t\t(instances (project {q(self.project)} "
                f'(path {q("/" + self.root_uuid)} (reference {q(ref)}) (unit {s["unit"]})))))')
        spans = top_spans(text)
        if self.new_libs:
            ls = next(s for s in spans if s[2] == "lib_symbols")
            ins = "".join("\n\t\t" + ser(d, 3) for d in self.new_libs) + "\n\t"
            text = text[:ls[1] - 1] + ins + text[ls[1] - 1:]
            spans = top_spans(text)
        if self.items:
            tail = next((s for s in spans if s[2] in ("sheet_instances", "embedded_fonts")), None)
            pos = tail[0] if tail else text.rstrip().rfind(")")
            text = text[:pos] + "".join(i + "\n\t" for i in self.items) + text[pos:]
        with open(self.path, "w") as f:
            f.write(text)
        n_new = len(self.new_syms)
        self._src, self.items, self.new_libs, self.field_edits = text, [], [], []
        for ref, s in self.new_syms.items():
            self.placed[ref] = s
        self.new_syms = {}
        print(f"saved {os.path.basename(self.path)}: {n_new} symbols added")
        return erc_report(self.path) if erc else None


def _on_wire(p, pts):
    (x1, y1), (x2, y2) = pts
    if abs(x1 - x2) < 1e-6 and abs(p[0] - x1) < 1e-3:
        return min(y1, y2) + 1e-3 < p[1] < max(y1, y2) - 1e-3
    if abs(y1 - y2) < 1e-6 and abs(p[1] - y1) < 1e-3:
        return min(x1, x2) + 1e-3 < p[0] < max(x1, x2) - 1e-3
    return False


def _natural(s):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", str(s))]


def erc_report(path, show=12):
    """Run KiCad's ERC; print counts and the first violations. Returns the violations."""
    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, "erc.json")
        r = subprocess.run([kicad_cli(), "sch", "erc", "--format", "json", "--severity-all", "-o", out, path],
                           capture_output=True, text=True)
        if not os.path.exists(out):
            raise RuntimeError("ERC failed (does the file load in KiCad?):\n" + r.stdout + r.stderr)
        data = json.load(open(out))
    vs = [v for sh in data.get("sheets", []) for v in sh.get("violations", [])]
    print(f"ERC: {len(vs)} violations" + (":" if vs else ""))
    for v in vs[:show]:
        where = "; ".join(f"{i['description']} @({i['pos']['x'] * 100:.2f}, {i['pos']['y'] * 100:.2f})"
                          for i in v.get("items", []))
        print(f"  {v['severity']}: {v['type']}: {where}")
    if len(vs) > show:
        print(f"  ... {len(vs) - show} more")
    return vs


# ----------------------------------------------------------------------------- command line
def main(argv):
    if len(argv) >= 2 and argv[0] == "symbol":
        lib, name = argv[1].split(":", 1)
        sym = Libraries(os.getcwd()).flat(lib, name)
        props = {uq(p[1]): uq(p[2]) for p in children(sym, "property")}
        print(f"{argv[1]}  footprint: {props.get('Footprint') or '-'}")
        units = sorted({int(m.group(1)) for c in children(sym, "symbol")
                        for m in [re.match(r".*_(\d+)_\d+$", uq(c[1]))] if m and m.group(1) != "0"}) or [1]
        for u in units:
            if len(units) > 1:
                print(f"unit {u}:")
            for num, nm, typ, px, py, ang in sorted(lib_pins(sym, u), key=lambda p: _natural(p[0])):
                print(f"  {num:>4} {nm:<16} {typ:<14} at ({px:g}, {py:g}) angle {ang:g}")
    elif len(argv) == 3 and argv[0] == "pins":
        s = Schematic(argv[1], check_lock=False)
        for num, (x, y, ox, oy) in sorted(s.pins(argv[2]).items(), key=lambda kv: _natural(kv[0])):
            print(f"  {num:>4}  ({x:g}, {y:g})  points {({(1, 0): 'right', (-1, 0): 'left', (0, -1): 'up', (0, 1): 'down'})[(ox, oy)]}")
    else:
        print(__doc__)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
