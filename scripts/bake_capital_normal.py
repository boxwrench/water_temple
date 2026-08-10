"""Bake the capital's real surface detail onto the low-poly proxy as a normal map.

corinthian-capital-proxy-lod1.blend (3,842 faces, boundary 0, non-manifold 0 --
confirmed closed and valid, not broken; its rough clay-shaded look is real
negative space at the volute eyes and leaf crown, not a defect) is the bake
target. CAPITAL_MASTER_RENDER (v11, 152,249 faces, interior already stripped)
is the detail source.

Run:  blender --background --python scripts/bake_capital_normal.py
"""

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bmesh                                                      # noqa: E402
import bpy                                                        # noqa: E402
from mathutils import Vector                                      # noqa: E402

from paths import CAPITAL_MASTER_OBJECT, CAPITAL_MASTER_RENDER, MASTERS, RENDERS  # noqa: E402

PROXY_PATH = os.path.join(MASTERS, "corinthian-capital-proxy-lod1.blend")
PROXY_OBJECT = "CORINTHIAN_CAPITAL_PROXY_LOD1"
OUT_PATH = os.path.join(MASTERS, "corinthian-capital-lod1-baked.blend")
OUT_RENDER = os.path.join(RENDERS, "capital-lod1-bake")
IMG_SIZE = 2048
CAGE_EXTRUSION = 0.08  # relative to capital diag ~1.95 -- generous enough to
# reach the true surface across the proxy's own decimation deviation


def log(*a):
    print("[cap-bake]", *a)
    sys.stdout.flush()


def main():
    # Load the proxy as the base scene, then append the high-detail object
    # into it so both exist together for the selected-to-active bake.
    bpy.ops.wm.open_mainfile(filepath=PROXY_PATH)
    low = bpy.data.objects[PROXY_OBJECT]

    with bpy.data.libraries.load(CAPITAL_MASTER_RENDER, link=False) as (data_from, data_to):
        data_to.objects = [CAPITAL_MASTER_OBJECT]
    high = None
    for ob in data_to.objects:
        if ob is not None:
            bpy.context.scene.collection.objects.link(ob)
            high = ob
    if high is None:
        raise RuntimeError("failed to append high-poly source object")
    log(f"low {len(low.data.polygons)} faces, high {len(high.data.polygons)} faces")

    # --- UV unwrap the proxy (smart project handles an irregular blob shape
    # without manual seams) ---
    bpy.context.view_layer.objects.active = low
    bpy.ops.object.select_all(action="DESELECT")
    low.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.02)
    bpy.ops.object.mode_set(mode="OBJECT")
    log(f"UV unwrapped: {len(low.data.uv_layers)} UV layer(s)")

    # --- image + material set up for baking ---
    img = bpy.data.images.new("capital_lod1_normal", IMG_SIZE, IMG_SIZE, alpha=False)
    img.colorspace_settings.name = "Non-Color"
    # fill with the flat-normal baseline (128,128,255) so any unbaked texel
    # (UV gaps) reads as "no change" instead of black
    img.generated_color = (0.5, 0.5, 1.0, 1.0)

    mat = bpy.data.materials.new("capital_lod1_mat")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    tex_node = nt.nodes.new("ShaderNodeTexImage")
    tex_node.image = img
    tex_node.select = True
    nt.nodes.active = tex_node

    normal_map_node = nt.nodes.new("ShaderNodeNormalMap")
    nt.links.new(tex_node.outputs["Color"], normal_map_node.inputs["Color"])
    nt.links.new(normal_map_node.outputs["Normal"], bsdf.inputs["Normal"])

    low.data.materials.clear()
    low.data.materials.append(mat)

    # --- bake (selected-to-active requires Cycles) ---
    sc = bpy.context.scene
    prev_engine = sc.render.engine
    sc.render.engine = "CYCLES"
    sc.cycles.samples = 32
    sc.render.bake.use_selected_to_active = True
    sc.render.bake.cage_extrusion = CAGE_EXTRUSION
    sc.render.bake.margin = 8

    bpy.ops.object.select_all(action="DESELECT")
    high.select_set(True)
    low.select_set(True)
    bpy.context.view_layer.objects.active = low

    log("baking normal map (selected-to-active, Cycles)...")
    bpy.ops.object.bake(type="NORMAL", use_selected_to_active=True,
                         cage_extrusion=CAGE_EXTRUSION, margin=8)
    log("bake complete")

    img_path = os.path.join(MASTERS, "corinthian-capital-lod1-normal.png")
    img.filepath_raw = img_path
    img.file_format = "PNG"
    img.save()
    log(f"SAVED {img_path}")

    sc.render.engine = prev_engine

    # --- remove the high-poly object, keep only the baked low-poly ---
    bpy.data.objects.remove(high, do_unlink=True)
    os.makedirs(MASTERS, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=OUT_PATH)
    log(f"SAVED {OUT_PATH}")

    # --- render the baked low-poly with EEVEE for a visual check ---
    lo = Vector((1e18,) * 3)
    hi = Vector((-1e18,) * 3)
    for v in low.data.vertices:
        for i in range(3):
            lo[i] = min(lo[i], v.co[i])
            hi[i] = max(hi[i], v.co[i])
    ctr = (lo + hi) / 2.0
    diag = (hi - lo).length

    os.makedirs(OUT_RENDER, exist_ok=True)
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

    for p in low.data.polygons:
        p.use_smooth = True

    cam_data = bpy.data.cameras.new("cam")
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = diag * 0.55
    cam = bpy.data.objects.new("cam", cam_data)
    sc.collection.objects.link(cam)
    sc.camera = cam

    for name, yaw, pitch in (("baked_face.png", 0, 15), ("baked_corner.png", 45, 15)):
        yaw_r, pitch_r = math.radians(yaw), math.radians(pitch)
        d = diag * 2.2
        cam.location = ctr + Vector((-d * math.sin(yaw_r) * math.cos(pitch_r),
                                     d * math.cos(yaw_r) * math.cos(pitch_r),
                                     d * math.sin(pitch_r)))
        cam.rotation_euler = (ctr - cam.location).normalized().to_track_quat('-Z', 'Y').to_euler()
        sc.render.filepath = os.path.join(OUT_RENDER, name)
        bpy.ops.render.render(write_still=True)
        log("WROTE " + name)


if __name__ == "__main__":
    main()
