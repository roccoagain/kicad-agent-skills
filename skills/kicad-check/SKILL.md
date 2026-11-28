---
name: kicad-check
description: "Looks at and verifies a KiCad 10 design without changing it: cropped schematic and PCB plots, 3D renders, pin nets, resistance between nets, connection and decoupling checks and revision diffs with view.py; ERC, DRC with schematic parity and JLCPCB's manufacturing limits with check.py. Use before and after any schematic or board edit, before committing, when there are ERC or DRC errors, to check a connection or see what a commit changed, or when the user asks to see or screenshot a design or whether a board can be manufactured. Whether the circuit and layout are right is kicad-review."
---

# Look at and check a KiCad design

| Task | Read first |
|---|---|
| Plots, renders, pin nets, `ohms`, `expect`, `decoupling`, comparing revisions; `kicad-cli`'s path | [view.md](view.md) |
| ERC, DRC and JLC's limits; custom rule files; reporting findings | [checks.md](checks.md) |

Both scripts are in this skill's folder, run with plain `python3`, and leave the project unchanged. Write their output
to `<scratch>`.

```bash
python3 <skill dir>/view.py sch board.kicad_sch -o <scratch>/sheet.png
python3 <skill dir>/view.py pins board.kicad_sch U2
python3 <skill dir>/check.py board.kicad_pro          # ends in PASS or FAIL
```

A PASS doesn't cover everything: read "What DRC can't check" in [checks.md](checks.md) before saying a board can be
manufactured.
