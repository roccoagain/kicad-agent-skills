---
name: kicad-check
description: Check a KiCad 10 design with KiCad's own checkers - ERC on the schematic, DRC with schematic parity on the board, and DRC again against JLCPCB's fabrication limits and recommended values using the rule files in this skill's folder (separate files for 2-layer and multilayer boards) - plus the short checklist DRC can't express (board size and thickness, slots, mask, silk legibility). Use after every schematic or board change, before committing, and when the user asks whether a board is ready to order or manufacturable at JLC.
---

# Check a KiCad design

All of it is `kicad-cli` (`K` below; the `kicad-view` skill gives its path per OS and the version check). Nothing
is modified, except that the JLC passes run on a copy in a temporary folder outside the project (`<scratch>`
below).

## 1. Schematic: ERC

```bash
"$K" sch erc --severity-error --severity-warning --format json -o <scratch>/erc.json board.kicad_sch
```

## 2. Board: the project's own DRC and schematic parity

```bash
"$K" pcb drc --refill-zones --schematic-parity --severity-all --format json -o <scratch>/drc.json board.kicad_pcb
```

This is what KiCad's DRC dialog shows:
- the project's rules (Board Setup plus its `.kicad_dru`);
- unrouted nets;
- whether the board matches the schematic (parts, footprints, values, fields, pad nets).

Options:
- `--format report` gives a readable text report.
- `--severity-error --exit-code-violations` gives a pass/fail gate (exit 5 means errors).
- `--refill-zones` refills in memory only. The file changes only with `--save-board`.

## 3. Board: JLCPCB's limits and recommended values

The rule files beside this skill encode JLC's standard FR-4 process for 1 oz outer copper. Pick the pair for the
board's copper layer count (the `(layers ...)` list in the `.kicad_pcb`, or `get_copper_layer_count()`):

| Board | Limits (errors) | Recommended (warnings) |
|---|---|---|
| 1 or 2 layers | `jlcpcb-2layer-limits.kicad_dru` | `jlcpcb-2layer-recommended.kicad_dru` |
| 4 layers or more | `jlcpcb-multilayer-limits.kicad_dru` | `jlcpcb-multilayer-recommended.kicad_dru` |

They run in place of the project's own custom rules, on a copy:

```bash
W=$(mktemp -d <scratch>/jlc.XXXX)
cp board.kicad_pcb board.kicad_pro "$W/"
cp <skill dir>/jlcpcb-2layer-limits.kicad_dru "$W/board.kicad_dru"   # <skill dir>: this SKILL.md's folder; same stem as the board
"$K" pcb drc --refill-zones --severity-all --format json -o "$W/drc.json" "$W/board.kicad_pcb"
```

Then the same with the recommended file in a second folder.

- **Limits pass:** anything here that the project's pass (step 2) doesn't report is outside JLC's capability. The
  board can't be made as drawn: that's an error, whatever severity DRC prints.
- **Recommended pass:** anything new here is below JLC's preferred values or legibility (PTH ring, via size, 1.0 mm
  text, 0.15 mm strokes, 0.15 mm silk to pads). JLC builds it anyway: report it as a warning, and fix it when the
  user wants.
- Ignore `lib_footprint_issues` in these passes: the copy can't reach the project's library tables.
- The board-setup minimums in the `.kicad_pro` still apply in the copy. That's fine, because step 2 already reports
  anything below them.
- **2 oz outer copper:** change the values each file marks `[2oz]`, in a copy of the file, not the skill's own.

### Editing a rule file: comments go on their own line

KiCad 10.0.5 silently ignores every rule after a comment that shares a line with code, such as
`(constraint clearance (min 0.1mm)))   # note`. It gives no error and no warning, and those rules simply never run.
Put `#` comments on lines of their own.

After editing any `.kicad_dru`, prove it loads to the end:
1. Copy it and append `(rule "canary" (condition "A.Type == 'Track'") (constraint track_width (min 1000mm)))`.
2. Run DRC with the copy on a board with tracks.
3. Check that violations naming rule `'canary'` appear.

To check one rule, raise its minimum absurdly in a copy and look for its name in the report. (Some rules are
shadowed on purpose: for one constraint, the last matching rule wins.)

JLC's numbers are from https://jlcpcb.com/capabilities/pcb-capabilities, read 2026-11-05. Re-check them before an
order, and update the files if JLC changes them.

## 4. What DRC can't check

Read these from the `.kicad_pcb` and say what you found. Values are JLC's standard FR-4 process:

- **Size:**
  - Outline at least 3 × 3 mm (castellated boards: 10 × 10 mm).
  - Maximum 670 × 600 mm (2-layer) or 663 × 593 mm (4-layer). Check any free-board size limit the user has too,
    often 100 × 100 mm.
- **Stackup:**
  - Thickness from `(general (thickness ...))` should be one of 0.4, 0.6, 0.8, 1.0, 1.2, 1.6 or 2.0 mm.
  - Outer copper: 1 or 2 oz. JLC's inner copper defaults to 0.5 oz.
- **Slots** (oval drills, `(drill oval W H)`):
  - Plated at least 0.5 mm wide on 2-layer boards. JLC's table says 0.35 mm on multilayer, but the same row's text
    says 0.5 mm, so prefer 0.5 mm.
  - Non-plated at least 1.0 mm wide.
  - Length at least twice the width.
  - Rectangular cut-outs need rounded corners.
- **Edges:**
  - Copper at least 0.2 mm from a routed edge (the rule files check this) and 0.4 mm from a V-cut.
  - Castellated holes at least 0.5 mm, ENIG only.
- **Solder mask:**
  - Bridges between pads at least 0.10 mm (0.13 mm for black or white mask).
  - Board Setup → Solder Mask/Paste "Minimum web width" should match, so DRC's `solder_mask_bridge` check uses it.
- **Silk legibility:**
  - Silkscreen lines at least 0.15 mm wide. Stock KiCad footprints draw 0.12 mm: JLC prints them, but say so.
  - Text stroke at least 1/6 of its height (the recommended files check 1.0 mm height and 0.15 mm stroke).
- **Assembly at JLC:** see the `kicad-assembly-export` skill (part-to-edge distance, LCSC numbers, rotations).

## Reporting

- Lead with errors, then warnings, each with its location (board mm) and what it means physically. Group repeats
  ("21 × silkscreen clipped by the board edge, all at the jack footprints").
- Check the project's design notes (DESIGN.md, or the agent instructions in CLAUDE.md/AGENTS.md) for findings
  already accepted on purpose. Say "expected" for those, rather than "fixing" a recorded decision.
- Propose a fix for each new finding. After fixing, run the check again until the errors are gone. Use the
  `kicad-view` skill to look at the spots it names.
