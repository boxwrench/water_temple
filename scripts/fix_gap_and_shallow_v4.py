"""Second follow-up pass on the frieze ring/molding, on top of v3.

Diagnosis (see conversation): the lion/scroll/anthemion masters and the
leaf-and-tongue molding are organic/relief shapes, not flat-backed panels --
their mesh mass is spread across the whole radial depth, with only a small
sliver (or, for the molding, none at all) actually touching the drum/backing
wall's outer surface. Measured facts:
  - drum outer surface: flat r=0.286 (z 0.198-0.313)
  - backing (above drum, z 0.313-0.395) outer surface: varies r=0.286-0.29
  - molding ("flat tongue"/"narrow upper fillet"/"small lower ridge") back
    (min r) sits at r=0.2955-0.2996 -- entirely OUTSIDE the wall, a real
    0.01+ air gap, not just a shading artifact.
  - ANTHEMION_C back sits at r=0.2868 -- only 0.0008-0.003 inside the wall's
    tightest point, effectively a hairline touch, reading as a gap.

Translating these objects further inward to close the gap was tried (v3) but
doesn't fully work: the molding is too thin (~0.004-0.005 total depth) to
survive enough inward push to reach the wall without also pushing its front
face behind the wall (i.e. it would vanish). And uniform translation of the
rounder lion/scroll/anthemion risks over-embedding the thin scroll while
still not guaranteeing full contact everywhere along their rounded backs.

Fix used here instead: leave every visible front surface exactly where it
is, and add hidden solid backing-filler blocks that physically bridge from
inside the wall out to just past each element's own current back extent.
These fillers sit entirely behind/within the visible object's own footprint
(same angular and vertical span, sized from real geometry, not guessed), so
they're never seen directly -- they just guarantee there is solid material
touching the wall everywhere behind the ring and the molding, closing the
gap "not just at the drum but above it" (the backing zone) too.

Also (per user "cuts...more shallow"): halves the leaf-and-tongue relief
depth again on top of the v3 shallowing pass (now ~1/4 of the original cut
depth).

Never touches the v3 file: opens it, immediately saves to a new working
file, and edits there.

Run:  blender --background --python fix_gap_and_shallow_v4.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import math

import bpy
import bmesh
from mathutils import Vector

from paths import chain_blend, chain_render  # noqa: E402

SRC_BLEND = chain_blend("frieze-ring-v3")
OUT_BLEND = chain_blend("frieze-ring-v4")
OUT_RENDER = chain_render("cornice-frieze-ring-v4")

CY = -0.5456366539001465
MODULE_ARC_DEG = 36.0

WALL_EMBED_R = 0.280      # comfortably inside the drum/backing solid (outer surface is 0.286-0.29)
OVERLAP = 0.003           # extra reach past each element's own back, guarantees contact
THETA_MARGIN = math.radians(1.0)
Z_MARGIN = 0.002

MOLDING_DEPTH_FACTOR = 0.5   # further halves the v3-shallowed relief depth


def log(*a):
    print("[fix-v4]", *a)
    sys.stdout.flush()


def world_theta_z_r(ob):
    mat = ob.matrix_world
    thetas, zs, rs = [], [], []
    for v in ob.data.vertices:
        w = mat @ v.co
        thetas.append(math.atan2(w.y - CY, w.x))
        zs.append(w.z)
        rs.append(math.hypot(w.x, w.y - CY))
    return thetas, zs, rs


def build_annular_wedge(name, r_in, r_out, z0, z1, theta0, theta1, segments=16):
    bm = bmesh.new()
    bi, bo, ti, to = [], [], [], []
    for i in range(segments + 1):
        t = theta0 + (theta1 - theta0) * i / segments
        ct, st = math.cos(t), math.sin(t)
        bi.append(bm.verts.new((r_in * ct, CY + r_in * st, z0)))
        bo.append(bm.verts.new((r_out * ct, CY + r_out * st, z0)))
        ti.append(bm.verts.new((r_in * ct, CY + r_in * st, z1)))
        to.append(bm.verts.new((r_out * ct, CY + r_out * st, z1)))
    bm.verts.ensure_lookup_table()
    for i in range(segments):
        bm.faces.new((bo[i], bo[i + 1], to[i + 1], to[i]))       # outer wall
        bm.faces.new((bi[i + 1], bi[i], ti[i], ti[i + 1]))       # inner wall
        bm.faces.new((bi[i], bo[i], bo[i + 1], bi[i + 1]))       # bottom cap
        bm.faces.new((ti[i + 1], to[i + 1], to[i], ti[i]))       # top cap
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    ob = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(ob)
    ob["cornice_master_component"] = True
    return ob


def add_filler_for_object(ob, tag):
    thetas, zs, rs = world_theta_z_r(ob)
    # atan2 wraps at +-pi; if this object's footprint straddles that seam,
    # unwrap by shifting angles below 0 up by 2*pi before taking min/max.
    if max(thetas) - min(thetas) > math.pi:
        thetas = [t + 2 * math.pi if t < 0 else t for t in thetas]
    t0, t1 = min(thetas) - THETA_MARGIN, max(thetas) + THETA_MARGIN
    z0, z1 = min(zs) - Z_MARGIN, max(zs) + Z_MARGIN
    r_out = min(rs) + OVERLAP
    name = f"FRIEZE_BACKING_FILLER_{tag}"
    build_annular_wedge(name, WALL_EMBED_R, r_out, z0, z1, t0, t1)
    log(f"filler for {ob.name}: theta=[{math.degrees(t0):.1f},{math.degrees(t1):.1f}] "
        f"z=[{z0:.4f},{z1:.4f}] r=[{WALL_EMBED_R},{r_out:.4f}]")


def add_frieze_fillers():
    prefixes = ("LION_", "SCROLL_L", "SCROLL_R", "ANTHEMION_")
    targets = [o for o in bpy.data.objects if o.name.startswith(prefixes)]
    log(f"building backing fillers for {len(targets)} frieze objects")
    for ob in targets:
        add_filler_for_object(ob, ob.name)


def add_molding_filler():
    molds = [o for o in bpy.data.objects if o.name.startswith("LEAF-AND-TONGUE")]
    all_r = []
    all_z = []
    for m in molds:
        _, zs, rs = world_theta_z_r(m)
        all_r += rs
        all_z += zs
    r_out = min(all_r) + OVERLAP
    z0, z1 = min(all_z) - Z_MARGIN, max(all_z) + Z_MARGIN
    log(f"molding filler ring: r=[{WALL_EMBED_R},{r_out:.4f}] z=[{z0:.4f},{z1:.4f}] (full 360, hidden behind molding)")
    build_annular_wedge("FRIEZE_BACKING_FILLER_MOLDING", WALL_EMBED_R, r_out, z0, z1, 0.0, 2 * math.pi, segments=128)


def shallow_molding_more():
    molds = [o for o in bpy.data.objects if o.name.startswith("LEAF-AND-TONGUE")]
    for ob in molds:
        mat = ob.matrix_world
        inv = mat.inverted()
        rs = [math.hypot((mat @ v.co).x, (mat @ v.co).y - CY) for v in ob.data.vertices]
        front_r = max(rs)
        for v in ob.data.vertices:
            w = mat @ v.co
            r = math.hypot(w.x, w.y - CY)
            if r >= front_r:
                continue
            theta = math.atan2(w.y - CY, w.x)
            new_r = front_r - (front_r - r) * MOLDING_DEPTH_FACTOR
            new_w = Vector((new_r * math.cos(theta), CY + new_r * math.sin(theta), w.z))
            v.co = inv @ new_w
        ob.data.update()
    log(f"shallowed cut depth again on {len(molds)} molding objects by factor {MOLDING_DEPTH_FACTOR}")


def main():
    os.makedirs(OUT_RENDER, exist_ok=True)

    bpy.ops.wm.open_mainfile(filepath=SRC_BLEND)
    bpy.ops.wm.save_as_mainfile(filepath=OUT_BLEND)

    shallow_molding_more()
    add_molding_filler()
    add_frieze_fillers()

    bpy.ops.wm.save_as_mainfile(filepath=OUT_BLEND)
    log("SAVED", OUT_BLEND)


if __name__ == "__main__":
    main()
