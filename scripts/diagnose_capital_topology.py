"""Where, exactly, are the capital's non-manifold edges?

The easy pass (repair_masters.py) took the capital from 129 to 120 non-manifold
edges -- barely moved, because these are not weld-fixable cracks or duplicate
faces (both already handled). This is a spatial read on what's left, before
picking a repair strategy: are they clustered in the acanthus undercuts (the
donor's known trouble spot, per the capital's own build-script docstring), or
spread across the whole capital (which would suggest a different cause).

Marks each non-manifold edge's midpoint with a small red cube and each boundary
edge's midpoint with a small blue cube, renders them alongside the (semi-
transparent) capital from a few angles. Read-only with respect to the master;
writes only to renders/.

Run:  blender --background --python scripts/diagnose_capital_topology.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import math                                                       # noqa: E402

import bmesh                                                      # noqa: E402
import bpy                                                        # noqa: E402
from mathutils import Vector                                      # noqa: E402

from paths import CAPITAL_MASTER_OBJECT, MASTERS, RENDERS         # noqa: E402

IN_PATH = os.path.join(MASTERS, "corinthian-capital-master-v2.blend")
OUT = os.path.join(RENDERS, "capital-topology-diagnostic")


def log(*a):
    print("[cap-diag]", *a)
    sys.stdout.flush()


def marker_cube(center, size, verts_out, faces_out):
    s = size / 2.0
    base = len(verts_out)
    for dx in (-s, s):
        for dy in (-s, s):
            for dz in (-s, s):
                verts_out.append(center + Vector((dx, dy, dz)))
    idx = [base + i for i in range(8)]
    faces_out += [
        (idx[0], idx[1], idx[3], idx[2]), (idx[4], idx[6], idx[7], idx[5]),
        (idx[0], idx[4], idx[5], idx[1]), (idx[2], idx[3], idx[7], idx[6]),
        (idx[0], idx[2], idx[6], idx[4]), (idx[1], idx[5], idx[7], idx[3]),
    ]


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
    size = diag * 0.004

    bm = bmesh.new()
    bm.from_mesh(ob.data)

    nm_mid, nm_z, nm_r = [], [], []
    b_mid, b_z, b_r = [], [], []
    for e in bm.edges:
        n = len(e.link_faces)
        if n > 2:
            m = (e.verts[0].co + e.verts[1].co) / 2.0
            nm_mid.append(m)
            nm_z.append(m.z)
            nm_r.append(math.hypot(m.x, m.y))
        elif n == 1:
            m = (e.verts[0].co + e.verts[1].co) / 2.0
            b_mid.append(m)
            b_z.append(m.z)
            b_r.append(math.hypot(m.x, m.y))
    bm.free()

    zlo, zhi = lo.z, hi.z
    zrange = zhi - zlo

    def band_hist(zs, label):
        bands = [0] * 5
        for z in zs:
            frac = (z - zlo) / zrange
            b = min(4, max(0, int(frac * 5)))
            bands[b] += 1
        log(f"{label} by height band (0=bell/base .. 4=abacus/top): {bands}")

    log(f"non-manifold edges: {len(nm_mid)}   boundary edges: {len(b_mid)}")
    band_hist(nm_z, "non-manifold")
    band_hist(b_z, "boundary")
    if nm_r:
        log(f"non-manifold radius range: {min(nm_r):.4f} .. {max(nm_r):.4f}  "
            f"(capital diag {diag:.4f})")
    if b_r:
        log(f"boundary radius range: {min(b_r):.4f} .. {max(b_r):.4f}")

    # --- build marker objects ---
    verts_nm, faces_nm = [], []
    for m in nm_mid:
        marker_cube(m, size, verts_nm, faces_nm)
    me_nm = bpy.data.meshes.new("NM_MARKERS")
    me_nm.from_pydata(verts_nm, [], faces_nm)
    me_nm.update()
    ob_nm = bpy.data.objects.new("NM_MARKERS", me_nm)
    bpy.context.scene.collection.objects.link(ob_nm)

    verts_b, faces_b = [], []
    for m in b_mid:
        marker_cube(m, size, verts_b, faces_b)
    me_b = bpy.data.meshes.new("BOUND_MARKERS")
    me_b.from_pydata(verts_b, [], faces_b)
    me_b.update()
    ob_b = bpy.data.objects.new("BOUND_MARKERS", me_b)
    bpy.context.scene.collection.objects.link(ob_b)

    red = bpy.data.materials.new("RED")
    red.use_nodes = True
    red.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (1, 0.05, 0.05, 1)
    red.node_tree.nodes["Principled BSDF"].inputs["Emission Color"].default_value = (1, 0, 0, 1)
    red.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"].default_value = 2.0
    ob_nm.data.materials.append(red)

    blue = bpy.data.materials.new("BLUE")
    blue.use_nodes = True
    blue.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.1, 0.4, 1, 1)
    blue.node_tree.nodes["Principled BSDF"].inputs["Emission Color"].default_value = (0.1, 0.4, 1, 1)
    blue.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"].default_value = 2.0
    ob_b.data.materials.append(blue)

    clay = bpy.data.materials.new("CLAY")
    clay.use_nodes = True
    b = clay.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (0.6, 0.6, 0.62, 1)
    b.inputs["Roughness"].default_value = 0.9
    if "Alpha" in b.inputs:
        b.inputs["Alpha"].default_value = 0.55
    clay.blend_method = "BLEND"
    clay.show_transparent_back = False
    ob.data.materials.clear()
    ob.data.materials.append(clay)
    for p in ob.data.polygons:
        p.use_smooth = True

    os.makedirs(OUT, exist_ok=True)
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_EEVEE"
    sc.render.resolution_x = 1100
    sc.render.resolution_y = 1100
    sc.render.image_settings.file_format = "PNG"
    sc.render.film_transparent = False

    w = bpy.data.worlds.new("W")
    sc.world = w
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs["Color"].default_value = (0.20, 0.21, 0.24, 1)
    w.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.5

    for e, p, y in ((2.6, 42.0, -35.0), (1.6, 42.0, 35.0), (0.8, 10.0, 180.0)):
        li = bpy.data.lights.new("s", "SUN")
        li.energy = e
        o = bpy.data.objects.new("s", li)
        sc.collection.objects.link(o)
        o.rotation_euler = (math.radians(p), 0.0, math.radians(y))

    ctr = (lo + hi) / 2.0
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
        sc.render.filepath = os.path.join(OUT, name)
        bpy.ops.render.render(write_still=True)
        log("WROTE " + name)

    shot("diag_face.png", 0, 6)
    shot("diag_corner.png", 45, 12)
    shot("diag_top.png", 0, 80)
    shot("diag_low.png", 0, -20)


if __name__ == "__main__":
    main()
