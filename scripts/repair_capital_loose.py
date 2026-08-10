"""Delete loose geometry left behind by the weld/dissolve passes on v9.

audit found 74 loose verts, 7 loose edges -- none of today's capital-specific
repair scripts (repair_capital_seam/close/leafgaps*/final_cleanup) had the
final "delete loose" sweep that the original repair_masters.py easy-pass did.
Flagged by the user: an eventual STL export can't have loose ends.

Run:  blender --background --python scripts/repair_capital_loose.py
"""

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bmesh                                                      # noqa: E402
import bpy                                                        # noqa: E402
from mathutils import Vector                                      # noqa: E402

from paths import CAPITAL_MASTER_OBJECT, MASTERS, RENDERS         # noqa: E402

IN_PATH = os.path.join(MASTERS, "corinthian-capital-master-v9.blend")
OUT_PATH = os.path.join(MASTERS, "corinthian-capital-master-v10.blend")
OUT_RENDER = os.path.join(RENDERS, "capital-loose-cleanup")


def log(*a):
    print("[cap-loose]", *a)
    sys.stdout.flush()


def full_stats(bm):
    loose_v = sum(1 for v in bm.verts if len(v.link_faces) == 0)
    loose_e = sum(1 for e in bm.edges if len(e.link_faces) == 0)
    boundary = sum(1 for e in bm.edges if len(e.link_faces) == 1)
    nonmanifold = sum(1 for e in bm.edges if len(e.link_faces) > 2)
    return len(bm.faces), loose_v, loose_e, boundary, nonmanifold


def main():
    bpy.ops.wm.open_mainfile(filepath=IN_PATH)
    ob = bpy.data.objects[CAPITAL_MASTER_OBJECT]

    bm = bmesh.new()
    bm.from_mesh(ob.data)
    f0, lv0, le0, b0, nm0 = full_stats(bm)
    log(f"before: faces {f0}  loose_v {lv0}  loose_e {le0}  boundary {b0}  non-manifold {nm0}")

    loose_edges = [e for e in bm.edges if len(e.link_faces) == 0]
    bmesh.ops.delete(bm, geom=loose_edges, context="EDGES")
    loose_verts = [v for v in bm.verts if len(v.link_faces) == 0]
    bmesh.ops.delete(bm, geom=loose_verts, context="VERTS")

    f1, lv1, le1, b1, nm1 = full_stats(bm)
    log(f"after: faces {f1}  loose_v {lv1}  loose_e {le1}  boundary {b1}  non-manifold {nm1}")

    bm.to_mesh(ob.data)
    bm.free()
    ob.data.update()

    for other in list(bpy.data.objects):
        if other is not ob:
            bpy.data.objects.remove(other, do_unlink=True)
    ob.name = CAPITAL_MASTER_OBJECT
    ob.data.name = CAPITAL_MASTER_OBJECT
    os.makedirs(MASTERS, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=OUT_PATH)
    log(f"SAVED {OUT_PATH}")

    # --- render for visual confirmation ---
    lo = Vector((1e18,) * 3)
    hi = Vector((-1e18,) * 3)
    for v in ob.data.vertices:
        for i in range(3):
            lo[i] = min(lo[i], v.co[i])
            hi[i] = max(hi[i], v.co[i])
    ctr = (lo + hi) / 2.0
    diag = (hi - lo).length

    os.makedirs(OUT_RENDER, exist_ok=True)
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_EEVEE"
    sc.render.resolution_x = 1300
    sc.render.resolution_y = 1300
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
    ob.data.materials.clear()
    ob.data.materials.append(clay)
    for p in ob.data.polygons:
        p.use_smooth = True

    cam_data = bpy.data.cameras.new("cam")
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = diag * 0.55
    cam = bpy.data.objects.new("cam", cam_data)
    sc.collection.objects.link(cam)
    sc.camera = cam
    yaw, pitch = math.radians(0), math.radians(8)
    d = diag * 2.2
    cam.location = ctr + Vector((-d * math.sin(yaw) * math.cos(pitch),
                                 d * math.cos(yaw) * math.cos(pitch),
                                 d * math.sin(pitch)))
    cam.rotation_euler = (ctr - cam.location).normalized().to_track_quat('-Z', 'Y').to_euler()
    sc.render.filepath = os.path.join(OUT_RENDER, "v10_face.png")
    bpy.ops.render.render(write_still=True)
    log("WROTE v10_face.png")


if __name__ == "__main__":
    main()
