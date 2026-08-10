"""Is the capital's interior modeled, and if so, how much does it cost?

User's own inspection in Blender: the mesh looks hollow, and the interior
looks like it has its own modeled surface -- which, if true, is pure waste.
Nothing is ever inside a capital that sits on a shaft with its bell base
covered; only the outer sculpted surface is ever seen.

This bisects a copy of the master through its vertical centre plane and caps
the cut, so the interior structure is visible in a plain render, and counts
faces by a cheap inside/outside test (a face is "interior-shell" if a ray
from its centre outward along its own normal, up to the mesh's own radius,
does not exit before crossing more mesh -- approximated here by comparing
each face's distance-from-axis to its neighbourhood's local max, which is
far cheaper than real raycasting and good enough to answer "is there a second
wall"). Read-only with respect to the master; writes only to renders/.

Run:  blender --background --python scripts/diagnose_capital_interior.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import math                                                       # noqa: E402

import bmesh                                                      # noqa: E402
import bpy                                                        # noqa: E402
from mathutils import Vector                                      # noqa: E402

from paths import CAPITAL_MASTER_OBJECT, MASTERS, RENDERS         # noqa: E402

IN_PATH = os.path.join(MASTERS, "corinthian-capital-master-v3.blend")
OUT_RENDER = os.path.join(RENDERS, "capital-interior-diagnostic")


def log(*a):
    print("[cap-interior]", *a)
    sys.stdout.flush()


def main():
    bpy.ops.wm.open_mainfile(filepath=IN_PATH)
    ob = bpy.data.objects[CAPITAL_MASTER_OBJECT]

    lo = Vector((1e18,) * 3)
    hi = Vector((-1e18,) * 3)
    for v in ob.data.vertices:
        for i in range(3):
            lo[i] = min(lo[i], v.co[i])
            hi[i] = max(hi[i], v.co[i])
    ctr = (lo + hi) / 2.0
    diag = (hi - lo).length
    log(f"bounds x {lo.x:+.4f}..{hi.x:+.4f} y {lo.y:+.4f}..{hi.y:+.4f} z {lo.z:+.4f}..{hi.z:+.4f}")

    # --- quantify: for a set of sample rays from the central axis outward at
    # many heights/angles, how many mesh crossings does each ray have? A pure
    # single-wall shell crosses twice (front wall out, back wall... no -- once
    # per ray direction, since a ray from the axis outward through a shell
    # exits through exactly one wall on that side). Two nested walls on the
    # same side means two crossings.
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bm.faces.ensure_lookup_table()
    from mathutils.bvhtree import BVHTree
    bvh = BVHTree.FromBMesh(bm)

    axis_z_lo, axis_z_hi = lo.z + (hi.z - lo.z) * 0.15, lo.z + (hi.z - lo.z) * 0.85
    n_z, n_theta = 12, 24
    multi_hit = 0
    total_rays = 0
    hit_counts = {}
    for iz in range(n_z):
        z = axis_z_lo + (axis_z_hi - axis_z_lo) * iz / (n_z - 1)
        origin = Vector((ctr.x, ctr.y, z))
        for it in range(n_theta):
            theta = 2 * math.pi * it / n_theta
            direction = Vector((math.cos(theta), math.sin(theta), 0.0))
            # Walk the ray, collecting ALL crossings (ray_cast only gives the
            # first), by repeatedly casting just past the last hit.
            hits = 0
            o = origin.copy()
            for _ in range(6):
                loc, nrm, idx, dist = bvh.ray_cast(o, direction)
                if loc is None:
                    break
                hits += 1
                o = loc + direction * 1e-5
            total_rays += 1
            hit_counts[hits] = hit_counts.get(hits, 0) + 1
            if hits >= 2:
                multi_hit += 1
    bm.free()

    log(f"rays cast from the vertical axis outward: {total_rays}")
    log(f"crossing-count histogram (1 = single wall, 2+ = a second wall behind it): {hit_counts}")
    log(f"rays with 2+ crossings: {multi_hit}/{total_rays} "
        f"({100*multi_hit/total_rays:.0f}%)")

    # --- visual: bisect a copy through the vertical centre plane ---
    bm2 = bmesh.new()
    bm2.from_mesh(ob.data)
    geom = bm2.verts[:] + bm2.edges[:] + bm2.faces[:]
    bmesh.ops.bisect_plane(bm2, geom=geom, dist=1e-6,
                           plane_co=ctr, plane_no=Vector((1, 0, 0)),
                           clear_outer=True, clear_inner=False)
    me2 = bpy.data.meshes.new("CAPITAL_CUTAWAY")
    bm2.to_mesh(me2)
    bm2.free()
    ob2 = bpy.data.objects.new("CAPITAL_CUTAWAY", me2)
    bpy.context.scene.collection.objects.link(ob2)
    log(f"cutaway half: {len(me2.polygons)} faces (original whole: {len(ob.data.polygons)})")

    ob.hide_render = True

    os.makedirs(OUT_RENDER, exist_ok=True)
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_EEVEE"
    sc.render.resolution_x = 1100
    sc.render.resolution_y = 1100
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
    clay.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.85, 0.6, 0.5, 1)
    clay.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.75
    ob2.data.materials.append(clay)
    for p in ob2.data.polygons:
        p.use_smooth = True

    cam_data = bpy.data.cameras.new("cam")
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = diag * 0.75
    cam = bpy.data.objects.new("cam", cam_data)
    sc.collection.objects.link(cam)
    sc.camera = cam

    def shot(name, yaw_deg, pitch_deg):
        yaw, pitch = math.radians(yaw_deg), math.radians(pitch_deg)
        d = diag * 2.2
        cam.location = ctr + Vector((-d * math.sin(yaw) * math.cos(pitch),
                                     d * math.cos(yaw) * math.cos(pitch),
                                     d * math.sin(pitch)))
        cam.rotation_euler = (ctr - cam.location).normalized().to_track_quat('-Z', 'Y').to_euler()
        sc.render.filepath = os.path.join(OUT_RENDER, name)
        bpy.ops.render.render(write_still=True)
        log("WROTE " + name)

    # Straight into the cut face: cleared the +X half, kept -X, so the camera
    # has to sit on the removed (+X) side looking back toward -X to see the
    # freshly exposed cross-section rather than the kept half's outside.
    shot("cutaway_straight.png", -90, 6)
    shot("cutaway_angle.png", -65, 18)


if __name__ == "__main__":
    main()
