---
name: kicad-fab-export
description: Make the zip of Gerbers and drill files JLCPCB takes, with a KiCad jobset (KiCad's own saved export recipe, run by kicad-cli) after a DRC gate, then render the Gerber files themselves with pygerber to check them - plus STEP and DXF files for enclosure and mechanical work. Covers putting the jobset template from this skill's folder into a project, inner layers on 4+ layer boards, naming the zip, checking what came out, and re-exporting after board changes. Use when the user asks for Gerbers, a fab zip, files to order a board, or a STEP/DXF of the board, or after a board change in a project that keeps its fab zip. For JLC assembly files (BOM and CPL), use kicad-assembly-export.
---

# Export a board for JLCPCB

`K` is `kicad-cli` (the `kicad-view` skill gives its path per OS and the version check).

A jobset (`.kicad_jobset`, KiCad 9+) is KiCad's own saved list of export jobs and where their output goes. The template
`jlc-fab.kicad_jobset` beside this skill holds JLC's settings (following JLC's KiCad guide):
- **Gerbers:**
  - copper, mask, silkscreen on both sides, and Edge.Cuts;
  - Protel extensions; no X2; netlist attributes;
  - silkscreen clipped at mask openings;
  - 4.6 mm format; zones refilled first.
- **Drill:** Excellon in mm, decimal, absolute origin; PTH and NPTH in separate files; oval holes as G85 slots.
- **Output:** one zip, `fab/<project>_gerber.zip` beside the project.

## Set it up once per project

```bash
cp <skill dir>/jlc-fab.kicad_jobset <project dir>/jlc-fab.kicad_jobset    # <skill dir>: the folder this SKILL.md is in
```

Then edit the copy where the project needs it:
- **Zip name:** `output_path`, e.g. `${KIPRJMOD}/fab/TeamName_gerber.zip`. Keep `${KIPRJMOD}`: a relative path
  resolves against the shell's current directory, not the project.
- **4 or more copper layers:** add `In1.Cu`, `In2.Cu`... to the Gerber job's `layers`, in stack order. They come
  out as `*-In1_Cu.g1`, `*-In2_Cu.g2`...
- **Stencil or JLC assembly:** add `F.Paste` (and `B.Paste`) to `layers`.
- **Layer names** are KiCad's canonical ones (`F.SilkS`, not `F.Silkscreen`).
- **Different settings:** the key names are KiCad's own (`common/jobs/job_export_pcb_*.cpp` in KiCad's source).
  A job's defaults differ from `kicad-cli`'s flags (for instance X2 and netlist attributes), so state every setting.

Commit the jobset with the project. It's data, not code.

## Export

```bash
"$K" pcb drc --severity-error --exit-code-violations --refill-zones --schematic-parity \
     -o <scratch>/drc.rpt board.kicad_pcb \
  && "$K" jobset run --stop-on-error -f jlc-fab.kicad_jobset board.kicad_pro
```

The DRC gate has to be a separate command: KiCad 10.0 still writes the zip when a DRC job inside the same jobset
fails.
- If DRC finds errors, show them (`kicad-check` skill) and fix them, or export anyway only when the user says so.
- Run the JLC passes of `kicad-check` before an order too: this gate only knows the project's own rules.

## Check what came out

- **The file list:** `unzip -l <zip>` should show, at the zip's root:
  - one file per layer: `*-F_Cu.gtl`, `*-B_Cu.gbl`, `*-F_Mask.gts`, `*-B_Mask.gbs`, `*-F_Silkscreen.gto`,
    `*-B_Silkscreen.gbo`, `*-Edge_Cuts.gm1`, and `*-In<n>_Cu.g<n>` for every inner layer;
  - `*-PTH.drl` and `*-NPTH.drl`.

  A board with 4 copper layers must have 4 copper files.
- **Hole sizes:** `grep -h '^T[0-9]*C' <unzipped>/*.drl` lists every drill diameter in mm. Compare the smallest
  with the fab's minimum.
- **Look at the Gerbers themselves, not KiCad's plot of the board.** An export mistake (a layer missing, a wrong
  option, silk outside the outline) shows only in the files. Render them with pygerber, in a scratch copy of the
  unzipped files:

  ```bash
  mkdir -p <scratch>/gbr/in <scratch>/gbr/out && unzip -q -o <zip> -d <scratch>/gbr/in
  cd <scratch>/gbr
  uv run --no-project --with pygerber pygerber render project -d 20 -o out/top.png \
      in/*-F_Cu.gtl in/*-F_Mask.gts in/*-F_Silkscreen.gto in/*-Edge_Cuts.gm1     # later files draw on top
  uv run --no-project --with pygerber pygerber render raster -t copper -d 20 -o out/B_Cu.png in/*-B_Cu.gbl
  ```

  - `-d` is dots per mm; 20 is enough for a whole board, and 60+ for close looks.
  - Do the same for the bottom, and each inner layer on its own.
  - Look for copper where it shouldn't be (shorts, slivers, pours cut in two), missing pads, silk on pads or past
    the edge, and an outline that isn't closed.
  - pygerber 2.4 can't read Excellon drill files. Check holes with the `T…C` list above.
- **JLC's order page** also renders the uploaded Gerbers, and for 4+ layers shows the layer order it read. Tell the
  user to look there before paying; it's how JLC will read the files.
- **Re-exports:** with an unchanged board, only the dates inside the files change. To confirm, `diff` the unzipped
  files with `grep -v -e CreationDate -e 'date '`.

## Mechanical files (enclosure, panel, drawings)

```bash
"$K" pcb export step -f -o <scratch>/board.step board.kicad_pcb               # board and part models, mm
"$K" pcb export dxf --mode-single -l Edge.Cuts --output-units mm -o <scratch>/outline.dxf board.kicad_pcb
```

- **STEP:**
  - Each part brings the 3D model its footprint names. A part without one is simply missing from the STEP, so
    check `(model ...)` entries if the enclosure check matters. The `kicad-board-edit` skill's `sch_to_board.py`
    restores models the API dropped.
  - `--board-only` leaves the parts out.
  - `--no-dnp` leaves DNP parts out.
  - `--drill-origin` or `--user-origin 0x0mm` move the origin.
- **DXF:** `--output-units` defaults to inches, so always pass `mm`. Add `F.Fab` or `F.CrtYd` for part outlines.
- These go to the user (or into the project only if it keeps them), not into the fab zip.

## Rules

- In a project that commits its fab zip, re-export after every board change and commit the zip with that change.
- Don't edit files inside the zip, and don't change the template's settings for one order. If a fab asks for something
  else, change the project's jobset and say why in the commit.
- For JLC assembly (BOM and pick-and-place files), use the `kicad-assembly-export` skill.
