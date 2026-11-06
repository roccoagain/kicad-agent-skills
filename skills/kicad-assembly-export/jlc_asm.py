#!/usr/bin/env python3
"""JLC assembly files from KiCad's exports.

    python3 jlc_asm.py cpl fab/assembly/<p>_cpl-all-pos.csv fab/assembly/<p>_cpl.csv [jlc-rotations.csv]
    python3 jlc_asm.py check fab/assembly/<p>_bom.csv fab/assembly/<p>_cpl.csv

cpl: KiCad's position file (Ref,Val,Package,PosX,PosY,Rot,Side) -> JLC's CPL, applying rotation offsets from
jlc-rotations.csv (columns Match,Offset; Match is a designator or a Package value, a designator row wins). Deletes
the raw file.
check: BOM against CPL: parts in one file only, placed parts without an LCSC number, malformed LCSC numbers, sides,
oversized rows. Exit code 1 if any part is in one file only or lacks a number.
"""
import csv
import os
import re
import sys


def cpl(raw, out, corr=""):
    offsets = {}
    if corr and os.path.exists(corr):
        offsets = {r["Match"]: float(r["Offset"]) for r in csv.DictReader(open(corr, newline=""))}
    with open(raw, newline="") as f, open(out, "w", newline="") as g:
        w = csv.writer(g)
        w.writerow(["Designator", "Val", "Package", "Mid X", "Mid Y", "Rotation", "Layer"])
        for r in csv.DictReader(f):
            rot = (float(r["Rot"]) + offsets.get(r["Ref"], offsets.get(r["Package"], 0.0))) % 360
            w.writerow([r["Ref"], r["Val"], r["Package"], r["PosX"], r["PosY"], f"{rot:g}", r["Side"]])
    os.remove(raw)
    print(f"wrote {out}")


def check(bom_path, cpl_path):
    bom = list(csv.DictReader(open(bom_path, newline="")))
    rows = list(csv.DictReader(open(cpl_path, newline="")))
    in_bom = {d.strip(): r for r in bom for d in r["Designator"].split(",")}
    in_cpl = {r["Designator"]: r for r in rows}
    found = {
        "in the BOM, not placed": sorted(set(in_bom) - set(in_cpl)),
        "placed, not in the BOM": sorted(set(in_cpl) - set(in_bom)),
        "placed, no LCSC number": sorted(d for d in in_cpl if d in in_bom and not in_bom[d]["JLCPCB Part #"].strip()),
    }
    for k, v in found.items():
        print(f"{k}: {v}")
    print("odd LCSC numbers:", sorted({r["JLCPCB Part #"] for r in bom if r["JLCPCB Part #"].strip()
                                       and not re.fullmatch(r"C\d+", r["JLCPCB Part #"].strip())}))
    print("sides:", sorted({r["Layer"] for r in rows}))
    print("BOM rows over 200 designators:", [r["Comment"] for r in bom if len(r["Designator"].split(",")) > 200])
    return int(any(found.values()))


def main(argv):
    if len(argv) >= 3 and argv[0] == "cpl":
        cpl(*argv[1:4])
    elif len(argv) == 3 and argv[0] == "check":
        return check(argv[1], argv[2])
    else:
        print(__doc__)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
