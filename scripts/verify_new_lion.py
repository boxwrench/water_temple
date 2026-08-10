"""Verify donors/lion.glb on its own, before any temple integration.

Two questions this answers, in order:

1. **Where is the real symmetry plane?**  The user's read is that the donor "is
   not symmetrical". That can mean two very different things: the head is *posed*
   (yawed/tilted inside the mesh, but sculpted symmetrically about its own tilted
   axis), or it is genuinely sculpted differently on the two sides. Mirroring
   across the naive bounding-box centerline is only correct in the second case;
   in the first it produces a twisted mask. So we search for the plane that best
   maps the mesh onto itself (yaw, roll, offset) and report the residual. A low
   residual at a non-zero yaw means "posed"; a high residual everywhere means
   "genuinely asymmetric".

2. **Which half is the better half?**  Rendered side by side, both mirrored into
   full faces, under *mirror-symmetric* lighting -- an off-axis key (like the one
   in inspect_donor.py) flatters whichever side it faces and would bias the call.

Read-only with respect to donors/ and temple-model/. Writes renders and a JSON
report to renders/lion-new-symmetry/.

Run:  blender --background --python scripts/verify_new_lion.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import json                                                     # noqa: E402
import math                                                     # noqa: E402
import random                                                   # noqa: E402

import bmesh                                                    # noqa: E402
import bpy                                                      # noqa: E402
from mathutils import Matrix, Vector                            # noqa: E402
from mathutils.kdtree import KDTree                             # noqa: E402

from donor_prep import bounds, import_donor                     # noqa: E402,F401
from paths import DONORS, RENDERS                               # noqa: E402

DONOR = os.path.join(DONORS, "lion.glb")
OUT = os.path.join(RENDERS, "lion-new-symmetry")

RES = 1000

# Points used to *score* a candidate plane vs. points used to *represent* the
# surface the reflected points are measured against. The tree can be dense
# cheaply; the query set is what costs time, so it stays small in the coarse pass.
TREE_N = 40000
COARSE_Q = 1500
FINE_Q = 6000

# Only score against the sculpted front. The flat mounting back is trivially
# symmetric and would dilute the residual toward zero for every candidate plane.
FRONT_FRACTION = 0.35


def log(*a):
    print("[verify-lion]", *a)
    sys.stdout.flush()


# ---------------------------------------------------------------- load


def load_donor():
    """The raw donor, deliberately un-welded.

    This script measures the donor as it actually arrives, so the symmetry
    numbers it reports describe the file on disk. The weld belongs in the
    master build (donor_prep.weld), where it precedes the decimate that would
    otherwise tear the split seams open.
    """
    return import_donor(DONOR, name="LION_DONOR")


# ---------------------------------------------------------------- symmetry


def plane_normal(yaw_deg, roll_deg):
    """Unit normal of a candidate mirror plane.

    Starts at +Y (the expected mirror normal for a +X-facing wall relief),
    rolled about X (head tilt) then yawed about Z (head turn).
    """
    y, r = math.radians(yaw_deg), math.radians(roll_deg)
    return Vector((-math.cos(r) * math.sin(y), math.cos(r) * math.cos(y), math.sin(r)))


def sample_points(ob, n, seed=0):
    verts = ob.data.vertices
    total = len(verts)
    rng = random.Random(seed)
    idx = rng.sample(range(total), min(n, total))
    return [verts[i].co.copy() for i in idx]


def build_tree(points):
    t = KDTree(len(points))
    for i, p in enumerate(points):
        t.insert(p, i)
    t.balance()
    return t


def residual(tree, query, normal, d, diag):
    """Mean normalised distance from each reflected query point to the surface."""
    total = 0.0
    for p in query:
        k = 2.0 * (normal.dot(p) - d)
        q = p - normal * k
        _, _, dist = tree.find(q)
        total += dist
    return (total / len(query)) / diag


def find_symmetry_plane(ob, lo, hi):
    diag = (hi - lo).length
    tree_pts = sample_points(ob, TREE_N, seed=1)
    tree = build_tree(tree_pts)

    x_cut = lo.x + FRONT_FRACTION * (hi.x - lo.x)

    def front_query(n, seed):
        pts = [p for p in sample_points(ob, n * 3, seed=seed) if p.x >= x_cut]
        return pts[:n]

    ctr = (lo + hi) / 2.0
    span = (hi.y - lo.y)

    coarse_q = front_query(COARSE_Q, seed=2)
    log(f"coarse search over {len(coarse_q)} front points "
        f"(x >= {x_cut:.4f}), tree of {len(tree_pts)}")

    best = None
    for yaw in [-24, -16, -8, 0, 8, 16, 24]:
        for roll in [-18, -12, -6, 0, 6, 12, 18]:
            n = plane_normal(yaw, roll)
            base = n.dot(ctr)
            for k in range(-4, 5):
                d = base + k * 0.030 * span
                s = residual(tree, coarse_q, n, d, diag)
                if best is None or s < best[0]:
                    best = (s, yaw, roll, d)
    log(f"coarse best: residual={best[0]:.5f} yaw={best[1]} roll={best[2]} d={best[3]:.5f}")

    fine_q = front_query(FINE_Q, seed=3)
    _, yaw0, roll0, d0 = best
    best = None
    for yi in range(-3, 4):
        yaw = yaw0 + yi * 3.0
        for ri in range(-3, 4):
            roll = roll0 + ri * 2.5
            n = plane_normal(yaw, roll)
            for k in range(-3, 4):
                d = d0 + k * 0.012 * span
                s = residual(tree, fine_q, n, d, diag)
                if best is None or s < best[0]:
                    best = (s, yaw, roll, d)
    log(f"fine best:   residual={best[0]:.5f} yaw={best[1]:.2f} roll={best[2]:.2f} d={best[3]:.5f}")

    # Baseline: the naive plane a careless mirror would have used.
    n_naive = plane_normal(0, 0)
    naive = residual(tree, fine_q, n_naive, n_naive.dot(ctr), diag)
    log(f"naive plane (yaw=0 roll=0, bbox centre): residual={naive:.5f}")

    return {
        "residual": best[0],
        "yaw_deg": best[1],
        "roll_deg": best[2],
        "d": best[3],
        "naive_residual": naive,
        "diag": diag,
    }


def per_side_residual(ob, lo, hi, sym):
    """Split the residual by side, so a genuinely-worse half shows up as such."""
    diag = sym["diag"]
    n = plane_normal(sym["yaw_deg"], sym["roll_deg"])
    d = sym["d"]
    tree = build_tree(sample_points(ob, TREE_N, seed=1))
    x_cut = lo.x + FRONT_FRACTION * (hi.x - lo.x)
    pts = [p for p in sample_points(ob, FINE_Q * 3, seed=4) if p.x >= x_cut]

    sides = {"neg": [], "pos": []}
    for p in pts:
        (sides["pos"] if n.dot(p) - d > 0 else sides["neg"]).append(p)

    out = {}
    for key, group in sides.items():
        if not group:
            out[key] = None
            continue
        out[key] = {
            "n_points": len(group),
            "residual": residual(tree, group, n, d, diag),
        }
    return out


# ---------------------------------------------------------------- canonicalise


def canonical_transform(sym):
    """Rotate the found plane's normal onto +Y and slide the plane onto y = 0.

    Working in this frame turns every later operation (bisect, mirror, measuring
    width/height/depth for the master) into a plain axis-aligned one, and is also
    exactly the frame the eventual master needs: flat back on -X, front +X,
    up +Z, mirror plane y = 0.
    """
    n = plane_normal(sym["yaw_deg"], sym["roll_deg"])
    target = Vector((0.0, 1.0, 0.0))
    rot = n.rotation_difference(target).to_matrix().to_4x4()
    # After rotation the plane normal is +Y and its offset is unchanged in length.
    trans = Matrix.Translation(Vector((0.0, -sym["d"], 0.0)))
    return trans @ rot


# ---------------------------------------------------------------- render


def make_variant(src, name, keep_sign):
    """Duplicate, cut away one side of y = 0, mirror the survivor back across it.

    keep_sign = -1 keeps the viewer's-LEFT half (screen right is +Y when the
    camera looks down -X with +Z up, so -Y is the viewer's left).
    """
    ob = src.copy()
    ob.data = src.data.copy()
    ob.name = name
    bpy.context.scene.collection.objects.link(ob)

    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bmesh.ops.bisect_plane(
        bm,
        geom=list(bm.verts) + list(bm.edges) + list(bm.faces),
        plane_co=Vector((0.0, 0.0, 0.0)),
        plane_no=Vector((0.0, 1.0, 0.0)),
        clear_outer=(keep_sign < 0),   # outer = +Y side
        clear_inner=(keep_sign > 0),
    )
    bm.to_mesh(ob.data)
    bm.free()
    ob.data.update()

    m = ob.modifiers.new("MIRROR", "MIRROR")
    m.use_axis = (False, True, False)
    m.use_mirror_merge = True
    m.merge_threshold = 1e-4
    return ob


def setup_scene(size, ctr):
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_EEVEE"
    sc.render.resolution_x = RES
    sc.render.resolution_y = RES
    sc.render.image_settings.file_format = "PNG"
    sc.render.film_transparent = False

    w = bpy.data.worlds.new("W")
    sc.world = w
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs["Color"].default_value = (0.30, 0.30, 0.31, 1)
    w.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.35

    clay = bpy.data.materials.new("CLAY")
    clay.use_nodes = True
    b = clay.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (0.85, 0.83, 0.78, 1)
    b.inputs["Roughness"].default_value = 0.80

    cam_data = bpy.data.cameras.new("cam")
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = max(size) * 1.10
    cam = bpy.data.objects.new("cam", cam_data)
    sc.collection.objects.link(cam)
    sc.camera = cam
    cam.location = (ctr.x + max(size) * 3.0, ctr.y, ctr.z)
    cam.rotation_euler = (math.radians(90.0), 0.0, math.radians(90.0))

    # Mirror-symmetric key pair about the y = 0 plane, so neither half is
    # flattered by the lighting. A single off-axis key would decide the
    # left-vs-right question by shadow alone.
    def sun(energy, pitch, yaw):
        li = bpy.data.lights.new("sun", "SUN")
        li.energy = energy
        ob = bpy.data.objects.new("sun", li)
        sc.collection.objects.link(ob)
        ob.rotation_euler = (math.radians(pitch), 0.0, math.radians(yaw))
        return ob

    sun(2.2, 55.0, 60.0)
    sun(2.2, 55.0, 120.0)
    sun(0.9, 12.0, 90.0)
    return clay


def main():
    os.makedirs(OUT, exist_ok=True)

    ob = load_donor()
    ob.data.calc_loop_triangles()
    lo, hi = bounds(ob)
    size = hi - lo
    log(f"{len(ob.data.vertices)} verts, {len(ob.data.loop_triangles)} tris")
    log(f"bounds x {lo.x:+.4f}..{hi.x:+.4f}  y {lo.y:+.4f}..{hi.y:+.4f}  z {lo.z:+.4f}..{hi.z:+.4f}")
    log(f"size {size.x:.4f} x {size.y:.4f} x {size.z:.4f}")

    sym = find_symmetry_plane(ob, lo, hi)
    sides = per_side_residual(ob, lo, hi, sym)
    log(f"per-side residual: -Y (viewer left) = {sides['neg']}")
    log(f"per-side residual: +Y (viewer right) = {sides['pos']}")

    # Move into the canonical frame and re-measure there.
    ob.data.transform(canonical_transform(sym))
    ob.data.update()
    lo, hi = bounds(ob)
    size = hi - lo
    log(f"canonical bounds x {lo.x:+.4f}..{hi.x:+.4f}  y {lo.y:+.4f}..{hi.y:+.4f}  "
        f"z {lo.z:+.4f}..{hi.z:+.4f}")
    ctr = (lo + hi) / 2.0

    clay = setup_scene(size, ctr)

    left = make_variant(ob, "LION_LEFT_MIRRORED", -1)
    right = make_variant(ob, "LION_RIGHT_MIRRORED", +1)

    for o in (ob, left, right):
        o.data.materials.clear()
        o.data.materials.append(clay)

    sc = bpy.context.scene
    cam = sc.camera
    full_scale = cam.data.ortho_scale

    def shot(name, visible, zoom=1.0, focus_z=None):
        for o in (ob, left, right):
            o.hide_render = o not in visible
        cam.data.ortho_scale = full_scale * zoom
        cam.location = (ctr.x + max(size) * 3.0, ctr.y,
                        ctr.z if focus_z is None else focus_z)
        sc.render.filepath = os.path.join(OUT, name)
        bpy.ops.render.render(write_still=True)
        log("WROTE", name)

    shot("original_front.png", {ob})
    shot("left_half_mirrored.png", {left})
    shot("right_half_mirrored.png", {right})

    # Centre-line closeups: a mirror weld can leave a visible ridge or crease
    # down the nose, which is a defect the full-head view hides.
    face_z = ctr.z - 0.08 * size.z
    shot("closeup_left_mirrored.png", {left}, zoom=0.45, focus_z=face_z)
    shot("closeup_right_mirrored.png", {right}, zoom=0.45, focus_z=face_z)

    report = {
        "donor": DONOR,
        "verts": len(ob.data.vertices),
        "tris": len(ob.data.loop_triangles),
        "canonical_size": [size.x, size.y, size.z],
        "symmetry": sym,
        "per_side": sides,
    }
    with open(os.path.join(OUT, "report.json"), "w") as f:
        json.dump(report, f, indent=2)
    log("WROTE report.json")


if __name__ == "__main__":
    main()
