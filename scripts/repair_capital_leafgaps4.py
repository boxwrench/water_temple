"""Close the last 4 open/branch loops (9 edges) that v7's self-collapse pass
skipped -- those aren't closed simple cycles, so per-loop vertex collapse
doesn't apply. Same pooled open-fragment weld that already worked once this
session (repair_capital_leafgaps.py: 293->227 boundary): pool the loops'
vertices, measure the real nearest-neighbor gap via KDTree, weld scoped to
just that vertex set.

Run:  blender --background --python scripts/repair_capital_leafgaps4.py
"""

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bmesh                                                      # noqa: E402
import bpy                                                        # noqa: E402
from mathutils import Vector                                      # noqa: E402

from paths import CAPITAL_MASTER_OBJECT, MASTERS, RENDERS         # noqa: E402

IN_PATH = os.path.join(MASTERS, "corinthian-capital-master-v7.blend")
OUT_PATH = os.path.join(MASTERS, "corinthian-capital-master-v8.blend")
OUT_RENDER = os.path.join(RENDERS, "capital-leafgap4-repair")


def log(*a):
    print("[cap-leafgap4]", *a)
    sys.stdout.flush()


def full_stats(bm):
    boundary = sum(1 for e in bm.edges if len(e.link_faces) == 1)
    nonmanifold = sum(1 for e in bm.edges if len(e.link_faces) > 2)
    return len(bm.faces), boundary, nonmanifold


def boundary_components(bm):
    boundary_edges = [e for e in bm.edges if len(e.link_faces) == 1]
    by_vert = {}
    for e in boundary_edges:
        for v in e.verts:
            by_vert.setdefault(v, []).append(e)
    seen = set()
    comps = []
    for e0 in boundary_edges:
        if id(e0) in seen:
            continue
        comp_edges, comp_verts = [], set()
        stack = [e0]
        seen.add(id(e0))
        while stack:
            e = stack.pop()
            comp_edges.append(e)
            for v in e.verts:
                comp_verts.add(v)
                for e2 in by_vert.get(v, []):
                    if id(e2) not in seen:
                        seen.add(id(e2))
                        stack.append(e2)
        comps.append((comp_edges, comp_verts))
    return comps


def main():
    bpy.ops.wm.open_mainfile(filepath=IN_PATH)
    ob = bpy.data.objects[CAPITAL_MASTER_OBJECT]

    bm = bmesh.new()
    bm.from_mesh(ob.data)
    tag = bm.verts.layers.int.new("frag_tag")  # before any refs captured
    f0, b0, nm0 = full_stats(bm)
    log(f"before: faces {f0}  boundary {b0}  non-manifold {nm0}")

    comps = boundary_components(bm)
    log(f"{len(comps)} boundary loops remain")
    for e, v in comps:
        log(f"  loop: {len(e)} edges, {len(v)} verts")

    all_verts = set()
    for e, v in comps:
        all_verts |= v
    all_verts = list(all_verts)
    log(f"{len(all_verts)} verts total across all remaining loops")

    for v in all_verts:
        v[tag] = 1

    import mathutils
    kd = mathutils.kdtree.KDTree(len(all_verts))
    for i, v in enumerate(all_verts):
        kd.insert(v.co, i)
    kd.balance()
    gaps = []
    for v in all_verts:
        for co, idx, dist in kd.find_n(v.co, 2):
            if dist > 1e-9:
                gaps.append(dist)
                break
    gaps.sort()
    dist = gaps[-1] * 1.2 if gaps else 1e-5
    log(f"gap across {len(gaps)} verts: median {gaps[len(gaps)//2]:.6f}  "
        f"max {gaps[-1]:.6f}  welding at {dist:.6f}")

    sel = [v for v in bm.verts if v[tag] == 1]
    bmesh.ops.remove_doubles(bm, verts=sel, dist=dist)
    bmesh.ops.dissolve_degenerate(bm, dist=1e-6, edges=bm.edges[:])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])

    f1, b1, nm1 = full_stats(bm)
    log(f"after: faces {f1}  boundary {b1}  non-manifold {nm1}")

    bm.to_mesh(ob.data)
    bm.free()
    ob.data.update()

    log("")
    log(f"{'':10s} {'faces':>8s} {'boundary':>9s} {'nonmanifold':>12s}")
    log(f"{'before':10s} {f0:8d} {b0:9d} {nm0:12d}")
    log(f"{'after':10s} {f1:8d} {b1:9d} {nm1:12d}")

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
    cam = bpy.data.objects.new("cam", cam_data)
    sc.collection.objects.link(cam)
    sc.camera = cam

    def shot(name, yaw_deg, pitch_deg, zoom, focus):
        cam_data.ortho_scale = diag * zoom
        yaw, pitch = math.radians(yaw_deg), math.radians(pitch_deg)
        d = diag * 2.2
        cam.location = focus + Vector((-d * math.sin(yaw) * math.cos(pitch),
                                       d * math.cos(yaw) * math.cos(pitch),
                                       d * math.sin(pitch)))
        cam.rotation_euler = (focus - cam.location).normalized().to_track_quat('-Z', 'Y').to_euler()
        sc.render.filepath = os.path.join(OUT_RENDER, name)
        bpy.ops.render.render(write_still=True)
        log("WROTE " + name)

    shot("v8_face.png", 0, 8, 0.55, ctr)
    shot("v8_corner.png", 45, 14, 0.55, ctr)


if __name__ == "__main__":
    main()
