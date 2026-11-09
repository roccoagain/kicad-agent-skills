# kicad-agent-skills

Agent Skills for designing PCBs in KiCad 10 with a coding agent: from a new project and schematic through parts,
placement, routing, checks (including JLCPCB's limits), review and simulation, to fab and assembly files and a
bring-up plan. The agent drives KiCad, so you don't have to open it.

Edits go through small Python scripts bundled with the skills (`sch.py`, `board.py`, `view.py`, `check.py`): the
agent calls a few verbs by part and pin, and the scripts handle the file formats, pin geometry and KiCad's traps,
then run ERC or DRC on every save. Checks and exports use KiCad's own `kicad-cli` and jobsets. They work with any
agent that reads the open [Agent Skills](https://agentskills.io) format, such as Claude Code and OpenAI Codex.

## Skills

| Skill | What it does |
|---|---|
| `kicad-new-project` | Create the project, schematic and board files, rules, outline, jobsets |
| `kicad-schematic` | Draw and edit the schematic with `sch.py`; ERC and lint on every save |
| `kicad-library` | Make and check symbols and footprints (`ipc_land.py`, `pinpad.py`) |
| `kicad-part-selection` | Choose orderable parts, JLC Basic/Extended, BOM fields |
| `kicad-view` | Cropped plots, pin nets, resistance between nets, connection and decoupling checks, revision diffs with `view.py` |
| `kicad-placement` | Place parts; compare candidates with `board.py score` |
| `kicad-routing` | Route by hand: net classes, widths, clearances, pours |
| `kicad-board-edit` | Board, sync from schematic, placement, tracks, vias, pours with `board.py` |
| `kicad-check` | ERC, DRC and JLCPCB's limits in one run with `check.py` |
| `kicad-design-review` | Review the circuit by hand against datasheets |
| `kicad-simulate` | Simulate a stage with ngspice |
| `kicad-fab-export` | Gerber and drill zip, STEP and DXF |
| `kicad-assembly-export` | JLC BOM and CPL, with order checks (`jlc_asm.py`) |
| `kicad-bringup` | Write the bring-up and test plan |

## Requirements

- KiCad 10 (tested with 10.0.5 on macOS).
- Python 3 for `sch.py`, `view.py`, `check.py` and the other helpers; KiCad's bundled Python for `board.py`.
- poppler (`pdftoppm`, `pdfinfo`) for pictures.
- For checking symbols and footprints as pictures: `rsvg-convert` (librsvg).
- For rendering Gerbers: `uv` (runs pygerber without installing it).
- For simulation: `ngspice`.

## Install

```bash
npx skills add roccoagain/kicad-agent-skills -g -a claude-code codex --skill '*' -y
```

Update with `npx skills update -g`. To edit the skills, symlink each folder in `skills/` into `~/.claude/skills/` or
`~/.agents/skills/` instead.

Other skill sets may share some of these names, so install only one set.

## Testing

```bash
python3 tests/smoke.py [DIR]
```

builds a small project from nothing with the scripts (schematic with a multi-unit op-amp, board, placement, a hand
route, pours), runs every checker and both jobsets, and prints PASS or FAIL per step. Without DIR it works in a
temporary folder. Run it after changing a script or upgrading KiCad.

`tests/evals.json` holds task-level evaluations in Anthropic's format (query, skills, expected behaviour) against
the smoke test's project. Run them by giving each query to a fresh agent with the skills installed and comparing
what it does with the expected behaviour, with each model you plan to use.

## Limits

- JLCPCB numbers were read from JLC's pages on 2026-11-05. Re-check them before an order.
- KiCad 10.0.5's API has bugs that `kicad-board-edit` works around.
- Reviews and simulations show their numbers and sources so you can check them.

## License

MIT, see [LICENSE](LICENSE).
