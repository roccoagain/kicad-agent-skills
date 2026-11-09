#!/usr/bin/env python3
"""Look at a KiCad 10 design with KiCad's own plots, cropped to what you need, and read connections from its netlist.

    python3 view.py sch board.kicad_sch -o out.png                     # whole sheet
    python3 view.py sch board.kicad_sch -o out.png --around U2,C3     # zoom to these symbols
    python3 view.py sch board.kicad_sch -o out.png --zoom 120,30,80,60 # window x,y,w,h in sheet mm
    python3 view.py pcb board.kicad_pcb -o out.png [--around U2] [--layers F.Cu,F.SilkS,Edge.Cuts] [--back]
    python3 view.py pins board.kicad_sch [U2 R3 ...]                   # each pin's net (every part if none named)
    python3 view.py net board.kicad_sch /I2C_SDA                       # every pin on a net
    python3 view.py ohms board.kicad_sch +3V3 [GND]                    # resistance between nets, resistors only
    python3 view.py expect board.kicad_sch DESIGN.md                   # check "U2.4 = +3V3" lines against the netlist
    python3 view.py decoupling board.kicad_sch                         # IC supply pins and the caps on their rails

Options: --page N (schematic sheet N), --dpi D (default 200 zoomed, 100 whole), --margin MM (default 8).
Open the PNG with your image viewer or Read tool. Needs pdftoppm (poppler) for PNGs.
Coordinates are mm from the sheet's or page's top-left, y down: the same numbers the files and scripts use.
"""
import os
import re
import subprocess
import sys
import tempfile


def kicad_cli():
    for p in (os.environ.get("KICAD_CLI"), "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli",
              r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe"):
        if p and os.path.exists(p):
            return p
    return "kicad-cli"


def opt(argv, name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default


def top_blocks(text):
    """The root expression's children as text, found by matching brackets (any layout)."""
    out, depth, i, start = [], 0, 0, 0
    while i < len(text):
        c = text[i]
        if c == '"':
            i += 1
            while text[i] != '"':
                i += 2 if text[i] == "\\" else 1
        elif c == "(":
            depth += 1
            start = i if depth == 2 else start
        elif c == ")":
            if depth == 2:
                out.append(text[start:i + 1])
            depth -= 1
        i += 1
    return out


def positions(path, kind):
    """{ref: (x, y)} of placed symbols (kind "symbol") or footprints (kind "footprint"), read from the file."""
    out = {}
    for block in top_blocks(open(path).read()):
        if not block.startswith("(" + kind):
            continue
        at = re.search(r"\(at ([-\d.]+) ([-\d.]+)", block)
        ref = re.search(r'\(property "Reference" "([^"]+)"', block)
        if at and ref:
            out[ref.group(1)] = (float(at.group(1)), float(at.group(2)))
    return out


def crop(pdf, png, window, dpi, page=1):
    args = ["pdftoppm", "-png", "-r", str(dpi), "-f", str(page), "-l", str(page), "-singlefile"]
    if window:
        x, y, w, h = window
        px = lambda mm: str(max(0, round(mm / 25.4 * dpi)))
        args += ["-x", px(x), "-y", px(y), "-W", px(w), "-H", px(h)]
    subprocess.run(args + [pdf, os.path.splitext(png)[0]], check=True)
    print(f"wrote {png}" + (f" (window {', '.join(f'{v:g}' for v in window)} mm)" if window else ""))


def window_around(pos, refs, margin):
    """pos: {ref: [(x, y), ...]} points each part covers; the window holds all of them plus margin."""
    missing = [r for r in refs if r not in pos]
    if missing:
        raise SystemExit(f"not found: {missing}")
    xs, ys = [p[0] for r in refs for p in pos[r]], [p[1] for r in refs for p in pos[r]]
    return (min(xs) - margin, min(ys) - margin, max(xs) - min(xs) + 2 * margin, max(ys) - min(ys) + 2 * margin)


def symbol_extents(path):
    """{ref: points}: every placed unit's origin and pin ends, via sch.py beside this skill (else origins only)."""
    out = {r: [xy] for r, xy in positions(path, "symbol").items()}
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "kicad-schematic"))
        from sch import Schematic
        s = Schematic(path, check_lock=False)
        for ref, units in s.placed.items():
            out[ref] = [(u["x"], u["y"]) for u in units.values()] + [p[:2] for p in s.pins(ref).values()]
    except Exception:
        pass
    return out


def netlist_pins(sch):
    with tempfile.TemporaryDirectory() as d:
        subprocess.run([kicad_cli(), "sch", "export", "netlist", "-o", f"{d}/n.net", sch], capture_output=True,
                       check=True)
        text = open(f"{d}/n.net").read()
    out = []
    # KiCad writes one item per line: (net / (name ...) / (node / (ref ...) / (pin ...)
    net = None
    for line in text.splitlines():
        n = re.match(r'\s*\(net\s*$', line)
        if n:
            net = None
            continue
        nm = re.match(r'\s*\(name "((?:[^"\\]|\\.)*)"\)', line)
        if nm and net is None:
            net = nm.group(1)
        r = re.match(r'\s*\(ref "([^"]+)"\)', line)
        if r:
            ref = r.group(1)
        p = re.match(r'\s*\(pin "([^"]+)"\)', line)
        if p and net is not None:
            out.append((ref, p.group(1), net))
    return out


_TOK = re.compile(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()"]+')


def sexpr(text):
    stack = [[]]
    for t in _TOK.findall(text):
        if t == "(":
            stack.append([])
        elif t == ")":
            done = stack.pop()
            stack[-1].append(done)
        else:
            stack[-1].append(re.sub(r"\\(.)", r"\1", t[1:-1]) if t[0] == '"' else t)
    return stack[0][0]


def _get(n, key):
    return next((c for c in n[1:] if isinstance(c, list) and c and c[0] == key), None)


def _val(n, key, default=""):
    c = _get(n, key)
    return c[1] if c and len(c) > 1 else default


def netlist(sch):
    """(parts, nets): parts {ref: {value, lib, dnp, pins: {pin: (net, pintype)}}}, nets {name: [(ref, pin, type)]}."""
    with tempfile.TemporaryDirectory() as d:
        subprocess.run([kicad_cli(), "sch", "export", "netlist", "-o", f"{d}/n.net", sch], capture_output=True,
                       check=True)
        tree = sexpr(open(f"{d}/n.net").read())
    parts, nets = {}, {}
    for c in _get(tree, "components")[1:]:
        src = _get(c, "libsource")
        props = {_val(p, "name") for p in c[1:] if isinstance(p, list) and p and p[0] == "property"}
        parts[_val(c, "ref")] = dict(value=_val(c, "value"), lib=f"{_val(src, 'lib')}:{_val(src, 'part')}" if src
                                     else "", pins={}, dnp="dnp" in props)
    for n in _get(tree, "nets")[1:]:
        name = _val(n, "name")
        for node in (x for x in n[1:] if isinstance(x, list) and x[0] == "node"):
            ref, pin, typ = _val(node, "ref"), _val(node, "pin"), _val(node, "pintype")
            nets.setdefault(name, []).append((ref, pin, typ))
            parts.setdefault(ref, dict(value="", lib="", pins={}, dnp=False))["pins"][pin] = (name, typ)
    return parts, nets


def ohms_value(v):
    """'4k7', '10k', '1M', '100R', '0R', '2.2 kΩ', '10k 1%', '10K_0603', '100 Ohm' -> ohms, or None. Anything after
    the number and its multiplier (tolerance, package, unit) is ignored if it starts with a separator."""
    m = re.match(r"\s*(\d+(?:[.,]\d+)?)\s*([RrKkMmGg]?)(\d*)\s*(?:Ω|[Oo]hms?)?(?=$|[\s/_%,;(Ω]|[Rr]\b)",
                 v)
    if not m:
        return None
    mult = {"": 1, "r": 1, "R": 1, "k": 1e3, "K": 1e3, "m": 1e-3, "M": 1e6, "g": 1e9, "G": 1e9}[m.group(2)]
    return float(f"{m.group(1).replace(',', '.')}{'.' + m.group(3) if m.group(3) else ''}") * mult


def is_ground(n):
    return bool(re.search(r"GND|VSS", n.upper())) or n in ("0", "Earth")


def resistance(parts, a, b):
    """Resistance between nets a and b through two-pin resistors only (capacitors open, ICs and diodes ignored):
    nodal analysis with 1 A into a and b grounded. None if no resistor path joins them."""
    edges = []
    for ref, p in parts.items():
        r = ohms_value(p["value"]) if re.match(r"R\d", ref) and len(p["pins"]) == 2 and not p.get("dnp") else None
        if r is not None:
            n1, n2 = (net for net, _ in p["pins"].values())
            if n1 != n2:
                edges.append((n1, n2, max(r, 1e-3)))
    nodes = sorted({n for e in edges for n in e[:2]} | {a, b})
    reach, todo = {a}, [a]                                   # only the part of the graph that a connects to
    while todo:
        x = todo.pop()
        for n1, n2, _ in edges:
            for u, v in ((n1, n2), (n2, n1)):
                if u == x and v not in reach:
                    reach.add(v); todo.append(v)
    if b not in reach:
        return None
    nodes = [n for n in nodes if n in reach and n != b]
    idx = {n: i for i, n in enumerate(nodes)}
    G = [[0.0] * len(nodes) for _ in nodes]
    for n1, n2, r in edges:
        for u, v in ((n1, n2), (n2, n1)):
            if u in idx:
                G[idx[u]][idx[u]] += 1 / r
                if v in idx:
                    G[idx[u]][idx[v]] -= 1 / r
    I = [0.0] * len(nodes)
    I[idx[a]] = 1.0
    n = len(nodes)                                          # Gaussian elimination with partial pivoting
    for c in range(n):
        piv = max(range(c, n), key=lambda r_: abs(G[r_][c]))
        G[c], G[piv], I[c], I[piv] = G[piv], G[c], I[piv], I[c]
        for r_ in range(c + 1, n):
            f = G[r_][c] / G[c][c]
            if f:
                G[r_] = [x - f * y for x, y in zip(G[r_], G[c])]
                I[r_] -= f * I[c]
    V = [0.0] * n
    for r_ in reversed(range(n)):
        V[r_] = (I[r_] - sum(G[r_][k] * V[k] for k in range(r_ + 1, n))) / G[r_][r_]
    return V[idx[a]]


def series_paths(parts, a, b, hops=4):
    """Chains of two-terminal parts joining nets a and b (up to `hops` parts), other than resistors-only chains:
    the paths a meter also sees, such as a resistor in series with an LED."""
    two = {ref: [net for net, _ in p["pins"].values()] for ref, p in parts.items() if not p.get("dnp")}
    two = {ref: ns for ref, ns in two.items() if len(set(ns)) == 2 and len(ns) == 2}
    out = []

    def walk(net, path, seen):
        if len(path) > hops:
            return
        for ref, (n1, n2) in two.items():
            if ref in path or net not in (n1, n2):
                continue
            nxt = n2 if net == n1 else n1
            if nxt == b:
                out.append(path + [ref])
            elif nxt not in seen and nxt != a:
                walk(nxt, path + [ref], seen | {nxt})
    walk(a, [], {a})
    return [p for p in out if not all(re.match(r"R\d", r) for r in p)]


def fmt_ohms(r):
    return next(f"{r / m:.4g} {u}Ω" for m, u in ((1e6, "M"), (1e3, "k"), (1, "")) if r >= m or m == 1)


def natural(s):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s)]


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    cmd, path = argv[0], argv[1]
    margin = float(opt(argv, "--margin", 8))
    zoomed = "--around" in argv or "--zoom" in argv
    dpi = int(opt(argv, "--dpi", 200 if zoomed else 100))   # sheet text stays legible; crops get more detail
    window = tuple(float(v) for v in opt(argv, "--zoom").split(",")) if "--zoom" in argv else None
    if cmd == "sch":
        out = opt(argv, "-o") or sys.exit("-o out.png needed")
        if "--around" in argv:
            window = window_around(symbol_extents(path), opt(argv, "--around").split(","), margin + 3)  # + field text
        with tempfile.TemporaryDirectory() as d:
            subprocess.run([kicad_cli(), "sch", "export", "pdf", "-o", f"{d}/s.pdf", path], capture_output=True,
                           check=True)
            crop(f"{d}/s.pdf", out, window, dpi, int(opt(argv, "--page", 1)))
    elif cmd == "pcb":
        out = opt(argv, "-o") or sys.exit("-o out.png needed")
        back = "--back" in argv
        layers = opt(argv, "--layers", "B.Cu,B.SilkS,Edge.Cuts" if back else "F.Cu,F.SilkS,Edge.Cuts")
        if "--around" in argv:
            window = window_around({r: [xy] for r, xy in positions(path, "footprint").items()},
                                   opt(argv, "--around").split(","), margin)
        with tempfile.TemporaryDirectory() as d:
            subprocess.run([kicad_cli(), "pcb", "export", "pdf", "-o", f"{d}/b.pdf", "--mode-single", "-l", layers,
                            "--scale", "1"] + (["--mirror"] if back else []) + [path], capture_output=True, check=True)
            if window is None:                               # whole board: the Edge.Cuts extent
                pts = []
                for blk in re.split(r"\n\t\(", open(path).read()):
                    if blk.startswith("gr_") and '"Edge.Cuts"' in blk:
                        pts += [(float(a), float(b)) for a, b in
                                re.findall(r"\((?:start|end|mid|center) ([-\d.]+) ([-\d.]+)\)", blk)]
                if pts:
                    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
                    window = (min(xs) - 3, min(ys) - 3, max(xs) - min(xs) + 6, max(ys) - min(ys) + 6)  # 3 mm border
            if back and window:                              # the plot is mirrored left-right across the page
                info = subprocess.run(["pdfinfo", f"{d}/b.pdf"], capture_output=True, text=True).stdout
                page_w = float(re.search(r"Page size:\s+([\d.]+)", info).group(1)) / 72 * 25.4
                window = (page_w - window[0] - window[2], window[1], window[2], window[3])
            crop(f"{d}/b.pdf", out, window, int(opt(argv, "--dpi", 400 if zoomed else 200)))
    elif cmd == "pins":
        pins = netlist_pins(path)
        missing = 0
        for ref in [a for a in argv[2:] if not a.startswith("-")] or sorted({r for r, _, _ in pins}, key=natural):
            rows = sorted(((p, n) for r, p, n in pins if r == ref), key=lambda t: natural(t[0]))
            if not rows:
                print(f"{ref}: not in the netlist")
                missing += 1
            for p, n in rows:
                print(f"{ref}.{p}\t{n}")
        return int(missing > 0)
    elif cmd == "net":
        pins = netlist_pins(path)
        names = {n for _, _, n in pins}
        if argv[2] not in names:
            near = sorted(n for n in names if argv[2].strip("/").lower() in n.lower())
            print(f"no net {argv[2]!r}" + (f"; similar: {', '.join(near[:8])}" if near else
                                          "; local labels are named /NAME"))
            return 1
        for r, p, n in sorted(pins, key=lambda t: (natural(t[0]), natural(t[1]))):
            if n == argv[2]:
                print(f"{r}.{p}")
    elif cmd == "ohms":
        parts, nets = netlist(path)
        a, b = argv[2], argv[3] if len(argv) > 3 else "GND"
        for n in (a, b):
            if n not in nets:
                sys.exit(f"no net {n!r}; nets: {', '.join(sorted(nets)[:20])} ...")
        r = resistance(parts, a, b)
        unread = sorted((ref for ref, p in parts.items() if re.match(r"R\d", ref) and len(p["pins"]) == 2
                         and not p.get("dnp") and ohms_value(p["value"]) is None), key=natural)
        if unread:
            print("  WARNING: values not understood, treated as open: " + ", ".join(
                f"{ref} ({parts[ref]['value']!r})" for ref in unread))
        dnp = sorted((ref for ref, p in parts.items() if p.get("dnp") and {a, b} & {n for n, _ in p["pins"].values()}),
                     key=natural)
        if dnp:
            print("  left out as DNP: " + ", ".join(dnp))
        print(f"{a} to {b}: " + (f"{fmt_ohms(r)} through resistors only" if r is not None else
                                  "no resistor path (open, as far as resistors go)"))
        others = sorted({ref for ref, p in parts.items() if not re.match(r"R\d", ref)
                         and {a, b} <= {net for net, _ in p["pins"].values()}}, key=natural)
        if others:
            print("  also across both nets (the meter reading can differ): " + ", ".join(
                f"{ref} ({parts[ref]['value']})" for ref in others))
        chains = [c for c in series_paths(parts, a, b) if len(c) > 1]
        for c in chains[:10]:
            print("  series path: " + " - ".join(f"{ref} ({parts[ref]['value']})" for ref in c)
                  + " (diodes conduct one way: give both meter polarities)")
    elif cmd == "expect":
        parts, nets = netlist(path)
        where = {(ref, pin): net for ref, p in parts.items() for pin, (net, _) in p["pins"].items()}
        bad = checked = 0
        for line in open(argv[2]):
            m = re.match(r"\s*[-*]?\s*`?([A-Za-z#]+\d+)\.(\S+?)`?\s*(==|=)\s*`?([^`\s]+)`?\s*(?:#.*)?$", line)
            if not m:
                continue
            ref, pin, op, rhs = m.groups()
            checked += 1
            got = where.get((ref, pin))
            if op == "==":
                r2, _, p2 = rhs.partition(".")
                want = where.get((r2, p2))
                ok = got is not None and got == want
                note = f"{ref}.{pin} on {got}, {rhs} on {want}"
            else:
                ok, note = got == rhs, f"{ref}.{pin} is on {got}, expected {rhs}"
            if not ok:
                bad += 1
                print("MISMATCH " + note)
        print(f"expect: {checked} checked, {bad} mismatched" + ("" if checked else
              " (lines look like `U2.4 = +3V3` or `U2.4 == C3.1`)"))
        return int(bad > 0 or checked == 0)
    elif cmd == "decoupling":
        parts, nets = netlist(path)
        caps = {}
        for ref, p in parts.items():
            ns = [net for net, _ in p["pins"].values()]
            if re.match(r"C\d", ref) and len(ns) == 2 and sum(map(is_ground, ns)) == 1:
                caps.setdefault(next(n for n in ns if not is_ground(n)), []).append(f"{ref} {p['value']}")
        missing = 0
        for ref in sorted(parts, key=natural):
            rails = sorted({net for net, typ in parts[ref]["pins"].values() if typ.startswith("power_in")
                            and not is_ground(net)})
            for rail in rails:
                pins = sorted((pin for pin, (net, typ) in parts[ref]["pins"].items() if net == rail), key=natural)
                found = caps.get(rail, [])
                missing += not found
                print(f"{ref} pins {','.join(pins)} on {rail}: " + (", ".join(found) if found else "NO CAPACITOR"))
        return int(missing > 0)
    else:
        print(__doc__)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
