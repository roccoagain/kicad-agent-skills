#!/usr/bin/env python3
"""End-to-end smoke test: build a small KiCad 10 project from nothing with the skills' scripts, then check it.

    python3 tests/smoke.py [DIR]          # default: a temporary folder, deleted afterwards

DIR is created if missing. An existing DIR is wiped only if an earlier run left its marker file in it.
The run covers: Schematic.new, add (incl. a multi-unit op-amp), power, labels, wires, set_field, remove and re-add,
refresh_symbol, ERC and lint; view.py pins/net/ohms/expect/decoupling and pictures; board.py new, rules, sync,
placement, score, a hand route with connect/track/via/gnd_via (dry run first), pours and DRC; check.py; the fab and
assembly jobsets and jlc_asm.py. Each step prints PASS/FAIL; the exit code is the number of failures.

Needs KiCad 10 and pdftoppm. KiCad's Python is found at $KPY or the macOS path.
"""
import glob
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SK = os.path.join(REPO, "skills")
SCH, BRD = f"{SK}/kicad-schematic", f"{SK}/kicad-board-edit"
VIEW, CHECK, ASM, FAB = (f"{SK}/kicad-view/view.py", f"{SK}/kicad-check/check.py", f"{SK}/kicad-assembly-export",
                         f"{SK}/kicad-fab-export")
KPY = os.environ.get("KPY") or "/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3"
MARK = ".kicad-skills-testbed"
NAME = "testbed"
sys.path.insert(0, SCH)
from sch import kicad_cli  # noqa: E402

failures = []


def step(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f": {detail}" if detail and not ok else ""))
    if not ok:
        failures.append(name)
    return ok


def run(cmd, kpy=False, cwd=None, ok_codes=(0,)):
    """Run a command; return (code, output). kpy: prefix KiCad's Python."""
    cmd = ([KPY, "-I"] if kpy else []) + cmd
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    out = "\n".join(line for line in (r.stdout + r.stderr).splitlines()
                    if not re.search(r"Fontconfig|wxApp|memory leak|swig/python detected", line))
    return r.returncode, out


def script(body, d, kpy=False):
    """Write a short script into d and run it, like an agent would."""
    p = os.path.join(d, "_step.py")
    open(p, "w").write(f"import sys\nsys.path.insert(0, {BRD if kpy else SCH!r})\n" + body)
    return run([p] if kpy else [sys.executable, p], kpy=kpy, cwd=d)


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def schematic(d):
    body = f'''
from sch import Schematic
s = Schematic.new("{NAME}.kicad_sch", title="kicad-agent-skills smoke test", date="2026-11-09")
R, C = "Resistor_SMD:R_0603_1608Metric", "Capacitor_SMD:C_0603_1608Metric"
s.add("Connector_Generic:Conn_01x05", "J1", (40.64, 76.2), value="Conn_01x05",
      footprint="Connector_PinHeader_2.54mm:PinHeader_1x05_P2.54mm_Vertical", fields={{"LCSC": "C2337"}})
s.wire(("J1", "1"), (27.94, 71.12)); s.power_at(27.94, 71.12, "+5V"); s.power_at(33.02, 71.12, "PWR_FLAG")
s.wire(("J1", "2"), (25.4, 73.66)); s.power_at(25.4, 73.66, "GND"); s.power_at(30.48, 73.66, "PWR_FLAG", (0, 1))
s.label("J1", "3", "IN"); s.label("J1", "4", "OUT"); s.label("J1", "5", "VREF")
s.add("Device:R", "R?", (76.2, 63.5), value="10k", footprint=R, fields={{"LCSC": "C25804"}})
s.add("Device:R", "R?", (76.2, 78.74), value="10k", footprint=R, fields={{"LCSC": "C25804"}})
s.power("R1", "1", "+5V"); s.power("R2", "2", "GND"); s.connect(("R1", "2"), ("R2", "1"))
s.label_at(76.2, 71.12, "VMID")
s.add("Device:C", "C?", (88.9, 78.74), value="1uF", footprint=C, fields={{"LCSC": "C15849"}})
s.label("C1", "1", "VMID"); s.power("C1", "2", "GND")
LM = "Amplifier_Operational:LM358"
u = s.add(LM, "U?", (127, 63.5), value="LM358", footprint="Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
          fields={{"LCSC": "C7950"}})
s.add(LM, u, (127, 88.9), unit=2); s.add(LM, u, (152.4, 76.2), unit=3)
for top, inp, out_ in ((63.5, "3", "OUT"), (88.9, "5", "VREF")):
    o, n = ("1", "2") if inp == "3" else ("7", "6")
    s.label(u, inp, "IN" if inp == "3" else "VMID")
    s.wire((u, o), (137.16, top), (137.16, top + 7.62), (116.84, top + 7.62), (116.84, top + 2.54), (u, n))
    s.label_at(137.16, top, out_)
s.power(u, "8", "+5V"); s.power(u, "4", "GND")
s.add("Device:C", "C?", (162.56, 76.2), value="100nF", footprint=C, fields={{"LCSC": "C14663"}})
s.power("C2", "1", "+5V"); s.power("C2", "2", "GND")
s.save(lint=False, erc=False)

s = Schematic("{NAME}.kicad_sch")
assert sorted(s.units("U1")) == [1, 2, 3], s.units("U1")
s.set_field("U1", "MPN", "LM358DR")
s.remove("C1"); s.add("Device:C", "C1", (88.9, 78.74), value="1uF", footprint=C, fields={{"LCSC": "C15849"}})
s.label("C1", "1", "VMID"); s.power("C1", "2", "GND")
s.refresh_symbol("Device:R")
vs = s.save()
errors = [v for v in vs if v["severity"] == "error"]
print("ERC_ERRORS", len(errors))
'''
    code, out = script(body, d)
    print("  " + "\n  ".join(out.splitlines()[-12:]))
    m = re.search(r"ERC_ERRORS (\d+)", out)
    step("schematic: draw, multi-unit, set_field, remove/re-add, refresh_symbol", code == 0 and m is not None, out[-800:])
    step("schematic: ERC has no errors", m is not None and m.group(1) == "0", out[-800:])
    sch = open(f"{d}/{NAME}.kicad_sch").read()
    step("schematic: MPN on all three op-amp units", sch.count('"LM358DR"') == 3)


def schematic_edge_cases(d):
    """Cases from code review: a T-joint added in the same edit as a remove(), a sub-sheet in a subfolder, escapes."""
    e = f"{d}/out/edge"
    os.makedirs(f"{e}/sub")
    body = f'''
import uuid, re
from sch import Schematic, uq, q
open("edge.kicad_pro", "w").write("{{}}")
r = Schematic.new("edge.kicad_sch"); Schematic.new("sub/child.kicad_sch")
su = str(uuid.uuid4())
sheet = ('(sheet (at 100 50) (size 20 10) (exclude_from_sim no) (in_bom yes) (on_board yes) (dnp no) '
         f'(stroke (width 0.1524) (type solid)) (fill (color 0 0 0 0.0000)) (uuid "{{su}}") '
         '(property "Sheetname" "child" (at 100 49.3 0) (effects (font (size 1.27 1.27)))) '
         '(property "Sheetfile" "sub/child.kicad_sch" (at 100 60.6 0) (effects (font (size 1.27 1.27)))) '
         f'(instances (project "edge" (path "/{{r.root_uuid}}" (page "2")))))\\n\\t')
t = open("edge.kicad_sch").read(); i = t.index("(sheet_instances")
open("edge.kicad_sch", "w").write(t[:i] + sheet + t[i:])
r = Schematic("edge.kicad_sch")
r.add("Device:R", "R?", (50.8, 50.8), value="1k"); r.add("Device:R", "R?", (63.5, 50.8), value="1k")
r.wire((40.64, 60.96), (76.2, 60.96)); r.label_at(40.64, 60.96, "W")
r.save(erc=False, lint=False)
r = Schematic("edge.kicad_sch")
r.remove("R1"); r.wire(("R2", "2"), (63.5, 60.96))
r.save(erc=False, lint=False)
c = Schematic("sub/child.kicad_sch")
print("CHILD", c.add("Device:R", "R?", (50.8, 50.8), value="2k"), c.add("Device:R", "R?", (63.5, 50.8), value="2k"),
      c.instance_paths == [f"/{{r.root_uuid}}/{{su}}"])
c.save(erc=False, lint=False)
print("ESCAPE", uq(q("C:\\\\docs\\\\new.pdf")) == "C:\\\\docs\\\\new.pdf")
'''
    code, out = script(body, e)
    step("sub-sheet in a subfolder: R? skips the root's R2, right instance path", "CHILD R1 R3 True" in out,
         out[-800:])
    step("escapes round-trip", "ESCAPE True" in out, out[-400:])
    code, out = run([sys.executable, VIEW, "pins", f"{e}/edge.kicad_sch", "R2"])
    step("T-joint made in the same edit as remove() keeps its junction", "R2.2\t/W" in out, out)
    sys.path.insert(0, f"{SK}/kicad-view")
    import view
    vals = [view.ohms_value(v) for v in ("10k 1%", "10K_0603", "100 Ohm", "4k7", "1M", "10m", "10uF", "DNP")]
    step("ohms value parsing", vals == [1e4, 1e4, 100, 4700, 1e6, 0.01, None, None], str(vals))
    parts = {"R3": dict(value="1k5", pins={"1": ("A", ""), "2": ("N", "")}),
             "D1": dict(value="LED", pins={"1": ("GND", ""), "2": ("N", "")}),
             "R9": dict(value="10k", pins={"1": ("A", ""), "2": ("GND", "")}, dnp=True)}
    step("ohms: series LED path listed, DNP resistor left out",
         view.series_paths(parts, "A", "GND") == [["R3", "D1"]] and view.resistance(parts, "A", "GND") is None)


def netlist_tools(d):
    f = f"{d}/{NAME}.kicad_sch"
    code, out = run([sys.executable, VIEW, "pins", f, "U1"])
    step("view pins: U1 has 8 pins on the right nets", "U1.8\t+5V" in out and "U1.4\tGND" in out and
         out.count("U1.") == 8, out)
    code, out = run([sys.executable, VIEW, "ohms", f, "+5V"])
    step("view ohms: +5V to GND is 20 kΩ", "20 kΩ" in out, out)
    open(f"{d}/expect.md", "w").write("- `U1.3 = /IN`\n- `U1.1 = /OUT`\n- `U1.7 == J1.5`\n- `R1.2 == C1.1`\n")
    code, out = run([sys.executable, VIEW, "expect", f, f"{d}/expect.md"])
    step("view expect: four connections hold", code == 0 and "4 checked, 0 mismatched" in out, out)
    open(f"{d}/wrong.md", "w").write("U1.3 = /OUT\n")
    code, out = run([sys.executable, VIEW, "expect", f, f"{d}/wrong.md"])
    step("view expect: catches a wrong connection", code == 1 and "MISMATCH" in out, out)
    code, out = run([sys.executable, VIEW, "net", f, "IN"])
    step("view net: a wrong name exits 1 and suggests /IN", code == 1 and "/IN" in out, out)
    code, out = run([sys.executable, VIEW, "decoupling", f])
    step("view decoupling: U1's +5V pin has C2", code == 0 and re.search(r"U1 pins 8 on \+5V: C2", out), out)
    code, out = run([sys.executable, VIEW, "sch", f, "-o", f"{d}/out/u1.png", "--around", "U1,C2"])
    step("view sch picture", code == 0 and os.path.getsize(f"{d}/out/u1.png") > 1000, out)
    code, out = run([sys.executable, f"{SCH}/sch.py", "lint", f])
    print("  " + out.splitlines()[0] if out else "")


def board(d):
    pcb, pro = f"{d}/{NAME}.kicad_pcb", f"{d}/{NAME}.kicad_pro"
    code, out = run([f"{BRD}/board.py", "new", pcb, "40", "30", "--holes", "M3"], kpy=True)
    step("board new", code == 0 and os.path.exists(pcb) and os.path.exists(pro), out)
    code, out = run([f"{BRD}/board.py", "rules", pro, "--power", "+5V,GND"], kpy=True)
    step("board rules", code == 0, out)
    code, out = run([f"{BRD}/board.py", "sync", pcb], kpy=True)
    step("board sync adds all parts", code == 0 and all(r in out for r in ("J1", "R1", "R2", "C1", "C2", "U1"))
         and "CHECK" not in out, out)
    place = '''
from board import Board
b = Board("testbed.kicad_pcb")
b.place("J1", 106.5, 109.92)
b.place("U1", 122, 113)
b.place("C2", 127, 110.3, rot=90)
b.place("R1", 128, 114, rot=270); b.place("R2", 128, 118, rot=270); b.place("C1", 130.5, 118, rot=270)
sc = b.score()
print("OVERLAPS", len(sc["overlaps"]), "EDGE", [r for r, d in sc["edge"] if d < 0])
print("DECOUPLING", sc["decoupling"])
print("LABELS_FAILED", b.auto_labels())
b.save()
'''
    code, out = script(place, d, kpy=True)
    print("  " + "\n  ".join(l for l in out.splitlines() if l.startswith(("score", "  decoupling", "DRC"))))
    step("board place + score: no courtyard overlaps, nothing past the edge",
         code == 0 and "OVERLAPS 0 EDGE []" in out, out[-1500:])
    m = re.search(r"DECOUPLING .*\('C2', '\+5V', 'U1\.8', ([\d.]+)\)", out)
    step("board score: decoupling distance C2 to U1.8 under 3 mm", m and float(m.group(1)) < 3, out[-600:])

    before = sha(pcb)
    trial = '''
from board import Board
b = Board("testbed.kicad_pcb")
b.connect(("R1", "2"), ("R2", "1"))
b.save(dry_run=True)
'''
    code, out = script(trial, d, kpy=True)
    step("board dry run leaves the file untouched", code == 0 and "dry run" in out and sha(pcb) == before, out)

    route = '''
import sys
from board import Board
b = Board("testbed.kicad_pcb")
b.remove_tracks(nets=["*"]); b.remove_zones(); b.remove_texts()
b.connect(("J1", "1"), ("U1", "8"))                              # +5V, Power class width
b.connect(("U1", "8"), ("C2", "1"))
b.connect(("C2", "1"), ("R1", "1"), first="diagonal")
b.connect(("J1", "3"), ("U1", "3"), first="diagonal")           # /IN
b.track("/OUT", [("U1", "1"), ("U1", "2")])                     # follower: output to inverting input
b.connect(("U1", "1"), (117.4, 111.095)); b.via(117.4, 111.095, "/OUT")
b.connect((117.4, 111.095), ("J1", "4"), net="/OUT", layer="B.Cu")
b.track("/VREF", [("U1", "7"), ("U1", "6")])
b.connect(("U1", "7"), (126.3, 112.365)); b.via(126.3, 112.365, "/VREF")
b.connect((126.3, 112.365), ("J1", "5"), net="/VREF", layer="B.Cu")
b.connect(("U1", "5"), ("R1", "2")); b.connect(("R1", "2"), ("R2", "1")); b.connect(("R2", "1"), ("C1", "1"))
b.gnd_via("U1", "4", dx=-1.7, dy=0); b.gnd_via("C2", "2", dx=0, dy=-1.1)
b.gnd_via("R2", "2", dx=0, dy=1.1); b.gnd_via("C1", "2", dx=0, dy=1.1)
b.zone("GND", ["F.Cu", "B.Cu"], pads="solid")
b.text("SMOKE TEST", 120, 125.5)
rep = b.save(dry_run=sys.argv[-1] == "dry")
errs = [v for v in rep["violations"] if v["severity"] == "error"]
print("RESULT errors", len(errs), "unconnected", len(rep["unconnected_items"]), "parity", len(rep["schematic_parity"]))
'''
    open(f"{d}/route.py", "w").write(f"import sys\nsys.path.insert(0, {BRD!r})\n" + route)
    before = sha(pcb)
    code, out = run([f"{d}/route.py", "dry"], kpy=True, cwd=d)
    step("board hand route, dry run: DRC clean and the file untouched",
         "RESULT errors 0 unconnected 0 parity 0" in out and sha(pcb) == before, out[-1500:])
    code, out = run([f"{d}/route.py"], kpy=True, cwd=d)
    print("  " + "\n  ".join(l for l in out.splitlines() if l.startswith(("DRC", "  "))))
    step("board hand route + pours: no errors, nothing unconnected, parity clean",
         "RESULT errors 0 unconnected 0 parity 0" in out and sha(pcb) != before, out[-1500:])
    return True


def rerun_safety(d):
    pcb = f"{d}/{NAME}.kicad_pcb"
    code, out = run([f"{BRD}/board.py", "nets", pcb], kpy=True)
    step("board nets: lengths, widths, vias and via-to-GND distance", code == 0 and
         re.search(r"^\+5V\t[\d.]+ mm, width 0\.5-0\.5", out, re.M) and "nearest GND via" in out, out[-600:])
    code, out = run([f"{BRD}/board.py", "tracks", pcb, "/OUT"], kpy=True)
    step("board tracks lists /OUT's segments and via", code == 0 and "/OUT\tvia (117.4, 111.095)" in out
         and "B.Cu" in out, out[-600:])
    before = sha(pcb)
    body = '''
from board import Board
b = Board("testbed.kicad_pcb")
b.remove_tracks(refs=["C1"])
rep = b.save(dry_run=True)
print("UNCONNECTED", len(rep["unconnected_items"]))
'''
    code, out = script(body, d, kpy=True)
    m = re.search(r"-(\d+) removed", out)
    step("remove_tracks(refs) takes only C1's copper (dry run)", m and 2 <= int(m.group(1)) <= 5
         and "UNCONNECTED 0" not in out and sha(pcb) == before, out[-800:])


def checks_and_exports(d):
    pro, pcb = f"{d}/{NAME}.kicad_pro", f"{d}/{NAME}.kicad_pcb"
    code, out = run([sys.executable, CHECK, pro, "--json", f"{d}/out/check.json"])
    print("  " + "\n  ".join(out.splitlines()[-14:]))
    step("check.py passes", code == 0 and out.rstrip().endswith("PASS"), out[-1500:])
    step("check.py prints the JLC date", "JLC values as read on 20" in out, out[-500:])
    code, out = run([sys.executable, VIEW, "pcb", pcb, "-o", f"{d}/out/top.png"])
    step("view pcb picture", code == 0 and os.path.getsize(f"{d}/out/top.png") > 1000, out)
    code, out = run([sys.executable, VIEW, "pcb", pcb, "-o", f"{d}/out/bot.png", "--back", "--around", "U1",
                     "--layers", "B.SilkS,Edge.Cuts,F.Fab"])
    step("view pcb back, cropped", code == 0 and os.path.getsize(f"{d}/out/bot.png") > 500, out)

    K = kicad_cli()
    shutil.copy(f"{FAB}/jlc-fab.kicad_jobset", d)
    code, out = run([K, "jobset", "run", "--stop-on-error", "-f", "jlc-fab.kicad_jobset", f"{NAME}.kicad_pro"], cwd=d)
    z = f"{d}/fab/{NAME}_gerber.zip"
    names = zipfile.ZipFile(z).namelist() if os.path.exists(z) else []
    want = ["-F_Cu.gtl", "-B_Cu.gbl", "-F_Mask.gts", "-B_Mask.gbs", "-F_Silkscreen.gto", "-B_Silkscreen.gbo",
            "-Edge_Cuts.gm1", "-PTH.drl", "-NPTH.drl"]
    missing = [w for w in want if not any(n.endswith(w) for n in names)]
    step("fab jobset: zip holds the files the skill lists", code == 0 and not missing, f"missing {missing}; {out[-600:]}")

    shutil.copy(f"{ASM}/jlc-assembly.kicad_jobset", d)
    code, out = run([K, "jobset", "run", "--stop-on-error", "-f", "jlc-assembly.kicad_jobset", f"{NAME}.kicad_pro"],
                    cwd=d)
    a = f"{d}/fab/assembly"
    files = sorted(os.listdir(a)) if os.path.isdir(a) else []
    raw = f"{a}/{NAME}_cpl-all-pos.csv"
    step("assembly jobset: BOM and the -all-pos CPL the skill names", code == 0 and f"{NAME}_bom.csv" in files
         and os.path.exists(raw), f"files {files}; {out[-600:]}")
    if os.path.exists(raw):
        code, out = run([sys.executable, f"{ASM}/jlc_asm.py", "cpl", raw, f"{a}/{NAME}_cpl.csv"])
        cpl = open(f"{a}/{NAME}_cpl.csv").read() if code == 0 else ""
        step("jlc_asm cpl: Top/Bottom layer, raw file removed", "Top" in cpl and not os.path.exists(raw), out + cpl)
        code, out = run([sys.executable, f"{ASM}/jlc_asm.py", "check", f"{a}/{NAME}_bom.csv", f"{a}/{NAME}_cpl.csv"])
        step("jlc_asm check: BOM and CPL agree", code == 0, out)


def consistency():
    """The kicad_cli() helper is copied into each script (skills install separately); keep the copies identical."""
    bodies = {}
    for f in glob.glob(f"{SK}/*/*.py"):
        m = re.search(r"^def kicad_cli\(\):\n(?:    .*\n|\n)+", open(f).read(), re.M)
        if m:
            bodies[os.path.relpath(f, SK)] = m.group(0).strip()
    step("kicad_cli() is identical in every script", len(set(bodies.values())) == 1, str(list(bodies)))
    code, out = run([sys.executable, "-m", "py_compile"] + glob.glob(f"{SK}/*/*.py"))
    step("every script compiles", code == 0, out)


def main(argv):
    if argv:
        d = os.path.abspath(argv[0])
        if os.path.exists(d) and os.listdir(d):
            if not os.path.exists(os.path.join(d, MARK)):
                sys.exit(f"{d} exists and isn't a testbed from this script; refusing to wipe it")
            shutil.rmtree(d)
        os.makedirs(d)
        keep = True
    else:
        d, keep = tempfile.mkdtemp(prefix="kicad-smoke-"), False
    open(os.path.join(d, MARK), "w").write("Made by kicad-agent-skills/tests/smoke.py; rerunning it wipes this folder.\n")
    os.makedirs(f"{d}/out")
    print(f"testbed: {d}")
    consistency()
    schematic(d)
    schematic_edge_cases(d)
    netlist_tools(d)
    board(d)
    rerun_safety(d)
    checks_and_exports(d)
    print(f"\n{len(failures)} failed" + (": " + ", ".join(failures) if failures else ""))
    if not keep:
        shutil.rmtree(d)
    return len(failures)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
