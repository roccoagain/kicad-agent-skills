---
name: kicad-part-selection
description: "Choose real, orderable parts for a KiCad design: ratings with margin, a package suited to hand or JLC assembly, stock, lifecycle, JLC Basic vs Extended, and a footprint that matches the exact part number. Records MPN, LCSC and distributor numbers in the schematic. Use when adding or replacing a part (out of stock, obsolete), building a BOM, or when the user asks which part to use."
---

# Choose parts

A part counts as chosen when it has all four of these:
- an exact orderable part number;
- a datasheet that proves its ratings;
- stock where the board will be built;
- a footprint checked against that exact package.

Stock, prices and lifecycle change monthly. Look them up, never answer from memory, and give the date you checked.

## 1. Requirements

Take the worst cases from `kicad-design-review`, then write down the following.

**Electrical ratings, with margin:**
- Resistors: power at no more than half the rating.
- Ceramic capacitors: rated at about twice the DC voltage they see, or confirmed on the maker's DC-bias curve.
- ICs: supply range, input and output ranges, and every absolute maximum the circuit can reach.
- Tolerance, tempco and dielectric where they matter.

**Package:**
- Hand soldering: 0805 or 1206 passives, and SOIC, SOT or TSSOP ICs. Avoid QFN, BGA and 0402.
- JLC Economic assembly: 0402 and up, and IC pitch of 0.4 mm and up.
- Use one size per part type where the design allows.

**Build:** JLC assembly (LCSC stock) or hand assembly (DigiKey, Mouser). The project notes or existing BOM fields
usually say which. If neither settles the package size, ask.

**By part type:**
- **Resistors:** thick film is fine for most uses. Use thin film in low-noise or precision paths (audio inputs,
  references, sense dividers, precision feedback).
- **Ceramic capacitors:** use C0G/NP0 or film in audio, signal and RF-matching paths. X7R/X5R capacitance changes with
  voltage, and they are microphonic. Check the dielectric's temperature range.
- **Inductors:** get these figures from the user, or from the regulator datasheet's calculation:
  - inductance;
  - rated current;
  - saturation current, above the peak with margin;
  - DCR;
  - shielded or not. Use shielded near anything sensitive.

  Prefer a part that has a stock KiCad footprint. For RF, use high-Q RF parts.
- **ICs:** the value field may hold only part of the number ("TLV9061"). Read the ordering table, list the variants that
  fit (package, temperature, options), and let the user pick when it isn't obvious.

## 2. Search

**JLC:**
- Search jlcpcb.com/parts or lcsc.com.
- Prefer **Basic** parts, which have no loading fee.
- **Extended** parts carry a fee for each unique part on Economic assembly (about $3 in November 2026). **Preferred
  Extended** parts skip that fee.
- Record the LCSC number (`C` + digits). Check stock against the build quantity plus attrition.

**DigiKey and Mouser:**
- Filter the parametric search to in stock, active, and cut tape.
- Record the MPN and the distributor's part number.

**Lifecycle:**
- Reject NRND, last-time-buy and obsolete parts.
- Record single-source parts in the design notes, with a fallback if one exists.

**MCP parts search:** if one is connected, use it, then confirm on the distributor's page and in the datasheet.

**Suffixes:** read the datasheet for the exact suffix. It selects package, temperature range and voltage option, and two
suffixes of one part can have different pinouts.

## 3. Footprint

- **Match by dimensions.** Find the package code in the ordering table (TI's `DBV` is SOT-23-5, `DCK` is SC-70-5).
  Match it to a KiCad footprint by pitch, body size and pads, not by name.
- **Check the pinout.** Compare that package's pinout with the symbol's pin numbers (`kicad-library` step 4). Generic
  symbols often assume a different pinout.
- **No stock footprint fits:** make one with `kicad-library`.

## 4. Record it

Set these fields on the symbol (`kicad-schematic`):
- `Value`, `Footprint`, and `Datasheet` (a stable PDF URL);
- `MPN` and `Manufacturer`;
- `LCSC`, `DigiKey` or `Mouser`, depending on the build;
- for passives, the ratings that matter: `Voltage`, `Dielectric`, `Tolerance` and `Power`.

The schematic is the BOM's source, so regenerate order files from it (`kicad-assembly-export`). Then carry the fields
to the board with `board.py sync` (`kicad-board-edit`).

## Report

For each part, give:
- the requirement;
- the part number, its key ratings, and the margin on each;
- the package and footprint;
- stock and price, with the date checked;
- Basic or Extended at JLC;
- one alternative.

If stock or lifecycle rules out the obvious part, say so.
