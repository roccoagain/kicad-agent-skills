---
name: kicad-export
description: "Exports order and mechanical files from a KiCad 10 board and verifies them: Gerbers, drill files and the JLCPCB fab zip after a DRC check, JLCPCB assembly files (BOM and CPL/pick-and-place) with LCSC, edge and rotation checks, and STEP and DXF files for enclosures. Use when the user asks for Gerbers, a fab zip, files to order a PCB, JLC assembly, a BOM, CPL or centroid file, or a STEP/DXF, or after a board change in a project that keeps its order files."
---

# Export a board

| Task | Read first |
|---|---|
| Gerbers, drill files, fab zip; STEP and DXF | [fab.md](fab.md) |
| BOM and CPL for JLC assembly; pre-order assembly checks | [assembly.md](assembly.md) |

An assembled order needs both, in this order:
1. Run the full check (`kicad-check`).
2. Add the paste layers to the fab jobset, for the stencil.
3. Pass the DRC gate and export the Gerbers ([fab.md](fab.md)).
4. Export and check the BOM and CPL ([assembly.md](assembly.md)).

The jobsets, the edge-clearance rule and `jlc_asm.py` are in this skill's folder.
