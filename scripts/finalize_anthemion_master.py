"""Turn the supplied result.glb into the approved anthemion master.

Deliberately minimal: sizing, orientation, and triangle reduction only. The
sculpted form is kept exactly as supplied -- no symmetry mirroring, no aspect
correction, no re-cutting of the back plane. Those were offered and declined;
the look is approved as-is.

Output convention matches the trace spec
(docs/superpowers/specs/2026-08-07-anthemion-trace-design.md):
  x horizontal, y depth (0 at the back plane, +y toward the viewer), z up,
  half-width = 1.0. Scaling into the cornice module happens once, at transfer.

Run:  blender --background --python finalize_anthemion_master.py
"""


import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import math
import os
import sys

import bpy
from mathutils import Vector

from paths import ANTHEMION_MASTER as OUT_BLEND, RENDERS  # noqa: E402

# the donor lives outside the project; it is read, never written
SRC = r"C:\Users\wests\Downloads\result.glb"
OUT_RENDER = os.path.join(RENDERS, "anthemion-master")

NAME = "ANTHEMION_PLAQUE_MASTER"
TARGET_TRIS = 80000
SWEEP = (160000, 80000, 40000)   # front-view comparison so the level can be judged
RES = 850


def log(*a):
    print("[master]", *a)
    sys.stdout.flush()


def clear():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)


def world_bounds(ob):
    lo = Vector((1e9, 1e9, 1e9))
    hi = Vector((-1e9, -1e9, -1e9))
    for c in ob.bound_box:
        w = ob.matrix_world @ Vector(c)
        for i in range(3):
            lo[i] = min(lo[i], w[i])
            hi[i] = max(hi[i], w[i])
    return lo, hi


def apply_transforms(ob):
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    ob.select_set(False)


def tri_count(ob):
    ob.data.calc_loop_triangles()
    return len(ob.data.loop_triangles)


def import_donor():
    clear()
    bpy.ops.import_scene.gltf(filepath=SRC)
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    if len(meshes) > 1:
        bpy.context.view_layer.objects.active = meshes[0]
        for o in meshes:
            o.select_set(True)
        bpy.ops.object.join()
        meshes = [bpy.context.view_layer.objects.active]
    ob = meshes[0]
    ob.name = NAME
    ob.data.name = NAME + "_mesh"
    log(f"imported {tri_count(ob)} tris")
    return ob


def orient_and_size(ob):
    """Face the plaque along +y, put its back plane at y=0, half-width = 1.0.

    The donor arrives with its face in the Y-Z plane and +X pointing out of the
    relief, so a +90 degree turn about Z carries +X to +Y and leaves Z up.
    """
    ob.rotation_mode = "XYZ"          # GLB import can leave this QUATERNION, in
    ob.rotation_euler = (0, 0, math.radians(90.0))   # which case euler assignment
    apply_transforms(ob)                              # silently does nothing

    lo, hi = world_bounds(ob)
    size = hi - lo
    log(f"after rotate  size {size.x:.4f} x {size.y:.4f} x {size.z:.4f}")

    k = 2.0 / size.x                  # width 2.0  ->  half-width 1.0
    ob.scale = (k, k, k)
    apply_transforms(ob)

    lo, hi = world_bounds(ob)
    ob.location = (-(lo.x + hi.x) / 2.0, -lo.y, -(lo.z + hi.z) / 2.0)
    apply_transforms(ob)

    lo, hi = world_bounds(ob)
    size = hi - lo
    log(f"normalised    size {size.x:.4f} x {size.y:.4f} x {size.z:.4f}")
    log(f"              x {lo.x:+.4f}..{hi.x:+.4f}  y {lo.y:+.4f}..{hi.y:+.4f}  z {lo.z:+.4f}..{hi.z:+.4f}")
    log(f"              aspect h/w = {size.z / size.x:.4f}   relief depth/width = {size.y / size.x:.4f}")
    return ob


def decimate(ob, target):
    n = tri_count(ob)
    if target >= n:
        return n
    m = ob.modifiers.new("decimate", "DECIMATE")
    m.decimate_type = "COLLAPSE"
    m.ratio = target / n
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.modifier_apply(modifier=m.name)
    return tri_count(ob)


def record_provenance(ob):
    ob["source_file"] = "result.glb"
    ob["source_tool"] = "Tripo (image-to-3D)"
    ob["source_reference"] = "ChatGPT Image Aug 7, 2026, 09_02_35 AM.png"
    ob["date_acquired"] = "2026-08-07"
    ob["modifications"] = ("oriented +y front, back plane to y=0, uniform scale to "
                           f"half-width 1.0, decimated to ~{TARGET_TRIS} tris. "
                           "Form otherwise unmodified.")


def setup_render(size_hint):
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

    cam_data = bpy.data.cameras.new("cam")
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = size_hint * 1.18
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
    fillob.rotation_euler = (math.radians(32.0), 0.0, math.radians(145.0))
    return cam, keyob


def shot(cam, keyob, path, yaw_deg, pitch_deg, dist, key_yaw=-140.0, key_pitch=55.0):
    """Camera orbits on the +y side, since the plaque faces +y.

    A sun's beam travels along Rz(yaw)*Rx(pitch)*(0,0,-1), so lighting it from
    the viewer's side needs |key_yaw| > 90 -- the intuitive -38 puts the key
    behind the relief and lights the back.
    """
    yaw = math.radians(yaw_deg)
    pitch = math.radians(pitch_deg)
    cam.location = (-dist * math.sin(yaw) * math.cos(pitch),
                    dist * math.cos(yaw) * math.cos(pitch),
                    dist * math.sin(pitch))
    cam.rotation_euler = (math.radians(90.0) - pitch, 0.0, yaw + math.pi)
    keyob.rotation_euler = (math.radians(key_pitch), 0.0, math.radians(key_yaw))
    bpy.context.scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    log("WROTE", os.path.basename(path))


def clay(ob):
    ob.data.materials.clear()
    m = bpy.data.materials.new("PLAQUE_CLAY")
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (0.85, 0.83, 0.78, 1)
    b.inputs["Roughness"].default_value = 0.80
    ob.data.materials.append(m)


def main():
    os.makedirs(OUT_RENDER, exist_ok=True)

    # --- decimation sweep: same view at each level, so the level is a judgement
    #     call on evidence rather than a guess ---
    for target in SWEEP:
        ob = orient_and_size(import_donor())
        got = decimate(ob, target)
        clay(ob)
        _, hi = world_bounds(ob)
        cam, keyob = setup_render(hi.z * 2.2)
        shot(cam, keyob, os.path.join(OUT_RENDER, f"sweep-{target}.png"), 0, 0, 6.0)
        log(f"sweep {target} -> {got} tris")

    # --- the master ---
    ob = orient_and_size(import_donor())
    got = decimate(ob, TARGET_TRIS)
    log(f"master decimated to {got} tris")
    record_provenance(ob)

    lo, hi = world_bounds(ob)
    clay(ob)
    cam, keyob = setup_render(hi.z * 2.2)
    shot(cam, keyob, os.path.join(OUT_RENDER, "master-front.png"), 0, 0, 6.0)
    shot(cam, keyob, os.path.join(OUT_RENDER, "master-threequarter.png"), 34, 16, 6.0)
    shot(cam, keyob, os.path.join(OUT_RENDER, "master-frombelow.png"), 0, -26, 6.0)
    shot(cam, keyob, os.path.join(OUT_RENDER, "master-raking.png"), 0, 0, 6.0,
         key_yaw=-150.0, key_pitch=7.0)

    for o in list(bpy.data.objects):
        if o.type in {"CAMERA", "LIGHT"}:
            bpy.data.objects.remove(o, do_unlink=True)

    bpy.ops.wm.save_as_mainfile(filepath=OUT_BLEND)
    log("SAVED", OUT_BLEND)


main()
