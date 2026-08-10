"""Replace the inscribed drum with a plain, unlettered one, upstream of the
frieze chain -- requested so the drum stops carrying the real Pulgas Water
Temple's engraved quotation.

The original "Inscription drum with 150-percent inset quotation" mesh
(measured, see thicken_drum.py / fix_drum_wall_and_ring_seating.py) is three
pieces:
  - an outer wall tube at r=0.286, z 0.198->0.313 -- carries the text via a
    zone of dense sub-tessellation (177 z-rings) between two plain end rings
    (1152 verts each) elsewhere on the tube
  - a top rim annulus and a bottom rim annulus, each bridging r=0.282 (inner)
    to r=0.286 (outer) at their respective z, giving the drum's edges visible
    thickness
No inner wall exists between the two rim rings in this base file -- that gap
is intentional; fix_drum_wall_and_ring_seating.py bridges it later, downstream
in the frieze chain.

First attempt was to keep the existing mesh and edit it in place: push the
inset-text vertices (r~=0.2835) back out to the wall radius (r=0.286, pure
position edit, no topology change) and run a limited dissolve to collapse the
now-coplanar faces. Rejected -- confirmed via render, twice, even after
clearing the mesh's baked custom split normals (which was the first suspect):
the old letter edges still ghost through as faceting/shading artifacts. Same
failure family as the leafscroll's rejected flat-plane cut
(simplify_leafscroll_depth.py) and the capital's Solidify spikes -- editing
around complex existing topology fights back. Not reused here.

This instead throws away the whole drum mesh and rebuilds it from primitives
at the exact measured dimensions (same lesson as the well's braid/cap course
and the ROADMAP's capital-rebuild plan): a plain outer tube plus two rim
annuli, 360 segments (0.286 radius -- ~0.005 units of arc per segment, far
finer than needed for a smooth read at any real viewing distance). Clean by
construction: 0 boundary edges except the two inner-rim circles (360 verts
each, at r=0.282), which is exactly the shape thicken_drum.py and
fix_drum_wall_and_ring_seating.py already expect to find there (they select
by radius/z, not by name-of-origin, so a from-scratch rebuild at the same
radii is transparent to them). 0 non-manifold, 0 loose, 0 duplicate.

Renamed the object from "Inscription drum with 150-percent inset quotation"
to "Plain drum wall" since the old name is no longer true -- thicken_drum.py
and fix_drum_wall_and_ring_seating.py's lookups were updated to match.

Never touches CORNICE_WELL_DETAILED: opens it, immediately saves to a new
file, and edits there. Reads that constant directly rather than CHAIN_BASE,
which paths.py now points at this script's own output -- reading CHAIN_BASE
here would make the script read its own prior output on every run after the
first.

Run:  blender --background --python scripts/build_plain_drum.py
"""

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bmesh                                                      # noqa: E402
import bpy                                                        # noqa: E402

from paths import CORNICE_WELL_DETAILED, RENDERS, TEMPLE_MODEL  # noqa: E402

OLD_NAME = "Inscription drum with 150-percent inset quotation"
NEW_NAME = "Plain drum wall"

OUT_BLEND = os.path.join(
    TEMPLE_MODEL,
    "Pulgas-Water-Temple-live-cornice-with-lion-newcapitals-narrow90-well-plaindrum.blend")
OUT_RENDER = os.path.join(RENDERS, "plain-drum-check")

CY = -0.5456366539001465
INNER_R = 0.282
OUTER_R = 0.286
Z_BOT = 0.198
Z_TOP = 0.313
SEGMENTS = 360


def log(*a):
    print("[plain-drum]", *a)
    sys.stdout.flush()


def ring(bm, r, z, n):
    verts = []
    for i in range(n):
        theta = 2.0 * math.pi * i / n
        x = r * math.cos(theta)
        y = CY + r * math.sin(theta)
        verts.append(bm.verts.new((x, y, z)))
    return verts


def bridge_ring(bm, ring_a, ring_b):
    n = len(ring_a)
    for i in range(n):
        a0, a1 = ring_a[i], ring_a[(i + 1) % n]
        b0, b1 = ring_b[i], ring_b[(i + 1) % n]
        bm.faces.new((a0, a1, b1, b0))


def build_plain_drum_mesh():
    bm = bmesh.new()

    outer_bot = ring(bm, OUTER_R, Z_BOT, SEGMENTS)
    outer_top = ring(bm, OUTER_R, Z_TOP, SEGMENTS)
    inner_bot = ring(bm, INNER_R, Z_BOT, SEGMENTS)
    inner_top = ring(bm, INNER_R, Z_TOP, SEGMENTS)

    bridge_ring(bm, outer_bot, outer_top)   # the plain wall tube
    bridge_ring(bm, inner_top, outer_top)   # top rim annulus
    bridge_ring(bm, outer_bot, inner_bot)   # bottom rim annulus

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])

    me = bpy.data.meshes.new(NEW_NAME + " mesh")
    bm.to_mesh(me)
    bm.free()
    return me


def main():
    os.makedirs(OUT_RENDER, exist_ok=True)

    bpy.ops.wm.open_mainfile(filepath=CORNICE_WELL_DETAILED)
    bpy.ops.wm.save_as_mainfile(filepath=OUT_BLEND)

    drum = bpy.data.objects[OLD_NAME]
    faces_before = len(drum.data.polygons)

    new_mesh = build_plain_drum_mesh()
    drum.data = new_mesh
    drum.name = NEW_NAME
    drum.data.name = NEW_NAME + " mesh"

    bm = bmesh.new()
    bm.from_mesh(drum.data)
    boundary = sum(1 for e in bm.edges if len(e.link_faces) == 1)
    nonmanifold = sum(1 for e in bm.edges if len(e.link_faces) > 2)
    loose = sum(1 for v in bm.verts if len(v.link_faces) == 0)
    bm.free()

    log(f"faces {faces_before} -> {len(drum.data.polygons)}  "
        f"boundary {boundary}  non-manifold {nonmanifold}  loose {loose}")

    bpy.ops.wm.save_as_mainfile(filepath=OUT_BLEND)
    log(f"SAVED {OUT_BLEND}")

    # --- render check ---
    from mathutils import Vector

    for other in list(bpy.data.objects):
        if other is not drum:
            bpy.data.objects.remove(other, do_unlink=True)

    lo = Vector((1e18,) * 3)
    hi = Vector((-1e18,) * 3)
    for v in drum.data.vertices:
        for i in range(3):
            lo[i] = min(lo[i], v.co[i])
            hi[i] = max(hi[i], v.co[i])
    ctr = (lo + hi) / 2.0
    diag = (hi - lo).length

    sc = bpy.context.scene
    sc.render.engine = "BLENDER_EEVEE"
    sc.render.resolution_x = 1400
    sc.render.resolution_y = 700
    sc.render.image_settings.file_format = "PNG"
    w = bpy.data.worlds.new("W")
    sc.world = w
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs["Color"].default_value = (0.30, 0.31, 0.34, 1)
    w.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.5
    for e, p, y in ((2.6, 42.0, -35.0), (1.6, 42.0, 35.0), (0.8, 10.0, 180.0)):
        li = bpy.data.lights.new("s", "SUN")
        li.energy = e
        o = bpy.data.objects.new("s", li)
        sc.collection.objects.link(o)
        o.rotation_euler = (math.radians(p), 0.0, math.radians(y))
    clay = bpy.data.materials.new("CLAY")
    clay.use_nodes = True
    clay.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.85, 0.83, 0.78, 1)
    clay.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.80
    drum.data.materials.clear()
    drum.data.materials.append(clay)
    drum.hide_render = False
    for p in drum.data.polygons:
        p.use_smooth = True
    cam_data = bpy.data.cameras.new("cam")
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = diag * 0.55
    cam = bpy.data.objects.new("cam", cam_data)
    sc.collection.objects.link(cam)
    sc.camera = cam
    pitch = math.radians(5)
    d = diag * 2.2
    cam.location = ctr + Vector((0, -d, d * math.sin(pitch)))
    cam.rotation_euler = (ctr - cam.location).normalized().to_track_quat('-Z', 'Y').to_euler()
    sc.render.filepath = os.path.join(OUT_RENDER, "plain_drum_front.png")
    bpy.ops.render.render(write_still=True)
    log("WROTE plain_drum_front.png")


if __name__ == "__main__":
    main()
