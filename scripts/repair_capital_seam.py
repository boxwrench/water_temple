"""Close the capital's real crack: the necking/leaf-crown seam.

scripts/diagnose_capital_topology.py marked every non-manifold and boundary
edge and rendered them against the mesh. Two things fell out of that:

1. Most of the 575 boundary edges trace one continuous closed loop running
   all the way around the capital, exactly where the necking band (below the
   abacus) meets the leaf crown. That is not undercut-leaf noise -- it is the
   donor's two shell pieces (band, crown) never having been welded together,
   because they sit at a real (if small) distance apart, which is also why
   donor_prep's own global weld search declined to run on this mesh: a
   tolerance loose enough to close this seam is loose enough to fuse
   unrelated close geometry in the fine leaf carving elsewhere.
2. The 120 non-manifold edges and the remaining ~150 boundary edges are
   scattered through the acanthus leaves themselves with no such structure --
   consistent with the donor's undercut leaf geometry, not a single fixable
   seam. This script does not touch those.

The fix is a *scoped* weld: find the crack's own two lip-loops by connected-
component search over the boundary-edge graph (a real crack is two long
parallel loops; scattered leaf cracks are tiny, disconnected components by
comparison), then remove-doubles only the vertices on those loops, at a
distance measured from the loops' own real gap -- never a blanket mesh-wide
weld, which is what already failed here once.

Run:  blender --background --python scripts/repair_capital_seam.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import math                                                       # noqa: E402

import bmesh                                                      # noqa: E402
import bpy                                                        # noqa: E402

from paths import CAPITAL_MASTER_OBJECT, MASTERS, RENDERS         # noqa: E402

IN_PATH = os.path.join(MASTERS, "corinthian-capital-master-v2.blend")
OUT_PATH = os.path.join(MASTERS, "corinthian-capital-master-v3.blend")
OUT_RENDER = os.path.join(RENDERS, "capital-seam-repair")

# A loop component smaller than this is leaf-carving noise, not the seam.
RING_MIN_EDGES = 15


def log(*a):
    print("[cap-seam]", *a)
    sys.stdout.flush()


def full_stats(bm):
    boundary = sum(1 for e in bm.edges if len(e.link_faces) == 1)
    nonmanifold = sum(1 for e in bm.edges if len(e.link_faces) > 2)
    return boundary, nonmanifold


def boundary_components(bm):
    """Connected components of the boundary-edge-only subgraph."""
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


def main():
    bpy.ops.wm.open_mainfile(filepath=IN_PATH)
    ob = bpy.data.objects[CAPITAL_MASTER_OBJECT]

    bm = bmesh.new()
    bm.from_mesh(ob.data)
    # Created up front, before anything below captures BMVert references:
    # bm.verts.layers.int.new() reallocates CustomData and invalidates every
    # Python BMVert handle taken before the call ("BMesh data ... has been
    # removed"). Creating it here means nothing later needs to hold a stale one.
    tag = bm.verts.layers.int.new("ring_tag")
    b0, nm0 = full_stats(bm)
    faces_before = len(bm.faces)
    log(f"before: faces {faces_before}  boundary {b0}  non-manifold {nm0}")

    comps = boundary_components(bm)
    comps.sort(key=lambda c: -len(c[0]))
    log(f"{len(comps)} disconnected boundary-edge loops found")
    for i, (edges, verts) in enumerate(comps[:8]):
        log(f"  loop {i}: {len(edges)} edges, {len(verts)} verts")

    ring_verts = set()
    ring_loops = 0
    for edges, verts in comps:
        if len(edges) >= RING_MIN_EDGES:
            ring_verts |= verts
            ring_loops += 1
    log(f"treating {ring_loops} loop(s) >= {RING_MIN_EDGES} edges as the seam: "
        f"{len(ring_verts)} vertices")

    if not ring_verts:
        log("no loop met the size threshold -- nothing to do, aborting")
        bm.free()
        return

    ring_verts = list(ring_verts)

    # Measure the seam's own real gap: for each ring vertex, distance to its
    # nearest other ring vertex. The crack's matching lip is the closest thing
    # to most of these points; the leaf carving's own feature spacing is not
    # part of this vertex set at all, so this measures the crack, not noise.
    import mathutils
    kd = mathutils.kdtree.KDTree(len(ring_verts))
    for i, v in enumerate(ring_verts):
        kd.insert(v.co, i)
    kd.balance()

    gaps = []
    for v in ring_verts:
        hits = kd.find_n(v.co, 2)  # self + nearest other
        for co, idx, dist in hits:
            if dist > 1e-9:
                gaps.append(dist)
                break
    gaps.sort()
    med = gaps[len(gaps) // 2]
    p90 = gaps[int(len(gaps) * 0.9)]
    log(f"seam gap across {len(gaps)} ring verts: median {med:.6f}  "
        f"p90 {p90:.6f}  max {gaps[-1]:.6f}")

    # Tag ring vertices in the layer created up top, then copy: bm.copy() does
    # not keep .index attributes valid for lookup (that bit us in
    # repair_masters.py already), but custom data layers travel with their
    # vertex correctly across the copy.
    for v in ring_verts:
        v[tag] = 1

    # Trial a few thresholds bracketing the measured gap, scored on the whole
    # mesh (only tagged verts are ever passed to remove_doubles, so nothing
    # outside this vertex set can move regardless of distance chosen).
    candidates = sorted(set([med, p90, gaps[-1], p90 * 1.3, gaps[-1] * 1.3]))
    best = None
    for dist in candidates:
        trial = bm.copy()
        ttag = trial.verts.layers.int["ring_tag"]
        sel = [v for v in trial.verts if v[ttag] == 1]
        bmesh.ops.remove_doubles(trial, verts=sel, dist=dist)
        b, nm = full_stats(trial)
        log(f"  trial dist {dist:.6f}: boundary {b}  non-manifold {nm}  score {b + nm}")
        if best is None or (b + nm) < best[0]:
            if best is not None:
                best[3].free()
            best = (b + nm, dist, (b, nm), trial)
        else:
            trial.free()

    score, chosen_dist, (b1, nm1), trial_bm = best
    log(f"chosen: dist {chosen_dist:.6f} -> boundary {b1}  non-manifold {nm1}")

    trial_bm.to_mesh(ob.data)
    trial_bm.free()
    bm.free()
    ob.data.update()

    # Re-check on the real mesh (not the trial copy) and recalc normals --
    # merging verts does not create new faces, but keep this cheap step for
    # safety/consistency with the rest of the repair chain.
    bm2 = bmesh.new()
    bm2.from_mesh(ob.data)
    bmesh.ops.recalc_face_normals(bm2, faces=bm2.faces[:])
    b2, nm2 = full_stats(bm2)
    faces_after = len(bm2.faces)
    bm2.to_mesh(ob.data)
    bm2.free()
    ob.data.update()

    log("")
    log(f"{'':10s} {'faces':>8s} {'boundary':>9s} {'nonmanifold':>12s}")
    log(f"{'before':10s} {faces_before:8d} {b0:9d} {nm0:12d}")
    log(f"{'after':10s} {faces_after:8d} {b2:9d} {nm2:12d}")

    for other in list(bpy.data.objects):
        if other is not ob:
            bpy.data.objects.remove(other, do_unlink=True)
    ob.name = CAPITAL_MASTER_OBJECT
    ob.data.name = CAPITAL_MASTER_OBJECT
    os.makedirs(MASTERS, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=OUT_PATH)
    log(f"SAVED {OUT_PATH}")

    # --- quick render for visual confirmation ---
    from mathutils import Vector
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
    sc.render.resolution_x = 1000
    sc.render.resolution_y = 1000
    sc.render.image_settings.file_format = "PNG"

    w = bpy.data.worlds.new("W")
    sc.world = w
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs["Color"].default_value = (0.30, 0.31, 0.34, 1)
    w.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.45

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

    shot("seam-fixed_face.png", 0, 10)
    shot("seam-fixed_corner.png", 45, 14)
    shot("seam-fixed_seamzoom.png", 20, 8)


if __name__ == "__main__":
    main()
