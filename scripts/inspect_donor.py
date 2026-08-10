"""Inspect any donor mesh and write preview renders.

General replacement for the one-off GLB inspection scripts. Reports mesh stats
and bounds, works out which axis the relief faces, and renders orthographic
views from every side so the donor can be judged before anything is built on it.

Read-only: never modifies the donor or any project file.

Run:  blender --background --python scripts/inspect_donor.py -- <name-or-path>

`<name-or-path>` may be a bare donor filename (resolved against donors/) or an
absolute path. Renders land in renders/donor-<stem>/.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import math                                                    # noqa: E402

import bpy                                                     # noqa: E402
from mathutils import Vector                                   # noqa: E402

from paths import DONORS, RENDERS                              # noqa: E402

RES = 800


def log(*a):
    print("[donor]", *a)
    sys.stdout.flush()


def target_path():
    argv = sys.argv
    arg = argv[argv.index("--") + 1] if "--" in argv else "leafscroll.glb"
    return arg if os.path.isabs(arg) else os.path.join(DONORS, arg)


def clear():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)


def load(path):
    clear()
    ext = os.path.splitext(path)[1].lower()
    if ext == ".glb" or ext == ".gltf":
        bpy.ops.import_scene.gltf(filepath=path)
    elif ext == ".obj":
        bpy.ops.wm.obj_import(filepath=path)
    elif ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=path)
    else:
        raise SystemExit(f"unsupported donor format: {ext}")
    return [o for o in bpy.data.objects if o.type == "MESH"]


def bounds(meshes):
    lo = Vector((1e18,) * 3)
    hi = Vector((-1e18,) * 3)
    for o in meshes:
        for c in o.bound_box:
            w = o.matrix_world @ Vector(c)
            for i in range(3):
                lo[i] = min(lo[i], w[i])
                hi[i] = max(hi[i], w[i])
    return lo, hi


def main():
    path = target_path()
    if not os.path.exists(path):
        raise SystemExit(f"donor not found: {path}")
    stem = os.path.splitext(os.path.basename(path))[0]
    out = os.path.join(RENDERS, f"donor-{stem}")
    os.makedirs(out, exist_ok=True)

    meshes = load(path)
    total = 0
    log(f"{os.path.basename(path)}  --  {len(meshes)} mesh object(s)")
    for o in meshes:
        o.data.calc_loop_triangles()
        t = len(o.data.loop_triangles)
        total += t
        log(f"   {o.name}: {len(o.data.vertices)} verts, {t} tris, "
            f"{len(o.data.materials)} material(s), {len(o.data.uv_layers)} uv layer(s)")
    log(f"   total {total} tris")

    lo, hi = bounds(meshes)
    size = hi - lo
    ctr = (lo + hi) / 2.0
    log(f"   bounds  x {lo.x:+.4f}..{hi.x:+.4f}   y {lo.y:+.4f}..{hi.y:+.4f}   z {lo.z:+.4f}..{hi.z:+.4f}")
    log(f"   size    {size.x:.4f} x {size.y:.4f} x {size.z:.4f}")
    axes = sorted(range(3), key=lambda i: size[i])
    thin, long_ = axes[0], axes[2]
    log(f"   thinnest axis = {'xyz'[thin]}  ->  relief faces {'xyz'[thin]}, "
        f"depth/length = {size[thin] / max(size[long_], 1e-9):.3f}")
    log(f"   longest axis  = {'xyz'[long_]}   aspect long/mid = "
        f"{size[long_] / max(size[axes[1]], 1e-9):.3f}")

    sc = bpy.context.scene
    sc.render.engine = "BLENDER_EEVEE"
    sc.render.resolution_x = RES
    sc.render.resolution_y = RES
    sc.render.image_settings.file_format = "PNG"

    w = bpy.data.worlds.new("W")
    sc.world = w
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs["Color"].default_value = (0.30, 0.30, 0.31, 1)
    w.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.35

    clay = bpy.data.materials.new("DONOR_CLAY")
    clay.use_nodes = True
    b = clay.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (0.85, 0.83, 0.78, 1)
    b.inputs["Roughness"].default_value = 0.80
    for o in meshes:
        o.data.materials.clear()
        o.data.materials.append(clay)

    cam_data = bpy.data.cameras.new("cam")
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = max(size) * 1.12
    cam = bpy.data.objects.new("cam", cam_data)
    sc.collection.objects.link(cam)
    sc.camera = cam

    key = bpy.data.lights.new("key", "SUN")
    key.energy = 3.8
    keyob = bpy.data.objects.new("key", key)
    sc.collection.objects.link(keyob)
    fill = bpy.data.lights.new("fill", "SUN")
    fill.energy = 1.1
    fillob = bpy.data.objects.new("fill", fill)
    sc.collection.objects.link(fillob)

    dist = max(size) * 3.0

    def shot(name, yaw_deg, pitch_deg, key_yaw=-140.0, key_pitch=55.0):
        yaw, pitch = math.radians(yaw_deg), math.radians(pitch_deg)
        cam.location = (ctr.x - dist * math.sin(yaw) * math.cos(pitch),
                        ctr.y + dist * math.cos(yaw) * math.cos(pitch),
                        ctr.z + dist * math.sin(pitch))
        cam.rotation_euler = (math.radians(90.0) - pitch, 0.0, yaw + math.pi)
        keyob.rotation_euler = (math.radians(key_pitch), 0.0, math.radians(key_yaw))
        fillob.rotation_euler = (math.radians(32.0), 0.0, math.radians(145.0))
        sc.render.filepath = os.path.join(out, name)
        bpy.ops.render.render(write_still=True)
        log("   WROTE", name)

    # all four sides plus top -- the donor's facing axis is not known in advance
    shot("front.png", 0, 0)
    shot("back.png", 180, 0)
    shot("right.png", 90, 0)
    shot("left.png", 270, 0)
    shot("top.png", 0, 89)
    shot("threequarter.png", 34, 18)


main()
