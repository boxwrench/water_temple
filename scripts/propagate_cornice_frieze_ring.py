"""Propagate the approved single 36-degree frieze module to all ten positions.

Reuses integrate_cornice_frieze_v1.py's build (imported, not re-run standalone)
as the base module, then adds nine more linked-duplicate copies -- sharing the
same four mesh datablocks (lion, anthemion, scroll x2), never independent
copies, per the project's "linked duplicates" convention.

Important correction from the single-module review: that module included a
second, "closing" lion (LION_R) at its far edge just so the isolated module
could be visually judged with a lion on each side. Propagating the module
as-is would double up a lion at every seam (each copy's LION_R landing on
top of the next copy's LION_L). The repeatable unit is really just one lion
+ two scrolls + one anthemion (0 to 36 degrees, owning only the lion at its
own start); the ring closes naturally because copy 9's "next" position is
copy 0's own lion.

Never touches cornice-with-lion.blend or the single-module file directly:
opens the single-module file, immediately saves to a new ring file, and does
all edits there.

Run:  blender --background --python propagate_cornice_frieze_ring.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import math

import bpy
from mathutils import Vector

import integrate_cornice_frieze_v1 as base  # noqa: E402
from paths import chain_blend, chain_render  # noqa: E402

OUT_BLEND = chain_blend("frieze-ring")
OUT_RENDER = chain_render("cornice-frieze-ring")

N_REPEATS = 10

# The u-centers are NOT re-derived here. They are read back off the seated
# objects, which integrate_cornice_frieze_v1.seat_rigid() stamps as "u_center"
# and "r_target" when it places them. Recomputing them from the same constants
# looked equivalent and was not: the scroll's position now depends on a runtime
# measurement (its own length), so a formula here would silently drift from the
# module it is supposed to be repeating.


def log(*a):
    print("[frieze-ring]", *a)
    sys.stdout.flush()


def linked_dup(ob, name):
    new_ob = ob.copy()  # shares .data (mesh) with the source -- a true linked duplicate
    new_ob.name = name
    bpy.context.scene.collection.objects.link(new_ob)
    return new_ob


def main():
    os.makedirs(OUT_RENDER, exist_ok=True)

    bpy.ops.wm.open_mainfile(filepath=base.OUT_BLEND)
    bpy.ops.wm.save_as_mainfile(filepath=OUT_BLEND)

    lion_r = bpy.data.objects.get("LION_R")
    if lion_r is not None:
        data = lion_r.data
        bpy.data.objects.remove(lion_r, do_unlink=True)
        if data.users == 0:
            bpy.data.meshes.remove(data)
        log("removed redundant closing LION_R from the single-module build")

    lion_0 = bpy.data.objects["LION_L"]
    scroll_l_0 = bpy.data.objects["SCROLL_L"]
    anth_0 = bpy.data.objects["ANTHEMION_C"]
    scroll_r_0 = bpy.data.objects["SCROLL_R"]

    # Read each element's own seating back off it, before any of it is moved.
    seat = {}
    for ob in (lion_0, scroll_l_0, anth_0, scroll_r_0):
        if "u_center" not in ob:
            raise SystemExit(
                f"{ob.name} carries no 'u_center' -- rebuild the single module "
                f"with the current integrate_cornice_frieze_v1.py first")
        seat[ob.name] = (float(ob["u_center"]), float(ob["r_target"]))
        log(f"   {ob.name:12s} u={seat[ob.name][0]:.5f}  r={seat[ob.name][1]:.5f}")

    all_new = []
    for k in range(N_REPEATS):
        offset = k * base.MODULE_ARC
        if k == 0:
            lion, sl, an, sr = lion_0, scroll_l_0, anth_0, scroll_r_0
        else:
            lion = linked_dup(lion_0, f"LION_{k:02d}")
            sl = linked_dup(scroll_l_0, f"SCROLL_L_{k:02d}")
            an = linked_dup(anth_0, f"ANTHEMION_{k:02d}")
            sr = linked_dup(scroll_r_0, f"SCROLL_R_{k:02d}")

        for src, dst in ((lion_0, lion), (scroll_l_0, sl),
                         (anth_0, an), (scroll_r_0, sr)):
            base.seat_rigid(dst, seat[src.name][0] + offset, seat[src.name][1])
        all_new += [lion, sl, an, sr]

    log(f"propagated {N_REPEATS} repeats, {len(all_new)} objects "
        f"(4 shared mesh datablocks: {lion_0.data.name}, {scroll_l_0.data.name}, "
        f"{anth_0.data.name}, {scroll_r_0.data.name})")

    CY = base.CY
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_EEVEE"
    sc.render.resolution_x = 1400
    sc.render.resolution_y = 1000
    sc.render.image_settings.file_format = "PNG"
    w = bpy.data.worlds.get("W") or bpy.data.worlds.new("W")
    sc.world = w
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs["Color"].default_value = (0.55, 0.62, 0.72, 1)
    w.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.9

    cam_data = bpy.data.cameras.new("RINGCAM")
    cam = bpy.data.objects.new("RINGCAM", cam_data)
    sc.collection.objects.link(cam)
    sc.camera = cam
    cam.data.lens = 28
    key = bpy.data.lights.new("RINGKEY", "SUN")
    key.energy = 3.0
    keyob = bpy.data.objects.new("RINGKEY", key)
    sc.collection.objects.link(keyob)
    keyob.rotation_euler = (math.radians(55.0), 0.0, math.radians(35.0))

    center = Vector((0.0, CY, 0.36))
    for tag, dist, height, pitch_deg in [
        ("ring-overview.png", 1.05, 0.85, 22.0),
        ("ring-detail-angle.png", 0.55, 0.30, 10.0),
    ]:
        pitch = math.radians(pitch_deg)
        cam.location = center + Vector((0.0, -dist * math.cos(pitch), height))
        direction = (center - cam.location).normalized()
        cam.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
        sc.render.filepath = os.path.join(OUT_RENDER, tag)
        bpy.ops.render.render(write_still=True)
        log("WROTE", tag)

    bpy.ops.wm.save_as_mainfile(filepath=OUT_BLEND)
    log("SAVED", OUT_BLEND)


if __name__ == "__main__":
    main()
