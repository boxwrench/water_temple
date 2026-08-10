"""Build a smooth low-poly proxy base for normal-map baking.

Straight Collapse decimation of the capital's organic carved surface
produces a broken, spiky result even at mild ratios (build_capital_lod1.py,
confirmed via render, rejected). The fix is to decimate a SMOOTH,
uniformly-tessellated stand-in instead of the spiky organic source: a
coarse Voxel Remesh turns the deep acanthus/volute carving into a smooth
blob with bounded local curvature, which Collapse can then simplify
cleanly. This proxy is deliberately NOT detailed -- it exists only as a
bake target; scripts/bake_capital_normal.py bakes the real surface detail
from CAPITAL_MASTER_RENDER onto it as a normal map.

Remesh from CAPITAL_MASTER (v10, closed shell), not CAPITAL_MASTER_RENDER
(v11, interior-stripped -- open where the invisible backside was removed).
First attempt used v11 and produced a surface full of holes and cavities,
not just blur: a large open cut confuses Voxel Remesh's inside/outside test
the same way the original zero-thickness shell did before it was closed.
The proxy only needs the outer silhouette, which v10 has intact; the bake
step pulls detail from v11 separately.

Run:  blender --background --python scripts/build_capital_proxy.py
"""

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bmesh                                                      # noqa: E402
import bpy                                                        # noqa: E402
from mathutils import Vector                                      # noqa: E402

from paths import CAPITAL_MASTER, CAPITAL_MASTER_OBJECT, MASTERS, RENDERS  # noqa: E402

OUT_PATH = os.path.join(MASTERS, "corinthian-capital-proxy-lod1.blend")
OUT_RENDER = os.path.join(RENDERS, "capital-proxy-build")
PROXY_OBJECT = "CORINTHIAN_CAPITAL_PROXY_LOD1"

VOXEL_SIZE = 0.025
DECIMATE_RATIO = 0.15


def log(*a):
    print("[cap-proxy]", *a)
    sys.stdout.flush()


def main():
    bpy.ops.wm.open_mainfile(filepath=CAPITAL_MASTER)
    ob = bpy.data.objects[CAPITAL_MASTER_OBJECT]
    faces_before = len(ob.data.polygons)

    rem = ob.modifiers.new("Rem", "REMESH")
    rem.mode = "VOXEL"
    rem.voxel_size = VOXEL_SIZE
    rem.adaptivity = 0.0

    deps = bpy.context.evaluated_depsgraph_get()
    eval_ob = ob.evaluated_get(deps)
    bm = bmesh.new()
    bm.from_object(eval_ob, deps)
    remeshed_faces = len(bm.faces)
    me_remeshed = bpy.data.meshes.new("REMESHED")
    bm.to_mesh(me_remeshed)
    bm.free()
    log(f"voxel remesh {VOXEL_SIZE}: {faces_before} -> {remeshed_faces} faces")

    proxy_ob = bpy.data.objects.new(PROXY_OBJECT, me_remeshed)
    bpy.context.scene.collection.objects.link(proxy_ob)

    dec = proxy_ob.modifiers.new("Dec", "DECIMATE")
    dec.decimate_type = "COLLAPSE"
    dec.ratio = DECIMATE_RATIO
    deps2 = bpy.context.evaluated_depsgraph_get()
    eval_proxy = proxy_ob.evaluated_get(deps2)
    bm2 = bmesh.new()
    bm2.from_object(eval_proxy, deps2)
    me_final = bpy.data.meshes.new(PROXY_OBJECT)
    bm2.to_mesh(me_final)
    final_faces = len(bm2.faces)
    bm2.free()
    log(f"decimate ratio {DECIMATE_RATIO}: {remeshed_faces} -> {final_faces} faces")

    proxy_ob.modifiers.clear()
    proxy_ob.data = me_final

    for other in list(bpy.data.objects):
        if other is not proxy_ob:
            bpy.data.objects.remove(other, do_unlink=True)
    proxy_ob.name = PROXY_OBJECT
    proxy_ob.data.name = PROXY_OBJECT
    os.makedirs(MASTERS, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=OUT_PATH)
    log(f"SAVED {OUT_PATH}")

    # --- render for a quality check: smooth blob, no spikes ---
    lo = Vector((1e18,) * 3)
    hi = Vector((-1e18,) * 3)
    for v in proxy_ob.data.vertices:
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
    proxy_ob.data.materials.clear()
    proxy_ob.data.materials.append(clay)
    for p in proxy_ob.data.polygons:
        p.use_smooth = True

    cam_data = bpy.data.cameras.new("cam")
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = diag * 0.6
    cam = bpy.data.objects.new("cam", cam_data)
    sc.collection.objects.link(cam)
    sc.camera = cam

    for name, yaw, pitch in (("proxy_face.png", 0, 15), ("proxy_corner.png", 45, 15)):
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
