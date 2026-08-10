"""Three more follow-up fixes on top of the v2 working file:

1. The drum wall thickening (and its bridge to a continuous inner wall) only
   covered the drum itself (z 0.198-0.313). Directly above it sits a
   separate object, "Rebuilt upper cornice backing with chamfered top"
   (z 0.313-0.395, the structure's actual top), which is still built at the
   original thin wall profile (inner r~0.26-0.262, outer r~0.286-0.29,
   ~0.03 thick) -- so the solid-wall look stops at the drum's top edge
   instead of carrying through to the top of the structure. Fix: push that
   object's inner-surface vertices (r<0.27) inward to match the drum's
   thickened inner radius (0.204), same technique as thicken_drum.py, so
   the wall reads as continuous, uniformly thick masonry all the way up.

2. The LEAF-AND-TONGUE shelf molding's carved relief (the alternating
   leaf/tongue shapes) is cut too deep -- reads as gouged rather than a
   shallow classical molding profile. Fix: for every LEAF-AND-TONGUE object
   (including the 9 propagated repeats), shrink each vertex's radial
   recession toward that object's own front (max-radius) plane by half,
   which halves the visual cut depth while leaving the front surface and
   the u/z footprint of every leaf shape untouched.

3. Even though the frieze ring's back plane was pulled flush with the
   drum's outer surface (zero measured gap) in the previous pass, a flush
   *touch* between a carved-relief object and a cylindrical wall still
   reads as a gap/seam at the object's edges (the relief isn't backed by a
   matching curved solid). Fix: push the frieze objects (lion/scroll/
   anthemion, all 10 repeats) an additional fixed amount further inward so
   they solidly overlap into the drum wall instead of merely touching it.

Never touches the v2 file: opens it, immediately saves to a new working
file, and edits there.

Run:  blender --background --python fix_top_shelf_and_embed_v3.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import math

import bpy
from mathutils import Vector

from paths import DRUM_INNER_R, chain_blend, chain_render  # noqa: E402

SRC_BLEND = chain_blend("frieze-ring-v2")
OUT_BLEND = chain_blend("frieze-ring-v3")
OUT_RENDER = chain_render("cornice-frieze-ring-v3")

CY = -0.5456366539001465

BACKING_INNER_THRESHOLD = 0.27  # backing's inner-surface verts are r~0.26-0.262; outer starts at 0.28

MOLDING_DEPTH_FACTOR = 0.5     # halve the radial cut depth of the leaf-and-tongue relief

EXTRA_EMBED = 0.004            # additional inward push for the frieze ring, beyond "flush"


def log(*a):
    print("[fix-v3]", *a)
    sys.stdout.flush()


def thicken_upper_backing():
    ob = bpy.data.objects["Rebuilt upper cornice backing with chamfered top"]
    inv = ob.matrix_world.inverted()
    moved = 0
    for v in ob.data.vertices:
        w = ob.matrix_world @ v.co
        r = math.hypot(w.x, w.y - CY)
        if r < BACKING_INNER_THRESHOLD:
            theta = math.atan2(w.y - CY, w.x)
            new_w = Vector((DRUM_INNER_R * math.cos(theta), CY + DRUM_INNER_R * math.sin(theta), w.z))
            v.co = inv @ new_w
            moved += 1
    ob.data.update()
    log(f"thickened upper cornice backing: moved {moved} inner-surface vertices to r={DRUM_INNER_R}")


def shallow_molding_cuts():
    molds = [o for o in bpy.data.objects if o.name.startswith("LEAF-AND-TONGUE")]
    log(f"found {len(molds)} molding objects (base + propagated repeats)")
    for ob in molds:
        mat = ob.matrix_world
        inv = mat.inverted()
        rs = []
        for v in ob.data.vertices:
            w = mat @ v.co
            rs.append(math.hypot(w.x, w.y - CY))
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
    log(f"shallowed cut depth on {len(molds)} molding objects by factor {MOLDING_DEPTH_FACTOR}")


def embed_ring_deeper():
    prefixes = ("LION_", "SCROLL_L", "SCROLL_R", "ANTHEMION_")
    moved = 0
    for ob in bpy.data.objects:
        if not ob.name.startswith(prefixes):
            continue
        loc = ob.location
        theta = math.atan2(loc.y - CY, loc.x)
        ob.location = loc - EXTRA_EMBED * Vector((math.cos(theta), math.sin(theta), 0.0))
        moved += 1
    log(f"embedded {moved} frieze objects an additional {EXTRA_EMBED} inward")


def main():
    os.makedirs(OUT_RENDER, exist_ok=True)

    bpy.ops.wm.open_mainfile(filepath=SRC_BLEND)
    bpy.ops.wm.save_as_mainfile(filepath=OUT_BLEND)

    thicken_upper_backing()
    shallow_molding_cuts()
    embed_ring_deeper()

    bpy.ops.wm.save_as_mainfile(filepath=OUT_BLEND)
    log("SAVED", OUT_BLEND)


if __name__ == "__main__":
    main()
