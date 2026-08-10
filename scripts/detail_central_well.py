"""Add the well head's real detail: a chevron braid band and a separate cap course.

From the reference photo (reference/well.png) and the user's reading of the
building:

  * a narrow band of chevron braid a quarter of the way down from the top,
    running on BOTH the inner and outer faces of the well wall;
  * the top 10% read as a separate course of flat cap stones, sitting slightly
    proud of both faces, with real joints between them;
  * twelve joints around, i.e. twelve cap stones.

Measured starting point (the well is a plain extruded ring -- only a top and a
bottom vertex loop, nothing between):

    outer radius   0.11500        inner radius  0.08867
    wall thickness 0.02633        height        0.08000
    z             -0.29200 .. -0.21200          128 facets around

Method
------
Everything is authored in the band's own (theta, z) space and mapped onto the
cylinder at the end -- the same approach the frieze seating uses, and the reason
none of this needs booleans.

Each chevron is one closed hexagon: up the lower edge of the V, across the end,
back down the upper edge, and across the other end. Swept radially from r_base
to r_base +- relief that gives a watertight 12-vertex solid per unit.

The cap stones are annular wedges, each spanning slightly less than its share of
the circle so the gap between them reads as a joint.

Nothing is cut away from the existing wall. The cap wraps the top of it and the
braid stands proud of it, so the wall's own geometry is untouched and the well's
overall height and silhouette are unchanged.

Runs upstream of the frieze chain, like the capital swap: opens CHAIN_BASE,
immediately saves to a new base file, edits there.

Run:  blender --background --python scripts/detail_central_well.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import json                                                       # noqa: E402
import math                                                       # noqa: E402

import bmesh                                                      # noqa: E402
import bpy                                                        # noqa: E402
from mathutils import Vector                                      # noqa: E402

from paths import (CORNICE_COLUMNS_NARROWED, CORNICE_WELL_DETAILED,  # noqa: E402
                    RENDERS)

WELL_NAME = "Bottomless central well wall"
OUT_RENDER = os.path.join(RENDERS, "well-detail")

# --- cap course -------------------------------------------------------------
CAP_FRAC = 0.10        # of the well's height, measured down from the top
CAP_JOINTS = 12        # twelve stones around
CAP_OVERHANG = 0.0030  # how far the cap sails past each wall face
CAP_JOINT_GAP = 0.0011 # angular gap between neighbouring stones, as arc length

# --- braid band -------------------------------------------------------------
BRAID_CENTRE_FRAC = 0.25   # of the well's height, down from the top
BRAID_H = 0.0072           # band height
BRAID_T_FRAC = 0.36        # stroke thickness, as a fraction of the chevron's length
BRAID_RELIEF = 0.0026      # how far the braid stands proud of the wall face
BRAID_REPEATS = 72         # chevrons around; 0.01004 arc each at the outer face

# How far each chevron reaches past its own repeat, as a fraction of it, so that
# neighbours interlock instead of sitting end to end.
#
# The overlap is only safe because the chevrons point ALONG the band rather than
# up it. A ">" presents a thin wedge at mid-height and two open arms at top and
# bottom, so the next one's apex passes between those arms at v = h/2 and the
# two nest without their solids ever intersecting. An up-pointing "^" is widest
# at the base and would collide.
BRAID_OVERLAP_FRAC = 0.65

# Safety note on the overlap: chevron i's apex lands at fraction
# overlap/(1+overlap) = 0.39 along chevron i+1, where i+1 still has a clear gap
# through its middle (its arms only converge at fraction 1.0). So the tip passes
# between the arms with room to spare. Overlap can go to roughly 0.9 before the
# solids would begin to touch.


def log(*a):
    print("[well-detail]", *a)
    sys.stdout.flush()


def measure(ob):
    ws = [ob.matrix_world @ v.co for v in ob.data.vertices]
    cx = (max(w.x for w in ws) + min(w.x for w in ws)) / 2.0
    cy = (max(w.y for w in ws) + min(w.y for w in ws)) / 2.0
    rs = [math.hypot(w.x - cx, w.y - cy) for w in ws]
    zs = [w.z for w in ws]
    m = {"cx": cx, "cy": cy, "r_in": min(rs), "r_out": max(rs),
         "z_lo": min(zs), "z_hi": max(zs)}
    m["h"] = m["z_hi"] - m["z_lo"]
    log(f"well: centre ({cx:+.5f}, {cy:+.5f})  r {m['r_in']:.5f}..{m['r_out']:.5f}  "
        f"z {m['z_lo']:+.5f}..{m['z_hi']:+.5f}  h {m['h']:.5f}")
    return m


def polar(m, theta, r, z):
    return Vector((m["cx"] + r * math.cos(theta), m["cy"] + r * math.sin(theta), z))


def solid_from_profile(bm, m, profile, r_inner, r_outer):
    """Sweep a closed (theta, z) profile radially into a watertight solid.

    `profile` is a list of (theta, z) in order around the closed outline. The
    result is that outline at r_inner, the same outline at r_outer, and a quad
    band joining them -- so it is closed by construction with no boolean.
    """
    inner = [bm.verts.new(polar(m, t, r_inner, z)) for t, z in profile]
    outer = [bm.verts.new(polar(m, t, r_outer, z)) for t, z in profile]
    n = len(profile)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((inner[i], inner[j], outer[j], outer[i]))
    bm.faces.new(list(reversed(inner)))
    bm.faces.new(outer)


def build_braid(m, z_centre, r_base, outward):
    """One face's worth of chevron braid, as a single mesh.

    `outward` True builds it standing proud of the outer face, False proud of
    the inner face (relief pointing toward the well's axis).
    """
    bm = bmesh.new()
    z0 = z_centre - BRAID_H / 2.0
    step = 2.0 * math.pi / BRAID_REPEATS
    h = BRAID_H
    span = step * (1.0 + BRAID_OVERLAP_FRAC)
    tf = BRAID_T_FRAC

    for i in range(BRAID_REPEATS):
        a = i * step
        # A ">" chevron pointing along the band, as a closed hexagon in
        # (fraction along the chevron, height): down the outer edge from the top
        # arm to the apex and on to the bottom arm, then back along the inner
        # edge. The apex sits at mid-height, which is what lets neighbours
        # interlock.
        pts = [(0.0, h), (1.0, h / 2.0), (0.0, 0.0),
               (tf, 0.0), (1.0 - tf, h / 2.0), (tf, h)]
        profile = [(a + s * span, z0 + v) for s, v in pts]
        if outward:
            solid_from_profile(bm, m, profile, r_base, r_base + BRAID_RELIEF)
        else:
            # Reverse the profile so the winding stays consistent when the
            # sweep direction flips inward.
            solid_from_profile(bm, m, list(reversed(profile)),
                               r_base - BRAID_RELIEF, r_base)

    name = f"WELL braid band {'outer' if outward else 'inner'}"
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def build_cap(m):
    """Twelve flat cap stones wrapping the top of the wall."""
    z_lo = m["z_hi"] - CAP_FRAC * m["h"]
    z_hi = m["z_hi"]
    r_in = m["r_in"] - CAP_OVERHANG
    r_out = m["r_out"] + CAP_OVERHANG

    step = 2.0 * math.pi / CAP_JOINTS
    # Convert the joint gap from arc length to angle at the outer face, so the
    # visible joint on the outside is the width actually asked for.
    half_gap = (CAP_JOINT_GAP / 2.0) / r_out

    made = []
    for i in range(CAP_JOINTS):
        a0 = i * step + half_gap
        a1 = (i + 1) * step - half_gap
        bm = bmesh.new()
        # A wedge: the annular footprint extruded in z. Built as a closed loop
        # of (theta, z) at the inner radius and the outer radius.
        steps = 8
        arc = [a0 + (a1 - a0) * k / steps for k in range(steps + 1)]
        lower = [polar(m, t, r_in, z_lo) for t in arc]
        lower += [polar(m, t, r_out, z_lo) for t in reversed(arc)]
        upper = [polar(m, t, r_in, z_hi) for t in arc]
        upper += [polar(m, t, r_out, z_hi) for t in reversed(arc)]
        vl = [bm.verts.new(p) for p in lower]
        vu = [bm.verts.new(p) for p in upper]
        n = len(vl)
        for k in range(n):
            j = (k + 1) % n
            bm.faces.new((vl[k], vl[j], vu[j], vu[k]))
        bm.faces.new(list(reversed(vl)))
        bm.faces.new(vu)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])

        me = bpy.data.meshes.new(f"WELL cap stone {i + 1:02d}")
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new(me.name, me)
        bpy.context.scene.collection.objects.link(ob)
        made.append(ob)

    log(f"cap: {CAP_JOINTS} stones, z {z_lo:+.5f}..{z_hi:+.5f} "
        f"({CAP_FRAC * 100:.0f}% of height = {CAP_FRAC * m['h']:.5f} thick), "
        f"r {r_in:.5f}..{r_out:.5f}, overhang {CAP_OVERHANG:.4f} each face")
    log(f"     {math.degrees(step):.3f} deg per stone, "
        f"outer arc {step * r_out:.5f}, joint gap {CAP_JOINT_GAP:.4f}")
    return made


def main():
    os.makedirs(OUT_RENDER, exist_ok=True)

    bpy.ops.wm.open_mainfile(filepath=CORNICE_COLUMNS_NARROWED)
    bpy.ops.wm.save_as_mainfile(filepath=CORNICE_WELL_DETAILED)

    well = bpy.data.objects.get(WELL_NAME)
    if well is None:
        raise SystemExit(f"{WELL_NAME!r} not found")
    m = measure(well)

    # Inherit the well's own material rather than inventing one -- an
    # unmateralled addition renders at Blender's default near-white and reads as
    # a fault rather than as new stone.
    mats = [s.material for s in well.material_slots if s.material]
    log(f"inheriting material: {[x.name for x in mats] or '<none>'}")

    z_braid = m["z_hi"] - BRAID_CENTRE_FRAC * m["h"]
    log(f"braid: centred z {z_braid:+.5f} ({BRAID_CENTRE_FRAC * 100:.0f}% down "
        f"from the top), band {BRAID_H:.4f} tall, relief {BRAID_RELIEF:.4f}")
    log(f"     {BRAID_REPEATS} chevrons -> outer arc "
        f"{2 * math.pi * m['r_out'] / BRAID_REPEATS:.5f}, inner arc "
        f"{2 * math.pi * m['r_in'] / BRAID_REPEATS:.5f} each")

    new = [build_braid(m, z_braid, m["r_out"], outward=True),
           build_braid(m, z_braid, m["r_in"], outward=False)]
    new += build_cap(m)

    for ob in new:
        ob.data.materials.clear()
        for mat in mats:
            ob.data.materials.append(mat)
        ob["well_detail"] = True

    tot_f = sum(len(o.data.polygons) for o in new)
    log(f"added {len(new)} objects, {tot_f} faces total")

    bpy.ops.wm.save_as_mainfile(filepath=CORNICE_WELL_DETAILED)
    log("SAVED", CORNICE_WELL_DETAILED)

    with open(os.path.join(OUT_RENDER, "well_report.json"), "w") as f:
        json.dump({"out": CORNICE_WELL_DETAILED, "well": m,
                   "cap_joints": CAP_JOINTS, "cap_frac": CAP_FRAC,
                   "braid_repeats": BRAID_REPEATS,
                   "braid_centre_z": z_braid,
                   "objects": [o.name for o in new]}, f, indent=2)


if __name__ == "__main__":
    main()
