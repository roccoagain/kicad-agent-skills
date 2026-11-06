---
name: kicad-part-selection
description: Choose real parts for a KiCad design - electrical ratings with margin, a package that suits hand or JLC assembly, stock and lifecycle at the distributor, JLC Basic vs Extended parts and LCSC numbers, second sources - and confirm the footprint matches the exact orderable part number, then record MPN, manufacturer, datasheet and distributor numbers as schematic fields. Use when adding a part, replacing an out-of-stock or obsolete one, preparing a BOM for JLC assembly or a DigiKey/Mouser order, or when the user asks which part to use.
---

# Choose parts

A part is chosen when it has an exact orderable part number, a datasheet that proves its ratings, stock where the
board will be built, and a footprint checked against that exact package. Look these up: prices, stock and lifecycle
change monthly, so never answer from memory. Give the date you checked.

## 1. Requirements before searching

Write down, from the circuit (`kicad-design-review` gives the worst cases):
- **Electrical:**
  - voltage, current and power at the worst case, with margin: resistors at half their power rating or less;
    ceramic capacitors rated about twice the DC voltage they see (DC bias), or check the maker's curve;
  - tolerance, temperature coefficient, dielectric (C0G in signal paths and filters, X7R/X5R for decoupling);
  - for ICs: supply range, input and output ranges, and any absolute maximum the circuit can reach.
- **Package:**
  - Hand soldering with an iron: 0805 or 1206 passives, SOIC/SOT/TSSOP ICs; avoid QFN, BGA and 0402.
  - JLC Economic assembly: 0402 and up, IC pitch 0.4 mm and up.
  - Keep one package size per part type where the design allows (fewer reels, fewer mistakes).
- **Where it's built:** JLC assembly (LCSC stock) or hand assembly (DigiKey, Mouser...). The project's notes or
  existing BOM fields usually say. If neither says which package size a part should be, ask before choosing.

Rules by part type:
- **Resistors:** thick film suits most circuits. Use thin film in low-noise or precision paths (audio inputs,
  references, sense dividers, feedback networks of precision stages) for lower noise, lower temperature coefficient and
  tighter tolerance. Check dissipation at the worst case.
- **Ceramic capacitors:**
  - Allow for DC bias: take the maker's curve, or choose a rated voltage of about twice the working voltage. Check the
    dielectric's temperature range too.
  - In audio and other signal paths, choose C0G/NP0 or film. Class-2 dielectrics (X7R, X5R) are piezoelectric, so they
    pick up vibration, and their capacitance changes with voltage, which causes distortion.
  - In RF matching, choose C0G/NP0.
- **Inductors:** package sizes aren't standardised, so take the figures from the user or from the regulator datasheet's
  calculation:
  - inductance;
  - rated current;
  - saturation current, above the peak current with margin;
  - DC resistance;
  - shielded or unshielded (shielded if anything sensitive is nearby).

  Prefer a part that has a stock KiCad footprint. For RF matching, use high-Q parts made for RF.
- **ICs:** only a few orderable variants may exist, and the value field may carry only part of the number ("TLV9061").
  Read the ordering table, list the variants that fit (package, temperature grade, output option), and let the user
  choose the full number when the choice isn't obvious.

## 2. Search

- **JLC assembly:**
  - Search JLC's parts library (jlcpcb.com/parts) or LCSC (lcsc.com) by value and package.
  - Prefer **Basic** parts: they're always loaded, with no extra fee. **Extended** parts cost a loading fee per unique
    part on Economic assembly (about $3 each on JLC's price page in November 2026), so prefer **Preferred
    Extended**, which skip it on Economic.
  - Take the LCSC number (`C` + digits) and check stock against the build quantity, plus attrition.
- **Distributors:** DigiKey, Mouser and others, by parametric search.
  - Filter to "in stock", "active" and "cut tape" for small quantities.
  - Take the manufacturer part number (MPN) and the distributor's part number.
- **Lifecycle:** reject NRND (not recommended for new designs), last-time-buy and obsolete parts. Note single-source
  parts in the design notes, with a fallback when one exists (a pin-compatible part from another maker).
- **Search services:** if an MCP parts-search server is connected, use it for parametric search and stock, then confirm
  the result on the distributor's own page and in the datasheet.
- **Read the datasheet** for the exact part number: the suffix chooses package, temperature range, voltage option,
  tape and reel. Two suffixes of one part can have different pinouts.

## 3. Footprint for the exact part

- Find the package code in the datasheet's ordering table (TI's `DBV` is SOT-23-5, `DCK` is SC-70-5). Match it to
  a KiCad footprint by dimensions, not by name alone: compare pitch, body size and pad layout with the datasheet's
  land pattern.
- Check the pinout for that package against the symbol's pin numbers (`kicad-library` step 4). Generic symbols
  (an op-amp, a regulator) often assume one pinout that the chosen part doesn't follow.
- No stock footprint fits: make one (`kicad-library`).

## 4. Record it in the schematic

Set the project's field set on the symbol (`kicad-schematic`), e.g.:
- `Value` (what the BOM's Comment column shows), `Footprint`, `Datasheet` (a stable URL to the PDF);
- `MPN`, `Manufacturer`;
- `LCSC` for JLC assembly, `DigiKey` / `Mouser` for distributor orders;
- for passives, the ratings that matter (`Voltage`, `Dielectric`, `Tolerance`, `Power`).

The schematic is the source of the BOM. Regenerate any order file from it (`kicad-assembly-export`, or the project's
own export) rather than editing the order. Then carry the fields to the board (`sch_to_board.py`) so DRC parity
stays clean.

## Reporting a choice

For each part: the requirement, the chosen part number with its key ratings and the margin to each, package and
footprint, stock and price with the date checked, Basic/Extended at JLC, and one alternative. When stock or
lifecycle rules out the obvious part, say so.
