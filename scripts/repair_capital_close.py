"""Cap the open bottom and close the small gaps visible between leaves.

Builds on corinthian-capital-master-v3.blend (the scoped seam weld). The user
found, by eye, that you can still see into the hollow interior through gaps
between overlapping leaf tips -- a visible defect, not just a mesh-integrity
number. This closes three different kinds of hole, each with the method that
actually suits its shape:

1. **The bottom rim** -- one large, roughly circular, near-planar loop where
   the shell is simply open (it sits on the shaft; nothing ever modeled a
   floor). A straight n-gon fill is the right tool: flat loop, flat fill.
2. **The necking/crown seam remnant** -- whatever the scoped weld
   (repair_capital_seam.py) did not close. Try pushing that weld further
   first (still scoped to just this loop's own vertices, so nothing else can
   move); whatever is left after that gets an n-gon fill as a fallback, same
   reasoning as the bottom rim -- it is a long band, not a complex 3D pocket.
3. **Small leaf-carving gaps** -- everything else, dozens of tiny loops from
   the donor's undercut geometry. These are the ones that read as "holes
   between leaves" from outside. n-gon/triangle fill via bmesh's own
   holes_fill, which handles arbitrary small loops without needing a matched
   weld pair the way the big seam did.

This does NOT touch anything that isn't a boundary edge, so the interior
triangle-stripping the user wants next (remove faces no exterior angle can
ever see) still has an intact, still-hollow shell to work from -- capping the
openings is a prerequisite for that, not a replacement for it, since you
cannot tell what is "never visible" through a hole that shouldn't be there.

Run:  blender --background --python scripts/repair_capital_close.py
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
OUT_PATH = os.path.join(MASTERS, "corinthian-capital-master-v4.blend")
OUT_RENDER = os.path.join(RENDERS, "capital-close-repair")

BOTTOM_Z_FRAC = 0.05   # loop counts as "bottom rim" if its mean z is this close to the base
SEAM_MIN_EDGES = 30    # anything still this big after v3 is the seam remnant, not leaf noise


def log(*a):
    print("[cap-close]", *a)
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


def main():
    bpy.ops.wm.open_mainfile(filepath=IN_PATH)
    ob = bpy.data.objects[CAPITAL_MASTER_OBJECT]

    lo = Vector((1e18,) * 3)
    hi = Vector((-1e18,) * 3)
    for v in ob.data.vertices:
        for i in range(3):
            lo[i] = min(lo[i], v.co[i])
            hi[i] = max(hi[i], v.co[i])
    diag = (hi - lo).length
    z_thresh = lo.z + (hi.z - lo.z) * BOTTOM_Z_FRAC

    bm = bmesh.new()
    bm.from_mesh(ob.data)
    tag = bm.verts.layers.int.new("seam_tag")  # up front, before any refs are held

    b0, nm0 = full_stats(bm)
    faces0 = len(bm.faces)
    log(f"before: faces {faces0}  boundary {b0}  non-manifold {nm0}")

    comps = boundary_components(bm)
    comps.sort(key=lambda c: -len(c[0]))
    log(f"{len(comps)} boundary loops")

    bottom_edges, seam_verts, leaf_edges = [], [], []
    n_bottom_loops = n_leaf_loops = 0
    for edges, verts in comps:
        mean_z = sum(v.co.z for v in verts) / len(verts)
        if mean_z <= z_thresh:
            bottom_edges += edges
            n_bottom_loops += 1
            log(f"  loop: {len(edges)} edges -> BOTTOM RIM (mean z {mean_z:.4f})")
        elif len(edges) >= SEAM_MIN_EDGES:
            seam_verts += list(verts)
            log(f"  loop: {len(edges)} edges -> SEAM REMNANT (mean z {mean_z:.4f})")
        else:
            leaf_edges += edges
            n_leaf_loops += 1
    log(f"bottom rim: {len(bottom_edges)} edges across {n_bottom_loops} loop(s)   "
        f"seam remnant: {len(seam_verts)} verts   "
        f"leaf gaps: {len(leaf_edges)} edges across {n_leaf_loops} loops")

    # --- push the seam remnant weld further, scoped to just its own verts ---
    if seam_verts:
        for v in seam_verts:
            v[tag] = 1
        import mathutils
        kd = mathutils.kdtree.KDTree(len(seam_verts))
        for i, v in enumerate(seam_verts):
            kd.insert(v.co, i)
        kd.balance()
        gaps = []
        for v in seam_verts:
            for co, idx, dist in kd.find_n(v.co, 2):
                if dist > 1e-9:
                    gaps.append(dist)
                    break
        gaps.sort()
        # Push to the full measured max (repair_capital_seam.py stopped at
        # p90*1.3 out of caution; closing the rest now matters more than the
        # small risk of a slightly-simplified seam line, since anything left
        # gets an n-gon fill anyway).
        dist = gaps[-1] * 1.05 if gaps else 0.0
        sel = [v for v in bm.verts if v[tag] == 1]
        before_b, before_nm = full_stats(bm)
        if dist > 0:
            bmesh.ops.remove_doubles(bm, verts=sel, dist=dist)
        after_b, after_nm = full_stats(bm)
        log(f"seam remnant weld at {dist:.6f}: boundary {before_b}->{after_b}  "
            f"non-manifold {before_nm}->{after_nm}")
        # remove_doubles leaves edge/vert .index stale; boundary_components()
        # keys its dedup set on e.index, so this must run before calling it again.
        bm.verts.index_update()
        bm.edges.index_update()

    # --- fill only the real hole: the seam remnant ---
    # Investigation (see chat, and scripts/diagnose_capital_topology.py) found
    # this mesh has exactly ONE hole with real area: the necking/crown seam,
    # which is what the user can actually see into the hollow interior
    # through. Every other one of the ~108 remaining boundary loops is a
    # near-zero-area sliver (one measured at 3.3e-09 -- three points 1e-4
    # apart) left over from the donor's own decimation history: sub-pixel,
    # not visible, and holes_fill correctly refuses to fill a degenerate
    # triangle since there is no meaningful face to create. There is also no
    # hole at the bottom at all -- no boundary loop was found anywhere near
    # z=0, so the base was already closed before this script ever ran.
    comps2 = boundary_components(bm)
    comps2.sort(key=lambda c: -len(c[0]))
    seam_edges, seam_verts = comps2[0]
    log(f"largest remaining loop: {len(seam_edges)} edges "
        f"(everything else in the {len(comps2)} loops found is a sub-visible sliver)")
    res = bmesh.ops.holes_fill(bm, edges=seam_edges, sides=0)
    log(f"seam fill: {len(res['faces'])} face(s) created")

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    b1, nm1 = full_stats(bm)
    faces1 = len(bm.faces)
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

    # --- cutaway render again, same framing as diagnose_capital_interior.py,
    # to directly compare "can you still see through" before/after ---
    ctr = (lo + hi) / 2.0
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

    shot("cutaway_straight.png", -90, 6)
    shot("cutaway_angle.png", -65, 18)

    # Also a normal exterior view -- this is what actually needs checking for
    # "no more visible gaps between leaves" and "no ugly fill artifacts".
    ob.hide_render = False
    ob2.hide_render = True
    ob.data.materials.clear()
    ext_mat = bpy.data.materials.new("EXT")
    ext_mat.use_nodes = True
    ext_mat.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.85, 0.83, 0.78, 1)
    ext_mat.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.80
    ob.data.materials.append(ext_mat)
    for p in ob.data.polygons:
        p.use_smooth = True
    cam_data.ortho_scale = diag * 0.55
    shot("exterior_face.png", 0, 8)
    shot("exterior_lowangle.png", 10, -18)


if __name__ == "__main__":
    main()
