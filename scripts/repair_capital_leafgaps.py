"""Close the remaining small gaps between leaves that v4 left alone.

v4 (repair_capital_close.py) closed the one big seam hole but left ~108 small
boundary loops alone, on the strength of checking ONE of them (a genuinely
degenerate 3.3e-9-area sliver) and wrongly generalizing "these are all
sub-pixel." User looked at the actual model and correctly called that out --
there are still visible gaps. Checking the real size distribution (this
script's investigation, done interactively first) found loops up to 0.043 in
diagonal -- real, visible slits between overlapping leaf/scroll geometry, not
sub-pixel noise. The earlier dismissal was wrong.

Two separate problems, two fixes:

1. **73 loops are already closed simple cycles** (edges == verts, every
   vertex touches exactly two of the loop's own edges) with real if thin
   area -- long narrow slits, which is exactly what a crack between two
   overlapping carved surfaces looks like. `bmesh.ops.holes_fill` returns
   empty on every one of these when tested individually, even a non-
   degenerate one (measured: area 8.6e-06, still empty) -- it just does not
   handle this mesh's slightly non-planar organic loops. `triangle_fill`
   fills the same loop correctly. Both operators, tested with every loop's
   edges handed over in one flat list, silently filled only a handful and
   dropped the rest -- same failure mode already hit once in
   repair_capital_close.py. The fix there was calling per loop; it applies
   here too.
2. **36 loops are NOT closed** -- open chains or branches (edge count doesn't
   match vertex count, or some vertex touches != 2 of the loop's own edges).
   These are cracks whose two facing lips have not fully met yet -- no fill
   operator can cap something that is not a closed loop. Pool their vertices,
   measure the real gap the same way the big seam was closed
   (repair_capital_seam.py's method), and weld -- scoped to only these
   vertices, so nothing else in the mesh can move.

Run:  blender --background --python scripts/repair_capital_leafgaps.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import math                                                       # noqa: E402

import bmesh                                                      # noqa: E402
import bpy                                                        # noqa: E402
from mathutils import Vector                                      # noqa: E402

from paths import CAPITAL_MASTER_OBJECT, MASTERS, RENDERS         # noqa: E402

IN_PATH = os.path.join(MASTERS, "corinthian-capital-master-v4.blend")
OUT_PATH = os.path.join(MASTERS, "corinthian-capital-master-v5.blend")
OUT_RENDER = os.path.join(RENDERS, "capital-leafgap-repair")


def log(*a):
    print("[cap-leafgap]", *a)
    sys.stdout.flush()


def full_stats(bm):
    boundary = sum(1 for e in bm.edges if len(e.link_faces) == 1)
    nonmanifold = sum(1 for e in bm.edges if len(e.link_faces) > 2)
    return boundary, nonmanifold


def boundary_components(bm):
    boundary_edges = [e for e in bm.edges if len(e.link_faces) == 1]
    by_vert = {}
    for e in boundary_edges:
        for v in e.verts:
            by_vert.setdefault(v, []).append(e)
    seen_edges = set()
    comps = []
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
        comps.append((comp_edges, comp_verts))
    return comps


def is_closed_simple(edges, verts):
    if len(edges) < 3 or len(edges) != len(verts):
        return False
    touch = {}
    for e in edges:
        for v in e.verts:
            touch[v] = touch.get(v, 0) + 1
    return all(c == 2 for c in touch.values())


def main():
    bpy.ops.wm.open_mainfile(filepath=IN_PATH)
    ob = bpy.data.objects[CAPITAL_MASTER_OBJECT]

    bm = bmesh.new()
    bm.from_mesh(ob.data)
    tag = bm.verts.layers.int.new("open_tag")  # before any refs are taken

    b0, nm0 = full_stats(bm)
    faces0 = len(bm.faces)
    log(f"before: faces {faces0}  boundary {b0}  non-manifold {nm0}")

    comps = boundary_components(bm)
    open_verts = []
    for edges, verts in comps:
        if not is_closed_simple(edges, verts):
            open_verts += list(verts)
    log(f"{len(comps)} loops total, {len(open_verts)} verts on open/branch loops")

    if open_verts:
        for v in open_verts:
            v[tag] = 1
        import mathutils
        kd = mathutils.kdtree.KDTree(len(open_verts))
        for i, v in enumerate(open_verts):
            kd.insert(v.co, i)
        kd.balance()
        gaps = []
        for v in open_verts:
            for co, idx, dist in kd.find_n(v.co, 2):
                if dist > 1e-9:
                    gaps.append(dist)
                    break
        gaps.sort()
        dist = gaps[-1] * 1.05 if gaps else 0.0
        log(f"open-fragment gap: median {gaps[len(gaps)//2]:.6f}  max {gaps[-1]:.6f}  "
            f"welding at {dist:.6f}")
        sel = [v for v in bm.verts if v[tag] == 1]
        bmesh.ops.remove_doubles(bm, verts=sel, dist=dist)
        bm.verts.index_update()
        bm.edges.index_update()
        b1, nm1 = full_stats(bm)
        log(f"after open-fragment weld: boundary {b0}->{b1}  non-manifold {nm0}->{nm1}")

    # --- fill every now-closed simple loop, one call per loop ---
    comps2 = boundary_components(bm)
    filled = 0
    still_open = 0
    for edges, verts in comps2:
        if not is_closed_simple(edges, verts):
            still_open += 1
            continue
        before_faces = len(bm.faces)
        bmesh.ops.triangle_fill(bm, use_beauty=True, use_dissolve=False, edges=edges)
        if len(bm.faces) > before_faces:
            filled += 1
    log(f"triangle_fill: closed {filled} loops individually  "
        f"({still_open} loops still open after the weld pass)")

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    b2, nm2 = full_stats(bm)
    faces2 = len(bm.faces)
    bm.to_mesh(ob.data)
    bm.free()
    ob.data.update()

    log("")
    log(f"{'':10s} {'faces':>8s} {'boundary':>9s} {'nonmanifold':>12s}")
    log(f"{'before':10s} {faces0:8d} {b0:9d} {nm0:12d}")
    log(f"{'after':10s} {faces2:8d} {b2:9d} {nm2:12d}")

    for other in list(bpy.data.objects):
        if other is not ob:
            bpy.data.objects.remove(other, do_unlink=True)
    ob.name = CAPITAL_MASTER_OBJECT
    ob.data.name = CAPITAL_MASTER_OBJECT
    os.makedirs(MASTERS, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=OUT_PATH)
    log(f"SAVED {OUT_PATH}")

    # --- render close-ups on the leaf crown, where these gaps live ---
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
    w.node_tree.nodes["Background"].inputs["Color"].default_value = (0.15, 0.16, 0.19, 1)
    w.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.4

    for e, p, y in ((2.6, 42.0, -35.0), (1.6, 42.0, 35.0), (1.4, 65.0, 10.0)):
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

    shot("full_face.png", 0, 8, 0.55, ctr)
    # Zoom on the leaf crown band specifically -- where all the gap loops sat
    # (z roughly 0.2-0.8 in the topology diagnostic's histogram).
    crown_focus = Vector((ctr.x, ctr.y, lo.z + (hi.z - lo.z) * 0.45))
    shot("crown_zoom.png", 15, 10, 0.30, crown_focus)
    shot("crown_zoom_other_side.png", -160, 5, 0.30, crown_focus)


if __name__ == "__main__":
    main()
