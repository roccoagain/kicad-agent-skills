#!/usr/bin/env python3
"""Look at a KiCad 10 design with KiCad's own plots, cropped to what you need, and read connections from its netlist.

    python3 view.py sch board.kicad_sch -o out.png                     # whole sheet
    python3 view.py sch board.kicad_sch -o out.png --around U2,C3     # zoom to these symbols
    python3 view.py sch board.kicad_sch -o out.png --zoom 120,30,80,60 # window x,y,w,h in sheet mm
    python3 view.py pcb board.kicad_pcb -o out.png [--around U2] [--layers F.Cu,F.SilkS,Edge.Cuts] [--back]
    python3 view.py pins board.kicad_sch U2 [R3 ...]                   # each pin's net, from KiCad's netlist
    python3 view.py net board.kicad_sch /I2C_SDA                       # every pin on a net

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
    missing = [r for r in refs if r not in pos]
    if missing:
        raise SystemExit(f"not found: {missing}")
    xs, ys = [pos[r][0] for r in refs], [pos[r][1] for r in refs]
    return (min(xs) - margin, min(ys) - margin, max(xs) - min(xs) + 2 * margin, max(ys) - min(ys) + 2 * margin)


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


def natural(s):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s)]


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    cmd, path = argv[0], argv[1]
    margin = float(opt(argv, "--margin", 8))
    zoomed = "--around" in argv or "--zoom" in argv
    dpi = int(opt(argv, "--dpi", 200 if zoomed else 100))
    window = tuple(float(v) for v in opt(argv, "--zoom").split(",")) if "--zoom" in argv else None
    if cmd == "sch":
        out = opt(argv, "-o") or sys.exit("-o out.png needed")
        if "--around" in argv:
            window = window_around(positions(path, "symbol"), opt(argv, "--around").split(","), margin + 7)
        with tempfile.TemporaryDirectory() as d:
            subprocess.run([kicad_cli(), "sch", "export", "pdf", "-o", f"{d}/s.pdf", path], capture_output=True,
                           check=True)
            crop(f"{d}/s.pdf", out, window, dpi, int(opt(argv, "--page", 1)))
    elif cmd == "pcb":
        out = opt(argv, "-o") or sys.exit("-o out.png needed")
        back = "--back" in argv
        layers = opt(argv, "--layers", "B.Cu,B.SilkS,Edge.Cuts" if back else "F.Cu,F.SilkS,Edge.Cuts")
        if "--around" in argv:
            window = window_around(positions(path, "footprint"), opt(argv, "--around").split(","), margin)
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
                    window = (min(xs) - 3, min(ys) - 3, max(xs) - min(xs) + 6, max(ys) - min(ys) + 6)
            if back and window:                              # the plot is mirrored left-right across the page
                info = subprocess.run(["pdfinfo", f"{d}/b.pdf"], capture_output=True, text=True).stdout
                page_w = float(re.search(r"Page size:\s+([\d.]+)", info).group(1)) / 72 * 25.4
                window = (page_w - window[0] - window[2], window[1], window[2], window[3])
            crop(f"{d}/b.pdf", out, window, int(opt(argv, "--dpi", 400 if zoomed else 200)))
    elif cmd == "pins":
        pins = netlist_pins(path)
        for ref in argv[2:]:
            rows = sorted(((p, n) for r, p, n in pins if r == ref), key=lambda t: natural(t[0]))
            if not rows:
                print(f"{ref}: not in the netlist")
            for p, n in rows:
                print(f"{ref}.{p}\t{n}")
    elif cmd == "net":
        for r, p, n in sorted(netlist_pins(path), key=lambda t: (natural(t[0]), natural(t[1]))):
            if n == argv[2]:
                print(f"{r}.{p}")
    else:
        print(__doc__)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
