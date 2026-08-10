"""Mop up v8's last defects: 1 boundary edge, 87 non-manifold edges.

diagnose_capital_v8_remainder.py found these are all microscopic degenerate
slivers -- non-manifold edges border faces with areas of 1e-7 to 2e-6
(essentially zero), scattered across 82 spatially-isolated clusters of 1-3
edges each. These are crumbs left behind by the repeated weld+dissolve
passes: dissolve_degenerate's default 1e-6 distance was too tight to catch
them (the edges themselves are ~0.0005 long).

Same proven pattern as repair_capital_leafgaps3.py: scoped self-collapse per
cluster (weld each cluster's own vertices together, distance sized to that
cluster's own span), never a mesh-wide weld.

Run:  blender --background --python scripts/repair_capital_final_cleanup.py
"""

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bmesh                                                      # noqa: E402
import bpy                                                        # noqa: E402
from mathutils import Vector                                      # noqa: E402

from paths import CAPITAL_MASTER_OBJECT, MASTERS, RENDERS         # noqa: E402

IN_PATH = os.path.join(MASTERS, "corinthian-capital-master-v8.blend")
OUT_PATH = os.path.join(MASTERS, "corinthian-capital-master-v9.blend")
OUT_RENDER = os.path.join(RENDERS, "capital-final-cleanup")


def log(*a):
    print("[cap-final]", *a)
    sys.stdout.flush()


def full_stats(bm):
    boundary = sum(1 for e in bm.edges if len(e.link_faces) == 1)
    nonmanifold = sum(1 for e in bm.edges if len(e.link_faces) > 2)
    return len(bm.faces), boundary, nonmanifold


def cluster_span(verts):
    pts = [v.co for v in verts]
    lo, hi = pts[0].copy(), pts[0].copy()
    for p in pts[1:]:
        for i in range(3):
            lo[i] = min(lo[i], p[i])
            hi[i] = max(hi[i], p[i])
    return (hi - lo).length


def main():
    bpy.ops.wm.open_mainfile(filepath=IN_PATH)
    ob = bpy.data.objects[CAPITAL_MASTER_OBJECT]

    bm = bmesh.new()
    bm.from_mesh(ob.data)
    tag = bm.verts.layers.int.new("cluster_tag")  # before any refs are taken
    f0, b0, nm0 = full_stats(bm)
    log(f"before: faces {f0}  boundary {b0}  non-manifold {nm0}")

    # --- find the 1 boundary edge and the non-manifold clusters, and tag
    # every involved vertex with a unique cluster id, BEFORE any weld runs.
    # Welding invalidates previously-held BMVert Python references for
    # unrelated elements too (same class of bug hit repeatedly this session),
    # so every weld below re-scans bm.verts fresh by tag value instead of
    # reusing a captured list.
    next_id = 1
    dist_by_id = {}

    boundary = [e for e in bm.edges if len(e.link_faces) == 1]
    for e in boundary:
        length = e.calc_length()
        for v in e.verts:
            v[tag] = next_id
        dist_by_id[next_id] = length * 1.5 + 1e-7
        log(f"boundary edge len {length:.6f} -> cluster {next_id}")
        next_id += 1

    # Scoped tightly to just the non-manifold edges' own endpoint vertices --
    # NOT the full vertex set of every attached face. The first attempt
    # pulled in whole faces, and one of those tiny sliver faces sharing a
    # vertex with normal-sized real geometry elsewhere let the cluster span
    # (and therefore the weld distance) balloon, fusing unrelated mesh and
    # punching new holes (boundary 1 -> 44). An edge with too many face users
    # is fixed by collapsing that edge's own 2 verts -- nothing more.
    nonmanifold = [e for e in bm.edges if len(e.link_faces) > 2]
    by_vert = {}
    for e in nonmanifold:
        for v in e.verts:
            by_vert.setdefault(v, []).append(e)
    seen = set()
    n_clusters = 0
    for e0 in nonmanifold:
        if id(e0) in seen:
            continue
        cverts = set()
        stack = [e0]
        seen.add(id(e0))
        while stack:
            e = stack.pop()
            for v in e.verts:
                cverts.add(v)
                for e2 in by_vert.get(v, []):
                    if id(e2) not in seen:
                        seen.add(id(e2))
                        stack.append(e2)
        span = cluster_span(cverts)
        for v in cverts:
            v[tag] = next_id
        dist_by_id[next_id] = span * 1.5 + 1e-7
        next_id += 1
        n_clusters += 1
    log(f"{n_clusters} non-manifold clusters to self-collapse")

    welded = 0
    for cid, dist in dist_by_id.items():
        sel = [v for v in bm.verts if v[tag] == cid]
        if len(sel) < 2:
            continue
        bmesh.ops.remove_doubles(bm, verts=sel, dist=dist)
        welded += 1

    bmesh.ops.dissolve_degenerate(bm, dist=1e-5, edges=bm.edges[:])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])

    f1, b1, nm1 = full_stats(bm)
    log(f"self-collapsed {welded} clusters (boundary edge + non-manifold spots)")
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

    shot("v9_face.png", 0, 8, 0.55, ctr)
    shot("v9_corner.png", 45, 14, 0.55, ctr)


if __name__ == "__main__":
    main()
