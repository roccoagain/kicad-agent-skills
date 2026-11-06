---
name: kicad-check
description: Check a KiCad 10 design with KiCad's own checkers - ERC on the schematic, DRC with schematic parity on the board, and DRC again against JLCPCB's fabrication limits and recommended values using the rule files in this skill's folder (separate files for 2-layer and multilayer boards) - plus the short checklist DRC can't express (board size and thickness, slots, mask, silk legibility). Use after every schematic or board change, before committing, and when the user asks whether a board is ready to order or manufacturable at JLC.
---

# Check a KiCad design

`K` is `kicad-cli`. See `kicad-view` for its path. These checks don't modify the project. The JLC passes run on a copy
in `<scratch>`.

## 1. ERC

```bash
"$K" sch erc --severity-error --severity-warning --format json -o <scratch>/erc.json board.kicad_sch
```

## 2. DRC with the project's rules and schematic parity

```bash
"$K" pcb drc --refill-zones --schematic-parity --severity-all --format json -o <scratch>/drc.json board.kicad_pcb
```

This covers the same ground as KiCad's DRC dialog:
- the project's rules;
- unrouted nets;
- whether the board matches the schematic.

Options:
- `--format report` gives readable text.
- `--severity-error --exit-code-violations` turns the run into a pass/fail gate. Exit code 5 means errors.
- `--refill-zones` changes the file only if you add `--save-board`.

## 3. DRC with JLCPCB's rules

The rule files in this skill's folder are for JLC's standard FR-4 process with 1 oz outer copper. Choose them by
copper layer count:

| Board | Limits (errors) | Recommended (warnings) |
|---|---|---|
| 1–2 layers | `jlcpcb-2layer-limits.kicad_dru` | `jlcpcb-2layer-recommended.kicad_dru` |
| 4+ layers | `jlcpcb-multilayer-limits.kicad_dru` | `jlcpcb-multilayer-recommended.kicad_dru` |

Run each file on its own copy of the board. The rule file must have the same stem as the board:

```bash
W=$(mktemp -d <scratch>/jlc.XXXX)
cp board.kicad_pcb board.kicad_pro "$W/"
cp <skill dir>/jlcpcb-2layer-limits.kicad_dru "$W/board.kicad_dru"
"$K" pcb drc --refill-zones --severity-all --format json -o "$W/drc.json" "$W/board.kicad_pcb"
```

**Reading the results**
- **Limits pass:** anything step 2 didn't report means JLC can't make the board as drawn. Treat it as an error,
  whatever severity DRC prints.
- **Recommended pass:** anything new is a warning. JLC will still build it.
- **Library warnings:** ignore `lib_footprint_issues`. The copy can't reach the project's library tables.
- **2 oz outer copper:** edit the values marked `[2oz]` in a copy of the rule file.

**Editing a rule file**
- **Comments on their own line.** KiCad 10.0.5 silently skips every rule after a `#` comment that shares a line with
  code.
- **Prove the whole file loads.** Append this rule to a copy:

  ```
  (rule "canary" (condition "A.Type == 'Track'") (constraint track_width (min 1000mm)))
  ```

  Run DRC on a board that has tracks, and confirm that violations of `canary` appear.
- **Test one rule:** raise its minimum to an absurd value in a copy. For a given constraint, the last matching rule
  wins.

JLC's numbers come from jlcpcb.com/capabilities/pcb-capabilities, read on 2026-11-05. Re-check them before an order.

## 4. What DRC can't check

Read these from the `.kicad_pcb` and report them. The values are for JLC's standard FR-4 process.

- **Size:**
  - minimum 3 × 3 mm, or 10 × 10 mm if castellated;
  - maximum 670 × 600 mm (2-layer) or 663 × 593 mm (4-layer);
  - any price-tier limit the user mentions, often 100 × 100 mm.
- **Thickness** (`(general (thickness ...))`): one of 0.4, 0.6, 0.8, 1.0, 1.2, 1.6 or 2.0 mm.
- **Copper:** 1 or 2 oz outer. Inner layers default to 0.5 oz.
- **Slots** (`(drill oval W H)`):
  - plated slots at least 0.5 mm wide;
  - non-plated slots at least 1.0 mm wide;
  - length at least twice the width;
  - rectangular cut-outs have rounded corners.
- **Edges:**
  - copper at least 0.4 mm from a V-cut;
  - castellated holes at least 0.5 mm, ENIG only.
- **Solder mask:**
  - mask bridges at least 0.10 mm (0.13 mm on black or white mask);
  - Board Setup's "Minimum web width" should match.
- **Silkscreen:**
  - line width at least 0.15 mm. Stock footprints use 0.12 mm, which JLC prints, but mention it;
  - text stroke at least 1/6 of the text height.
- **Assembly:** see `kicad-assembly-export`.

## Report

- **Order:** errors first, then warnings. For each, give the location (board mm) and its physical meaning.
- **Repeats:** group them, e.g. "21 × silk clipped by edge, all at the jack footprints".
- **Accepted findings:** check the design notes (DESIGN.md, CLAUDE.md, AGENTS.md) and mark findings already accepted
  there as "expected".
- **Fixes:** propose a fix for each new finding, and re-run the checks until no errors remain. Look at each spot with
  `kicad-view`.
