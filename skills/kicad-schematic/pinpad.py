#!/usr/bin/env python3
"""Compare a symbol's pin numbers with a footprint's pad numbers (KiCad 10 native pin stacks expanded).

    python3 pinpad.py <lib>.kicad_sym <Symbol> <lib>.pretty/<Footprint>.kicad_mod

Prints pins without a pad and pads without a pin; exit code 1 if either list is non-empty.
"""
import re
import sys


def pins(sym_lib, name):
    text = open(sym_lib).read()
    m = re.search(r'\n\t\(symbol "%s"\n' % re.escape(name), text)
    if not m:
        sys.exit(f"no symbol {name!r} in {sym_lib}")
    block = text[m.start() + 1:text.find("\n\t)\n", m.start() + 1)]
    parent = re.search(r'\(extends "([^"]+)"\)', block)        # derived symbols hold no pins of their own
    if parent:
        return pins(sym_lib, parent.group(1))
    out = set()
    for n in re.findall(r'\(number "([^"]*)"', block):
        stack = re.fullmatch(r"\[(.*)\]", n)                # "[2,5,8]" or "[1-4]"
        for part in (stack.group(1).split(",") if stack else [n]):
            part, a = part.strip(), part.strip().split("-")
            if stack and len(a) == 2:
                pre = re.match(r"\D*", a[0]).group(0)
                out.update(pre + str(i) for i in range(int(a[0][len(pre):]), int(a[1][len(pre):]) + 1))
            else:
                out.add(part)
    return out


def main(argv):
    if len(argv) != 3:
        print(__doc__)
        return 2
    p = pins(argv[0], argv[1])
    pads = set(re.findall(r'\(pad "([^"]*)"', open(argv[2]).read())) - {""}
    print("pins without a pad:", sorted(p - pads))
    print("pads without a pin:", sorted(pads - p))
    return int(bool(p ^ pads))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
