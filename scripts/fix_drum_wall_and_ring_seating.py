"""Three follow-up fixes to the propagated frieze ring, all on top of the
thick-drum working file:

1. The drum "thickening" only pushed the top and bottom annular CAP rings
   inward -- there was never a continuous inner wall between them (the
   original mesh's inner surface only existed as two thin lips at the very
   top and bottom edges, nothing in between). From outside this was
   invisible, but looking into the opening or from underneath it doesn't
   read as solid. Bridges the (now-thickened) bottom cap ring to the top
   cap ring with a real cylindrical wall so it is solid top to bottom.

2. The LEAF-AND-TONGUE shelf molding was only ever built for one 36-degree
   cell and never propagated when the frieze ring was -- ANTHEMION/RINCEAUX/
   lion objects got ten repeats, the molding did not. Propagates it the
   same way: nine rotated copies (independent mesh data, since these
   objects' vertices are baked world-space coordinates, not object
   transforms) at 36-degree steps, same period as the lion spacing, so it
   stays centered under every lion.

3. The frieze ring (lion/anthemion/scroll) was seated with its back plane
   at SLOT_R_BACK=0.2921, which is *outside* the drum's actual outer
   surface (r=0.286) -- it read as floating in front of the wall rather
   than being carved into it. Pulls every frieze object radially inward by
   the difference (0.0061) so the back plane sits flush with the drum's
   real outer surface. Pure translation along each object's own radial
   direction -- rotation and relative offsets (e.g. the anthemion's
   proud-of-the-scroll push) are unchanged.

Never touches the thick-drum file: opens it, immediately saves to a new
working file, and edits there.

Run:  blender --background --python fix_drum_wall_and_ring_seating.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import math

import bpy
import bmesh
from mathutils import Vector

from paths import DRUM_INNER_R, chain_blend, chain_render  # noqa: E402

SRC_BLEND = chain_blend("frieze-ring-thick-drum")
OUT_BLEND = chain_blend("frieze-ring-v2")
OUT_RENDER = chain_render("cornice-frieze-ring-v2")

CY = -0.5456366539001465
MODULE_ARC_DEG = 36.0

DRUM_Z_BOT = 0.198
DRUM_Z_TOP = 0.313
Z_TOL = 0.0005

OLD_SLOT_R_BACK = 0.2921
NEW_SLOT_R_BACK = 0.286   # flush with the drum's actual outer surface
RING_PULL_IN = OLD_SLOT_R_BACK - NEW_SLOT_R_BACK


def log(*a):
    print("[fix-drum-ring]", *a)
    sys.stdout.flush()


def bridge_drum_inner_wall():
    drum = bpy.data.objects["Plain drum wall"]
    mesh = drum.data

    def ring(z_target):
        pts = []
        for v in mesh.vertices:
            w = drum.matrix_world @ v.co
            r = math.hypot(w.x, w.y - CY)
            if abs(w.z - z_target) < Z_TOL and abs(r - DRUM_INNER_R) < 0.001:
                theta = math.atan2(w.y - CY, w.x)
                pts.append((theta, v.index))
        pts.sort(key=lambda p: p[0])
        return pts

    bottom = ring(DRUM_Z_BOT)
    top = ring(DRUM_Z_TOP)
    log(f"bottom inner ring: {len(bottom)} verts, top inner ring: {len(top)} verts")
    if len(bottom) != len(top) or len(bottom) < 3:
        raise RuntimeError("inner cap rings don't match -- can't bridge safely")

    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.verts.ensure_lookup_table()
    n = len(bottom)
    made = 0
    for i in range(n):
        b0 = bm.verts[bottom[i][1]]
        b1 = bm.verts[bottom[(i + 1) % n][1]]
        t0 = bm.verts[top[i][1]]
        t1 = bm.verts[top[(i + 1) % n][1]]
        try:
            bm.faces.new((b0, b1, t1, t0))
            made += 1
        except ValueError:
            pass  # face already exists
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    log(f"bridged inner wall: {made} new faces")


def propagate_molding():
    molding = [o for o in bpy.data.objects if o.name.startswith("LEAF-AND-TONGUE")]
    log(f"found {len(molding)} molding objects to propagate")
    made = 0
    for k in range(1, 10):
        angle = math.radians(k * MODULE_ARC_DEG)
        cos_a, sin_a = math.cos(angle), math.sin(angle)
        for src in molding:
            dup = src.copy()
            dup.data = src.data.copy()
            dup.name = f"{src.name} repeat {k:02d}"
            bpy.context.scene.collection.objects.link(dup)
            dup.parent = None
            mat = dup.matrix_world.copy()
            for v in dup.data.vertices:
                w = mat @ v.co
                x, y = w.x, w.y - CY
                nx = x * cos_a - y * sin_a
                ny = x * sin_a + y * cos_a
                v.co = Vector((nx, CY + ny, w.z))
            dup.matrix_world.identity()
            dup.data.update()
            made += 1
    log(f"propagated molding: {made} new objects (9 rotated copies each)")


def pull_ring_inward():
    prefixes = ("LION_", "SCROLL_L", "SCROLL_R", "ANTHEMION_")
    moved = 0
    for ob in bpy.data.objects:
        if not ob.name.startswith(prefixes):
            continue
        loc = ob.location
        theta = math.atan2(loc.y - CY, loc.x)
        ob.location = loc - RING_PULL_IN * Vector((math.cos(theta), math.sin(theta), 0.0))
        moved += 1
    log(f"pulled {moved} frieze objects inward by {RING_PULL_IN:.4f}")


def main():
    os.makedirs(OUT_RENDER, exist_ok=True)

    bpy.ops.wm.open_mainfile(filepath=SRC_BLEND)
    bpy.ops.wm.save_as_mainfile(filepath=OUT_BLEND)

    bridge_drum_inner_wall()
    propagate_molding()
    pull_ring_inward()

    bpy.ops.wm.save_as_mainfile(filepath=OUT_BLEND)
    log("SAVED", OUT_BLEND)


if __name__ == "__main__":
    main()
