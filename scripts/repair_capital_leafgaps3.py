"""Close the last ~76 tiny leaf-gap loops by self-collapse, not fill.

Three different face-fill operators have now failed on these loops:
holes_fill (returns empty), triangle_fill (fabricates a phantom face
elsewhere in the mesh, doesn't touch the loop), contextual_create (returns
nothing at all) -- see scratchpad/probe_triangle_fill.py and
probe_contextual_create.py for the verified evidence. Separately, three
different "rebuild the whole surface from a volume/offset field" strategies
also failed (Solidify Complex: catastrophic spikes at sharp creases;
Solidify Simple: same spikes via Even Thickness's angle blowup; Mesh to
Volume -> Volume to Mesh: numerically perfect closure but a visibly torn,
fragmented render) -- this mesh's zero-thickness, deeply undercut, self-
overlapping leaf geometry is a bad fit for both families of fix.

The technique that HAS worked cleanly twice already this session
(repair_capital_seam.py's 575->375 boundary fix, repair_capital_leafgaps.py's
293->227 open-fragment fix) is a scoped bmesh.ops.remove_doubles weld, never
a fill. Every remaining loop here is a CLOSED simple cycle (not an open
fragment needing to find a partner), so the applicable move is different:
weld the loop's OWN vertices to each other, scoped to just that loop, at a
distance sized to that loop's own diagonal. This doesn't cover the hole with
a face -- it collapses the hole to a point/degenerate sliver, which
dissolve_degenerate then cleans up. No assumption about interior/exterior,
no new geometry, no offset -- just merging vertices that were already
extremely close together, which is what a real construction crack actually
is.

Run:  blender --background --python scripts/repair_capital_leafgaps3.py
"""

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bmesh                                                      # noqa: E402
import bpy                                                        # noqa: E402
from mathutils import Vector                                      # noqa: E402

from paths import CAPITAL_MASTER_OBJECT, MASTERS, RENDERS         # noqa: E402

IN_PATH = os.path.join(MASTERS, "corinthian-capital-master-v5.blend")
OUT_PATH = os.path.join(MASTERS, "corinthian-capital-master-v7.blend")
OUT_RENDER = os.path.join(RENDERS, "capital-leafgap3-repair")

# Safety valve: if any loop's own diagonal is bigger than this, self-collapse
# would visibly pinch a real feature shut -- skip it and report instead of
# silently damaging the model. Current known max is 0.018 (0.9% of capital
# diag ~1.95), well under this.
MAX_SAFE_LOOP_DIAG = 0.05


def log(*a):
    print("[cap-leafgap3]", *a)
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


def is_closed_simple(edges, verts):
    if len(edges) < 3 or len(edges) != len(verts):
        return False
    touch = {}
    for e in edges:
        for v in e.verts:
            touch[v] = touch.get(v, 0) + 1
    return all(c == 2 for c in touch.values())


def loop_diag(verts):
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
    f0, b0, nm0 = full_stats(bm)
    log(f"before: faces {f0}  boundary {b0}  non-manifold {nm0}")

    comps = boundary_components(bm)
    closed = [(e, v) for e, v in comps if is_closed_simple(e, v)]
    open_loops = len(comps) - len(closed)
    log(f"{len(comps)} loops total: {len(closed)} closed-simple, {open_loops} open/branch")

    diags = sorted((loop_diag(v), e, v) for e, v in closed)
    unsafe = [d for d in diags if d[0] > MAX_SAFE_LOOP_DIAG]
    log(f"loop diagonals: min {diags[0][0]:.6f}  max {diags[-1][0]:.6f}  "
        f"({len(unsafe)} exceed the {MAX_SAFE_LOOP_DIAG} safety cap)")

    welded = 0
    skipped = 0
    for diag, edges, verts in diags:
        if diag > MAX_SAFE_LOOP_DIAG:
            skipped += 1
            continue
        dist = diag * 1.5 + 1e-7  # comfortably exceeds this loop's own span
        bmesh.ops.remove_doubles(bm, verts=list(verts), dist=dist)
        welded += 1

    bmesh.ops.dissolve_degenerate(bm, dist=1e-6, edges=bm.edges[:])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])

    f1, b1, nm1 = full_stats(bm)
    log(f"welded {welded} loops, skipped {skipped} (over safety cap)")
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

    shot("v7_face.png", 0, 8, 0.55, ctr)
    shot("v7_corner.png", 45, 14, 0.55, ctr)
    crown_focus = Vector((ctr.x, ctr.y, lo.z + (hi.z - lo.z) * 0.45))
    shot("v7_crown_zoom.png", 15, 10, 0.30, crown_focus)
    shot("v7_crown_zoom_other.png", -160, 5, 0.30, crown_focus)


if __name__ == "__main__":
    main()
