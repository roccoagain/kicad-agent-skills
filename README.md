# kicad-agent-skills

Agent Skills for designing PCBs in KiCad 10 with a coding agent: from a new project and schematic through parts,
placement, routing, checks (including JLCPCB's limits), review and simulation, to fab and assembly files and a
bring-up plan. The agent drives KiCad, so you don't have to open it.

They use KiCad's own interfaces (`kicad-cli`, jobsets, the IPC API via `kicad-python`, and bundled `pcbnew`) and work
with any agent that reads the open [Agent Skills](https://agentskills.io) format, such as Claude Code and OpenAI Codex.

## Skills

| Skill | What it does |
|---|---|
| `kicad-new-project` | Create the project, schematic and board files, rules, outline, jobsets |
| `kicad-schematic` | Edit the schematic as text; verify with netlist and ERC |
| `kicad-library` | Make and check symbols and footprints |
| `kicad-part-selection` | Choose orderable parts, JLC Basic/Extended, BOM fields |
| `kicad-view` | Plot and render the design, trace nets, compare revisions |
| `kicad-placement` | Decide where parts go and why |
| `kicad-routing` | Route the board: net classes, widths, pours, return paths |
| `kicad-board-edit` | Move parts and edit tracks, vias and pours through the IPC API |
| `kicad-check` | ERC, DRC, and DRC against JLCPCB's limits |
| `kicad-design-review` | Review the circuit by hand against datasheets |
| `kicad-simulate` | Simulate a stage with ngspice |
| `kicad-fab-export` | Gerber and drill zip, STEP and DXF |
| `kicad-assembly-export` | JLC BOM and CPL, with order checks |
| `kicad-bringup` | Write the bring-up and test plan |

## Requirements

- KiCad 10 (tested with 10.0.5 on macOS).
- For board editing, routing and placement: KiCad's API enabled (Preferences → Plugins → Enable KiCad API) and
  [uv](https://docs.astral.sh/uv/).
- For simulation: `ngspice`.

## Install

```bash
npx skills add roccoagain/kicad-agent-skills -g -a claude-code codex --skill '*' -y
```

Update with `npx skills update -g`. To edit the skills, symlink each folder in `skills/` into `~/.claude/skills/` or
`~/.agents/skills/` instead.

Other skill sets may share some of these names, so install only one set.

## Limits

- JLCPCB numbers were read from JLC's pages on 2026-11-05. Re-check them before an order.
- KiCad 10.0.5's API has bugs that `kicad-board-edit` works around.
- Reviews and simulations show their numbers and sources so you can check them.

## License

MIT, see [LICENSE](LICENSE).
