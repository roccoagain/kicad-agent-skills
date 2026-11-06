# sch_to_board.py: KiCad's "Update PCB from Schematic", for when KiCad's GUI isn't used.
# Part of the kicad-board-edit skill. Copy it to a scratch folder and run it with KiCad's bundled python, with the
# board closed in the PCB editor:
#     <kicad python> -I sch_to_board.py board.kicad_pcb netlist.net [x y]
# netlist.net comes from `kicad-cli sch export netlist` (the default s-expression format, not kicadxml).
# It:
#   - adds the parts the board lacks, with their nets and the link to their symbol, in a row from (x, y) mm;
#   - brings every part's value, fields and DNP / BOM / position-file flags in line with the schematic;
#   - gives back 3D models the library footprint has and the board copy lost (KiCad 10.0's API drops a
#     footprint's model when it rotates it);
#   - reports what it won't change by itself: a different footprint, a pad on another net, a part that's on
#     the board but not in the schematic.
# Tested with KiCad 10.0.5. It writes the board in place: start from a clean git tree.
import os, re, sys
import pcbnew

board_path, net_path = sys.argv[1], sys.argv[2]
x0, y0 = (float(sys.argv[3]), float(sys.argv[4])) if len(sys.argv) > 4 else (0.0, 0.0)
proj = os.path.dirname(os.path.abspath(board_path))
SHARE = {"darwin": "/Applications/KiCad/KiCad.app/Contents/SharedSupport",
         "linux": "/usr/share/kicad"}.get(sys.platform, r"C:\Program Files\KiCad\10.0\share\kicad")
CONFIG = {"darwin": "~/Library/Preferences/kicad/10.0", "linux": "~/.config/kicad/10.0"}.get(
    sys.platform, os.path.join(os.environ.get("APPDATA", ""), "kicad", "10.0"))
ENV = {"KIPRJMOD": proj, "KICAD10_FOOTPRINT_DIR": f"{SHARE}/footprints", "KICAD10_3DMODEL_DIR": f"{SHARE}/3dmodels"}


def expand(uri):
    return re.sub(r"\$\{(\w+)\}", lambda m: os.environ.get(m.group(1), ENV.get(m.group(1), m.group(0))), uri)


def read_table(path, out):  # fp-lib-table; KiCad 10's global table nests the stock one as type "Table"
    if not os.path.exists(path):
        return
    for m in re.finditer(r'\(lib \(name "([^"]+)"\)\s*\(type "([^"]+)"\)\s*\(uri "([^"]+)"\)', open(path).read()):
        if m.group(2) == "Table":
            read_table(expand(m.group(3)), out)
        else:
            out.setdefault(m.group(1), expand(m.group(3)))


def sexpr(text):  # KiCad s-expression -> nested lists of strings
    stack = [[]]
    for t in re.findall(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()"]+', text):
        if t == "(":
            stack.append([])
        elif t == ")":
            done = stack.pop(); stack[-1].append(done)
        else:
            stack[-1].append(t[1:-1].replace('\\"', '"').replace("\\\\", "\\") if t[0] == '"' else t)
    return stack[0][0]


def get(node, key):
    return next((c for c in node[1:] if isinstance(c, list) and c and c[0] == key), None)


def val(node, key, default=""):
    c = get(node, key)
    return c[1] if c and len(c) > 1 else default


libs = {}
read_table(f"{proj}/fp-lib-table", libs)                       # project libraries first
read_table(os.path.expanduser(f"{CONFIG}/fp-lib-table"), libs)

# The s-expression netlist keeps KiCad's escaped net names ("/A{slash}B"), which the board uses.
# The kicadxml netlist unescapes them ("/A/B"): don't use it for this.
tree = sexpr(open(net_path).read())
pin_net = {}
for n in get(tree, "nets")[1:]:
    for node in (c for c in n[1:] if isinstance(c, list) and c[0] == "node"):
        pin_net[(val(node, "ref"), val(node, "pin"))] = val(n, "name")

board = pcbnew.LoadBoard(board_path)
# KiCad 10's bindings break objects read after an Add or Remove: read everything first.
on_board = {fp.GetReference(): fp for fp in board.GetFootprints()}
nets = {}
for pad in board.GetPads():
    nets.setdefault(pad.GetNetname(), pad.GetNet())
in_schematic, added, changed, restored, problems = set(), [], [], [], []
x = x0

for comp in get(tree, "components")[1:]:
    ref = val(comp, "ref"); in_schematic.add(ref)
    props = {val(p, "name"): val(p, "value") for p in comp[1:] if isinstance(p, list) and p[0] == "property"}
    fields = [(val(f, "name"), f[2] if len(f) > 2 else "") for f in (get(comp, "fields") or ["fields"])[1:]]
    fpid = val(comp, "footprint")
    fp = on_board.get(ref)
    if fp is None:
        if not fpid:
            problems.append(f"{ref}: no footprint in the schematic"); continue
        lib, name = fpid.split(":", 1)
        fp = pcbnew.FootprintLoad(libs[lib], name) if lib in libs else None
        if fp is None:
            problems.append(f"{ref}: footprint {fpid} not found"); continue
        fp.SetFPID(pcbnew.LIB_ID(lib, name))
        fp.SetReference(ref)
        sp = get(comp, "sheetpath")
        fp.SetPath(pcbnew.KIID_PATH(val(sp, "tstamps") + val(comp, "tstamps")))   # the link parity checks
        fp.SetSheetname(val(sp, "names")); fp.SetSheetfile(props.get("Sheetfile", ""))
        fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y0))); x += 10
        for p in fp.Pads():
            name_ = pin_net.get((ref, p.GetNumber()))
            if name_ is None:
                continue
            if name_ not in nets:
                item = pcbnew.NETINFO_ITEM(board, name_); board.Add(item); nets[name_] = item
            p.SetNet(nets[name_])
        added.append((ref, fp))
    else:
        if fpid and fp.GetFPID().GetUniStringLibId() != fpid:
            problems.append(f"{ref}: schematic says {fpid}, board has {fp.GetFPID().GetUniStringLibId()}"
                            " (replace it: delete it here, run this again, then re-place and re-route)")
        for p in fp.Pads():
            want = pin_net.get((ref, p.GetNumber()))
            if want is not None and p.GetNetname() != want:
                problems.append(f"{ref} pad {p.GetNumber()}: board net {p.GetNetname()}, schematic {want}")
    before = (fp.GetValue(), sorted((f.GetName(), f.GetText()) for f in fp.GetFields()),
              fp.IsDNP(), fp.IsExcludedFromBOM(), fp.IsExcludedFromPosFiles())
    fp.SetValue(val(comp, "value"))
    for fname, ftext in fields:
        if fname == "Footprint":
            continue
        new = fp.GetField(fname) is None
        fp.SetField(fname, ftext)                         # Datasheet and Description are fields too
        if new:
            f = fp.GetField(fname); f.SetVisible(False)
            f.SetLayer(pcbnew.B_Fab if fp.GetLayer() == pcbnew.B_Cu else pcbnew.F_Fab)
    # Always set these: library footprints carry their own (a test point excludes itself from the BOM).
    fp.SetDNP("dnp" in props)
    fp.SetExcludedFromBOM("exclude_from_bom" in props)
    fp.SetExcludedFromPosFiles("exclude_from_pos_files" in props)
    after = (fp.GetValue(), sorted((f.GetName(), f.GetText()) for f in fp.GetFields()),
             fp.IsDNP(), fp.IsExcludedFromBOM(), fp.IsExcludedFromPosFiles())
    if ref in on_board and before != after:
        changed.append(ref)
    if ref in on_board and not len(fp.Models()):
        fpid_ = fp.GetFPID(); lib_ = fpid_.GetLibNickname().wx_str()
        src = pcbnew.FootprintLoad(libs[lib_], fpid_.GetLibItemName().wx_str()) if lib_ in libs else None
        if src is not None and len(src.Models()):
            for m in src.Models():
                fp.Models().push_back(m)
            restored.append(ref)

for ref, fp in on_board.items():
    if ref not in in_schematic and not fp.IsBoardOnly():
        problems.append(f"{ref}: on the board but not in the schematic (delete it, or mark it board-only)")
for ref, fp in added:
    board.Add(fp)
board.Save(board_path)
print("added:", [r for r, _ in added])
print("updated:", changed)
print("3D model restored:", restored)
for p in problems:
    print("CHECK:", p)
