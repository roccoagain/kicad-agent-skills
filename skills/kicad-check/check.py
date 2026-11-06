#!/usr/bin/env python3
"""Check a KiCad 10 project with KiCad's own checkers, and summarise the results in a few lines.

    python3 check.py board.kicad_pro            # ERC, DRC with schematic parity, JLC limits, JLC recommended
    python3 check.py board.kicad_pro --no-jlc   # just ERC and DRC
    python3 check.py board.kicad_pro --json out.json
    python3 check.py board.kicad_pro --rules-dir DIR   # JLC rule files from DIR instead (e.g. edited for 2 oz)

Any .kicad_pro, .kicad_sch or .kicad_pcb path works: the others are found beside it. Nothing in the project is
changed: DRC refills zones only in memory, and the JLC passes run on a copy with the rule files from this skill's
folder (2-layer or multilayer, picked from the board). Exit code 1 if ERC or DRC has errors, unconnected items or
parity issues, or the board breaks JLC's limits.

JLC pass results list only what the project's own DRC didn't already report: those are things JLC can't make
(limits) or would rather not (recommended).
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
IGNORE = {"lib_footprint_issues", "lib_footprint_mismatch"}     # a copy can't reach the project's libraries


def kicad_cli():
    for p in (os.environ.get("KICAD_CLI"), "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli",
              r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe"):
        if p and os.path.exists(p):
            return p
    return "kicad-cli"


def run_json(cmd, out):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if not os.path.exists(out):
        raise RuntimeError(" ".join(cmd) + " failed:\n" + r.stdout + r.stderr)
    return json.load(open(out))


def key(v):
    return (v["type"], tuple(sorted(i["description"] for i in v.get("items", []))))


def show(title, vs, n=8):
    errors = sum(v["severity"] == "error" for v in vs)
    print(f"{title}: {errors} errors, {len(vs) - errors} warnings")
    groups = {}
    for v in vs:
        groups.setdefault((v["severity"], v["type"]), []).append(v)
    for (sev, typ), items in sorted(groups.items())[:n]:
        first = "; ".join(i["description"] for i in items[0].get("items", []))
        print(f"  {sev} {typ} x{len(items)}: {first}")
    if len(groups) > n:
        print(f"  ... {len(groups) - n} more kinds")


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 2
    stem = os.path.splitext(os.path.abspath(argv[0]))[0]
    sch, pcb, pro = stem + ".kicad_sch", stem + ".kicad_pcb", stem + ".kicad_pro"
    jlc = "--no-jlc" not in argv
    K, report, failed = kicad_cli(), {}, False
    rules_dir = argv[argv.index("--rules-dir") + 1] if "--rules-dir" in argv else HERE
    with tempfile.TemporaryDirectory() as d:
        if os.path.exists(sch):
            erc = run_json([K, "sch", "erc", "--format", "json", "--severity-all", "-o", f"{d}/erc.json", sch],
                           f"{d}/erc.json")
            vs = [v for s in erc.get("sheets", []) for v in s.get("violations", [])]
            show("ERC", vs)
            failed |= any(v["severity"] == "error" for v in vs)
            report["erc"] = vs
        if not os.path.exists(pcb):
            return int(failed)
        drc = run_json([K, "pcb", "drc", "--format", "json", "--severity-all", "--refill-zones", "--schematic-parity",
                        "-o", f"{d}/drc.json", pcb], f"{d}/drc.json")
        vs, un, par = drc.get("violations", []), drc.get("unconnected_items", []), drc.get("schematic_parity", [])
        show("DRC", vs)
        print(f"  unconnected: {len(un)}, schematic parity: {len(par)}")
        for p in par[:8]:
            print(f"  parity {p['type']}: {'; '.join(i['description'] for i in p.get('items', []))}")
        failed |= any(v["severity"] == "error" for v in vs) or bool(un) or bool(par)
        report["drc"] = drc
        if jlc:
            text = open(pcb).read()
            inner = bool(re.search(r'\(\d+ "In\d+\.Cu"', text))
            kind = "multilayer" if inner else "2layer"
            seen = {key(v) for v in vs}
            for level in ("limits", "recommended"):
                w = os.path.join(d, level)
                os.makedirs(w)
                base = os.path.basename(stem)
                shutil.copy(pcb, f"{w}/{base}.kicad_pcb")
                if os.path.exists(pro):
                    shutil.copy(pro, f"{w}/{base}.kicad_pro")
                shutil.copy(os.path.join(rules_dir, f"jlcpcb-{kind}-{level}.kicad_dru"), f"{w}/{base}.kicad_dru")
                j = run_json([K, "pcb", "drc", "--format", "json", "--severity-all", "--refill-zones",
                              "-o", f"{w}/drc.json", f"{w}/{base}.kicad_pcb"], f"{w}/drc.json")
                new = [v for v in j.get("violations", []) if key(v) not in seen and v["type"] not in IGNORE]
                if level == "limits":
                    for v in new:
                        v["severity"] = "error"
                    failed |= bool(new)
                else:
                    for v in new:
                        v["severity"] = "warning"
                show(f"JLC {kind} {level}", new)
                report[f"jlc_{level}"] = new
        m = re.search(r"\(thickness ([\d.]+)\)", open(pcb).read())
        print(f"Board: {kind if jlc else ''} thickness {m.group(1) if m else '?'} mm "
              "(size, slots, mask, silk legibility: see the skill's checklist)")
    if "--json" in argv:
        json.dump(report, open(argv[argv.index("--json") + 1], "w"), indent=1)
    print("FAIL" if failed else "PASS")
    return int(failed)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
