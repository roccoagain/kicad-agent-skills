"""IPC-7351B nominal land pattern for a leaded IC, computed the way KiCad's footprint generator does it.

Usage: python3 ipc_land.py <family> Lmin Lmax Tmin Tmax Wmin Wmax
  All in mm, from the datasheet's package drawing (min and max columns; nominal +/- t gives nom-t, nom+t):
    L = lead span, outer toe to outer toe (QFN/DFN: the body size)
    T = lead (terminal) length
    W = lead width
  family: gw       gull wing (SOIC, SSOP, TSSOP, QFP, SOT), pitch > 0.625 mm
          gw-fine  gull wing, pitch <= 0.625 mm
          qfn      no-lead (QFN, DFN) with a toe fillet
Prints Z (outer pad edge to outer pad edge), G (inner to inner), X (pad width), the pad size and centre.
"""
import math
import sys

# Nominal (density level B) fillet goals: toe, heel, side.
FILLETS = {"gw": (0.35, 0.35, 0.03), "gw-fine": (0.35, 0.35, -0.02), "qfn": (0.30, 0.00, -0.04)}
F, P = 0.10, 0.05  # fabrication and placement tolerance


def rnd(v):
    return round(v / 0.05) * 0.05


fam, Lmin, Lmax, Tmin, Tmax, Wmin, Wmax = sys.argv[1], *map(float, sys.argv[2:8])
jt, jh, js = FILLETS[fam]
CL, CT, CW = Lmax - Lmin, Tmax - Tmin, Wmax - Wmin  # tolerances are full ranges
CS = math.sqrt(CL**2 + 2 * CT**2)                  # heel-to-heel tolerance, root-sum-square
Smin, Smax = Lmin - 2 * Tmax, Lmax - 2 * Tmin
Smax -= ((Smax - Smin) - CS) / 2                   # Smax reduced to the RSS tolerance
Z = rnd(Lmin + 2 * jt + math.sqrt(CL**2 + F**2 + P**2))
G = rnd(Smax - 2 * jh - math.sqrt(CS**2 + F**2 + P**2))
X = rnd(Wmin + 2 * js + math.sqrt(CW**2 + F**2 + P**2))
print(f"Z={Z:.2f} G={G:.2f} X={X:.2f} -> pad {(Z - G) / 2:.3f} x {X:.3f} mm, "
      f"pad centres at +/-{(Z + G) / 4:.4f} mm from the part's centre")
