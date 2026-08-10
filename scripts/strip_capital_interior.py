"""Remove capital faces that are never visible from any realistic outside view.

The capital is a single zero-thickness shell whose deep leaf/volute undercuts
fold back on themselves (confirmed via the bisected cutaway render in
diagnose_capital_interior.py) -- meaning a real fraction of its 248,899
faces are the permanently-hidden backside of that same fold, never visible
once the capital sits on the shaft. This is also very likely a major
contributor to the decimate-collapse floor found while testing LOD
reduction (23,403 faces, proportional whether tested on the whole mesh or
a quarter slice) -- real geometric complexity, not a defect, so removing it
is the correct lever, not more welding.

Method: sample many outward-facing viewpoints on two spheres around the
capital (near + far radius, for both grazing and near-parallel view angles),
excluding the cone directly beneath the capital's own bottom (physically
inside the column shaft in the real assembly -- never a valid camera
position). For each face, ray-cast from every not-yet-resolved viewpoint
toward its center; a face is kept the moment ANY viewpoint sees it
unoccluded (BVH first-hit index matches), and once resolved it is skipped
for all later viewpoints (most faces resolve on the first few viewpoints,
so this early-exit is what keeps ~250k faces x hundreds of viewpoints
tractable). Faces resolved as never-visible after every viewpoint are
removed.

This produces a NEW candidate file for review, it does not touch the
promoted CAPITAL_MASTER (v10) -- multi-angle before/after renders need to
confirm nothing visible got clipped before this is ever promoted.

Run:  blender --background --python scripts/strip_capital_interior.py
"""

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bmesh                                                      # noqa: E402
import bpy                                                        # noqa: E402
from mathutils import Vector                                      # noqa: E402
from mathutils.bvhtree import BVHTree                             # noqa: E402

from paths import CAPITAL_MASTER, CAPITAL_MASTER_OBJECT, MASTERS, RENDERS  # noqa: E402

OUT_PATH = os.path.join(MASTERS, "corinthian-capital-master-v11.blend")
OUT_RENDER = os.path.join(RENDERS, "capital-interior-strip")

N_VIEWPOINTS_PER_RADIUS = 220
MIN_ELEVATION_DEG = -15.0  # below this, the viewpoint would be inside the shaft
BACKFACE_EPS = 1e-4
HIT_DIST_TOL = 1e-4


def log(*a):
    print("[cap-strip]", *a)
    sys.stdout.flush()


def fibonacci_sphere_points(n):
    pts = []
    ga = math.pi * (3.0 - math.sqrt(5.0))
    for i in range(n):
        y = 1 - (i / float(n - 1)) * 2
        r = math.sqrt(max(0.0, 1 - y * y))
        theta = ga * i
        x = math.cos(theta) * r
        z = math.sin(theta) * r
        pts.append(Vector((x, z, y)))  # z-up remap
    return pts


def main():
    bpy.ops.wm.open_mainfile(filepath=CAPITAL_MASTER)
    ob = bpy.data.objects[CAPITAL_MASTER_OBJECT]

    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bm.faces.ensure_lookup_table()
    bm.verts.ensure_lookup_table()
    faces_before = len(bm.faces)

    lo = Vector((1e18,) * 3)
    hi = Vector((-1e18,) * 3)
    for v in bm.verts:
        for i in range(3):
            lo[i] = min(lo[i], v.co[i])
            hi[i] = max(hi[i], v.co[i])
    ctr = (lo + hi) / 2.0
    radius = (hi - lo).length / 2.0
    log(f"faces {faces_before}  center {tuple(round(c,4) for c in ctr)}  radius {radius:.4f}")

    bvh = BVHTree.FromBMesh(bm)

    dirs = fibonacci_sphere_points(N_VIEWPOINTS_PER_RADIUS)
    dirs = [d for d in dirs if math.degrees(math.asin(max(-1.0, min(1.0, d.z)))) >= MIN_ELEVATION_DEG]
    log(f"{len(dirs)} viewpoint directions survive the shaft-exclusion cone "
        f"(elevation >= {MIN_ELEVATION_DEG} deg)")

    viewpoints = []
    for radius_mult in (2.2, 6.0):
        for d in dirs:
            viewpoints.append(ctr + d * (radius * radius_mult))
    log(f"{len(viewpoints)} total viewpoints (2 radii)")

    face_centers = {f.index: f.calc_center_median() for f in bm.faces}
    face_normals = {f.index: f.normal.copy() for f in bm.faces}
    unresolved = set(face_centers.keys())
    visible = set()

    for vi, vp in enumerate(viewpoints):
        if not unresolved:
            break
        newly_visible = []
        for fidx in unresolved:
            center = face_centers[fidx]
            to_face = center - vp
            dist = to_face.length
            if dist < 1e-9:
                newly_visible.append(fidx)
                continue
            direction = to_face / dist
            if direction.dot(face_normals[fidx]) > -BACKFACE_EPS:
                continue  # back-facing from this viewpoint, can't be the one that sees it
            loc, nrm, idx, hit_dist = bvh.ray_cast(vp, direction, dist + HIT_DIST_TOL)
            if idx == fidx and hit_dist is not None and abs(hit_dist - dist) < HIT_DIST_TOL:
                newly_visible.append(fidx)
        for fidx in newly_visible:
            unresolved.discard(fidx)
            visible.add(fidx)
        if vi % 20 == 0 or not unresolved:
            log(f"  viewpoint {vi+1}/{len(viewpoints)}: {len(visible)} visible, "
                f"{len(unresolved)} still unresolved")

    invisible = unresolved
    log(f"RESULT: {len(visible)} visible faces, {len(invisible)} never-visible "
        f"({100*len(invisible)/faces_before:.1f}% of the mesh)")

    to_delete = [bm.faces[i] for i in invisible]
    bmesh.ops.delete(bm, geom=to_delete, context="FACES")
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if len(v.link_faces) == 0], context="VERTS")

    boundary = sum(1 for e in bm.edges if len(e.link_faces) == 1)
    nonmanifold = sum(1 for e in bm.edges if len(e.link_faces) > 2)
    faces_after = len(bm.faces)
    log(f"after strip: faces {faces_before} -> {faces_after}  boundary {boundary}  non-manifold {nonmanifold}")

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

    # --- multi-angle render for a careful before/after visual check ---
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

    diag = (hi - lo).length

    def shot(name, yaw_deg, pitch_deg, zoom=0.55, focus=None):
        if focus is None:
            focus = ctr
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

    # Wide angular coverage, low and high pitch, to stress-test whether
    # anything visible got clipped.
    for yaw in (0, 30, 60, 90, 120, 150, 180, 210, 240, 270, 300, 330):
        shot(f"v11_yaw{yaw}.png", yaw, 15)
    shot("v11_low.png", 20, -10)
    shot("v11_high.png", 20, 45)


if __name__ == "__main__":
    main()
