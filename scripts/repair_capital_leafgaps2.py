"""Finish closing the small leaf gaps: fill one loop at a time, fully fresh.

repair_capital_leafgaps.py's fill pass computed the boundary-loop list ONCE,
then called bmesh.ops.triangle_fill in a loop over it -- and only the first
call actually created a face (1 of ~74 eligible closed loops). Root cause is
the same class of bug already hit twice this session: an operation that adds
geometry can invalidate previously-held BMVert/BMEdge Python references for
UNRELATED elements, so by the second iteration the "edges" list handed to
triangle_fill was silently stale and the call quietly did nothing.

The fix that actually holds: never reuse geometry references across a
mutation. Recompute the boundary-loop list from scratch before every single
fill, fill only the one loop found, repeat. More calls, but each one is
provably working on live data, and with ~74 tiny loops left this is still
just a few seconds of work.

Run:  blender --background --python scripts/repair_capital_leafgaps2.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import math                                                       # noqa: E402

import bmesh                                                      # noqa: E402
import bpy                                                        # noqa: E402
from mathutils import Vector                                      # noqa: E402

from paths import CAPITAL_MASTER_OBJECT, MASTERS, RENDERS         # noqa: E402

IN_PATH = os.path.join(MASTERS, "corinthian-capital-master-v5.blend")
OUT_PATH = os.path.join(MASTERS, "corinthian-capital-master-v6.blend")
OUT_RENDER = os.path.join(RENDERS, "capital-leafgap2-repair")


def log(*a):
    print("[cap-leafgap2]", *a)
    sys.stdout.flush()


def full_stats(bm):
    boundary = sum(1 for e in bm.edges if len(e.link_faces) == 1)
    nonmanifold = sum(1 for e in bm.edges if len(e.link_faces) > 2)
    return boundary, nonmanifold


def first_closed_loop(bm):
    """One boundary loop (edges, is_closed_simple), or None if there are none left."""
    boundary_edges = [e for e in bm.edges if len(e.link_faces) == 1]
    if not boundary_edges:
        return None
    by_vert = {}
    for e in boundary_edges:
        for v in e.verts:
            by_vert.setdefault(v, []).append(e)
    seen_edges = set()
    for e0 in boundary_edges:
        if e0.index in seen_edges:
            continue
        comp_edges, comp_verts = [], set()
        stack = [e0]
        seen_edges.add(e0.index)
        while stack:
            e = stack.pop()
            comp_edges.append(e)
            for v in e.verts:
                comp_verts.add(v)
                for e2 in by_vert.get(v, []):
                    if e2.index not in seen_edges:
                        seen_edges.add(e2.index)
                        stack.append(e2)
        touch = {}
        for e in comp_edges:
            for v in e.verts:
                touch[v] = touch.get(v, 0) + 1
        closed = (len(comp_edges) >= 3 and len(comp_edges) == len(comp_verts)
                 and all(c == 2 for c in touch.values()))
        if closed:
            return comp_edges
    return None


def main():
    bpy.ops.wm.open_mainfile(filepath=IN_PATH)
    ob = bpy.data.objects[CAPITAL_MASTER_OBJECT]

    bm = bmesh.new()
    bm.from_mesh(ob.data)
    b0, nm0 = full_stats(bm)
    faces0 = len(bm.faces)
    log(f"before: faces {faces0}  boundary {b0}  non-manifold {nm0}")

    filled = 0
    attempts = 0
    while True:
        edges = first_closed_loop(bm)
        if edges is None:
            break
        attempts += 1
        before_faces = len(bm.faces)
        bmesh.ops.triangle_fill(bm, use_beauty=True, use_dissolve=False, edges=edges)
        bm.verts.index_update()
        bm.edges.index_update()
        bm.faces.index_update()
        if len(bm.faces) > before_faces:
            filled += 1
        elif attempts > 400:
            log("bailing: too many non-progressing attempts, something is stuck")
            break

    log(f"filled {filled} closed loops (attempted {attempts})")

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    b1, nm1 = full_stats(bm)
    faces1 = len(bm.faces)

    # How many boundary loops remain, and their sizes -- honest accounting of
    # what is still open after this pass, not a claim of total closure.
    remaining_diag = []
    boundary_edges = [e for e in bm.edges if len(e.link_faces) == 1]
    by_vert = {}
    for e in boundary_edges:
        for v in e.verts:
            by_vert.setdefault(v, []).append(e)
    seen = set()
    n_loops = 0
    for e0 in boundary_edges:
        if e0.index in seen:
            continue
        ce, cv = [], set()
        stack = [e0]
        seen.add(e0.index)
        while stack:
            e = stack.pop()
            ce.append(e)
            for v in e.verts:
                cv.add(v)
                for e2 in by_vert.get(v, []):
                    if e2.index not in seen:
                        seen.add(e2.index)
                        stack.append(e2)
        n_loops += 1
        pts = [v.co for v in cv]
        lo2 = pts[0].copy()
        hi2 = pts[0].copy()
        for p in pts[1:]:
            for i in range(3):
                lo2[i] = min(lo2[i], p[i])
                hi2[i] = max(hi2[i], p[i])
        remaining_diag.append((hi2 - lo2).length)
    remaining_diag.sort(reverse=True)
    log(f"{n_loops} boundary loops remain, {len(boundary_edges)} edges total")
    log(f"largest remaining loop diagonals: {[round(x, 5) for x in remaining_diag[:10]]}")

    bm.to_mesh(ob.data)
    bm.free()
    ob.data.update()

    log("")
    log(f"{'':10s} {'faces':>8s} {'boundary':>9s} {'nonmanifold':>12s}")
    log(f"{'before':10s} {faces0:8d} {b0:9d} {nm0:12d}")
    log(f"{'after':10s} {faces1:8d} {b1:9d} {nm1:12d}")

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

    shot("v6_face.png", 0, 8, 0.55, ctr)
    shot("v6_corner.png", 45, 14, 0.55, ctr)
    crown_focus = Vector((ctr.x, ctr.y, lo.z + (hi.z - lo.z) * 0.5))
    shot("v6_crown_zoom.png", 20, 12, 0.28, crown_focus)


if __name__ == "__main__":
    main()
