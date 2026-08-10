"""Replace the master temple's accumulated scene lighting with one clean rig.

Every chain script's render-check step (integrate_cornice_frieze_v1.py's
FRIEZE_KEY/FILL, propagate_cornice_frieze_ring.py's RINGKEY, an earlier
cornice-checkpoint pass's CORNICE_CHECKPOINT_KEY/FILL/RIM, plus Blender's own
default "Light" point lamp that was apparently never deleted from the very
first save of this project) all opened the previous checkpoint and added
their own light on top without removing the last stage's -- each script
follows the correct "never touch the input, save to a new file" rule, but
none of them clean up inherited lights, so seven lights end up stacked in the
final file, including a stock 1000W point lamp. That combination blows
every material out toward white in any render, which is why the cast-stone
greys (measured: 0.31/0.32/0.325 etc, legitimate stone tones, not the bug)
were reading as flat white.

This is the first script to edit the CHAIN OUTPUT (frieze-ring-v6) in place
rather than fork to a new checkpoint -- deliberate, because this file is the
project's designated master now, not an intermediate step in a chain that
something downstream re-derives.

Run:  blender --background --python scripts/fix_master_lighting.py
"""

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy                                                        # noqa: E402

from paths import RENDERS, chain_blend  # noqa: E402

MASTER = chain_blend("frieze-ring-v6")
OUT_RENDER = os.path.join(RENDERS, "master-lighting-check")


def log(*a):
    print("[fix-lighting]", *a)
    sys.stdout.flush()


def main():
    bpy.ops.wm.open_mainfile(filepath=MASTER)

    removed = []
    for ob in list(bpy.data.objects):
        if ob.type == "LIGHT":
            removed.append(ob.name)
            data = ob.data
            bpy.data.objects.remove(ob, do_unlink=True)
            if data.users == 0:
                bpy.data.lights.remove(data)
    log(f"removed {len(removed)} old lights: {removed}")

    sc = bpy.context.scene
    for e, p, y, name in ((3.2, 42.0, -35.0, "KEY"),
                           (1.6, 45.0, 35.0, "FILL"),
                           (0.9, 15.0, 180.0, "RIM")):
        li = bpy.data.lights.new(f"MASTER_{name}", "SUN")
        li.energy = e
        o = bpy.data.objects.new(f"MASTER_{name}", li)
        sc.collection.objects.link(o)
        o.rotation_euler = (math.radians(p), 0.0, math.radians(y))
    log("added MASTER_KEY/FILL/RIM sun rig (3.2 / 1.6 / 0.9)")

    if sc.world is None:
        sc.world = bpy.data.worlds.new("W")
    sc.world.use_nodes = True
    bg = sc.world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs["Color"].default_value = (0.55, 0.58, 0.62, 1.0)
        bg.inputs["Strength"].default_value = 0.6
    log("world background set to a neutral grey-blue, strength 0.6")

    bpy.ops.wm.save_as_mainfile(filepath=MASTER)
    log(f"SAVED {MASTER}")

    # --- render check ---
    from mathutils import Vector

    lo = Vector((1e18,) * 3)
    hi = Vector((-1e18,) * 3)
    for ob in bpy.data.objects:
        if ob.type == "MESH" and not ob.hide_render:
            for v in ob.bound_box:
                w = ob.matrix_world @ Vector(v)
                for i in range(3):
                    lo[i] = min(lo[i], w[i])
                    hi[i] = max(hi[i], w[i])
    ctr = (lo + hi) / 2.0
    diag = (hi - lo).length

    sc.render.engine = "BLENDER_EEVEE"
    sc.render.resolution_x = 1600
    sc.render.resolution_y = 1000
    sc.render.image_settings.file_format = "PNG"

    cam_data = bpy.data.cameras.new("cam")
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = diag * 1.0
    cam = bpy.data.objects.new("cam", cam_data)
    sc.collection.objects.link(cam)
    sc.camera = cam
    yaw, pitch = math.radians(25), math.radians(25)
    d = diag * 2.6
    cam.location = ctr + Vector((d * math.sin(yaw) * math.cos(pitch),
                                  d * math.cos(yaw) * math.cos(pitch),
                                  d * math.sin(pitch)))
    cam.rotation_euler = (ctr - cam.location).normalized().to_track_quat('-Z', 'Y').to_euler()

    os.makedirs(OUT_RENDER, exist_ok=True)
    sc.render.filepath = os.path.join(OUT_RENDER, "overview.png")
    bpy.ops.render.render(write_still=True)
    log("WROTE overview.png")


if __name__ == "__main__":
    main()
