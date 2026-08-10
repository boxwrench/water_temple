"""Render one lion mask head-on, in situ, from any frieze .blend.

The module previews in integrate_cornice_frieze_v1.py frame the whole 36-degree
module from a fixed world angle, which means no single lion is ever seen square
on -- fine for judging the module's rhythm, useless for judging the mask itself.
This aims the camera radially outward from the lion at LION_ANGLE instead, so
the new master and the currently-approved one can be compared under an identical
camera and an identical light rig.

Read-only: opens a .blend, renders, never saves.

Run:  blender --background --python scripts/render_lion_compare.py -- <blend> <out-subdir> [lion-object]
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import math                                                     # noqa: E402

import bpy                                                      # noqa: E402
from mathutils import Vector                                    # noqa: E402

from paths import RENDERS, TEMPLE_MODEL                         # noqa: E402

CY = -0.5456366539001465
RMAP = 0.300
LION_ANGLE = math.atan2(0.0756035098, 0.2408188273)
SLOT_R_BACK = 0.2921
Z_BASELINE = 0.3172
LION_HEIGHT_REAL = 0.0498


def log(*a):
    print("[lion-compare]", *a)
    sys.stdout.flush()


def args():
    argv = sys.argv
    rest = argv[argv.index("--") + 1:] if "--" in argv else []
    if len(rest) < 2:
        raise SystemExit("usage: -- <blend> <out-subdir> [lion-object]")
    blend = rest[0] if os.path.isabs(rest[0]) else os.path.join(TEMPLE_MODEL, rest[0])
    return blend, os.path.join(RENDERS, rest[1]), (rest[2] if len(rest) > 2 else "LION_L")


def main():
    blend, out, lion_name = args()
    os.makedirs(out, exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=blend)

    lion = bpy.data.objects.get(lion_name)
    if lion is None:
        raise SystemExit(f"{lion_name} not found in {blend}")
    lion.data.calc_loop_triangles()
    log(f"{os.path.basename(blend)}  {lion_name}  "
        f"mesh={lion.data.name}  tris={len(lion.data.loop_triangles)}  "
        f"dims={tuple(round(c, 4) for c in lion.dimensions)}")

    # Aim point: the lion's own centre, on the cylinder at LION_ANGLE.
    focus = Vector((SLOT_R_BACK * math.cos(LION_ANGLE),
                    CY + SLOT_R_BACK * math.sin(LION_ANGLE),
                    Z_BASELINE + LION_HEIGHT_REAL * 0.5))
    radial = Vector((math.cos(LION_ANGLE), math.sin(LION_ANGLE), 0.0))
    tangent = Vector((-math.sin(LION_ANGLE), math.cos(LION_ANGLE), 0.0))

    sc = bpy.context.scene
    sc.render.engine = "BLENDER_EEVEE"
    sc.render.resolution_x = 1000
    sc.render.resolution_y = 1000
    sc.render.image_settings.file_format = "PNG"

    w = bpy.data.worlds.get("W") or bpy.data.worlds.new("W")
    sc.world = w
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs["Color"].default_value = (0.42, 0.46, 0.52, 1)
    w.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.55

    cam_data = bpy.data.cameras.new("LIONCAM")
    cam_data.lens = 85
    cam = bpy.data.objects.new("LIONCAM", cam_data)
    sc.collection.objects.link(cam)
    sc.camera = cam

    # Key pair straddling the lion's own radial axis, so neither the old nor the
    # new mask is flattered by an off-axis light. Sun rotation is world-space,
    # so the yaws are offsets from the lion's angle, not absolutes.
    lion_yaw = math.degrees(LION_ANGLE)
    for energy, pitch, yaw in [(3.2, 50.0, lion_yaw - 125.0),
                               (3.2, 50.0, lion_yaw - 55.0),
                               (1.0, 5.0, lion_yaw - 90.0)]:
        li = bpy.data.lights.new("LIONSUN", "SUN")
        li.energy = energy
        o = bpy.data.objects.new("LIONSUN", li)
        sc.collection.objects.link(o)
        o.rotation_euler = (math.radians(pitch), 0.0, math.radians(yaw))

    def shot(name, dist, swing_deg, pitch_deg):
        swing, pitch = math.radians(swing_deg), math.radians(pitch_deg)
        # Orbit the lion's own radial axis rather than the world axes, so
        # "straight on" means straight on to this mask, not to the temple.
        out_dir = (radial * math.cos(swing) + tangent * math.sin(swing))
        cam.location = focus + out_dir * (dist * math.cos(pitch)) + Vector((0, 0, dist * math.sin(pitch)))
        cam.rotation_euler = (focus - cam.location).normalized().to_track_quat('-Z', 'Y').to_euler()
        sc.render.filepath = os.path.join(out, name)
        bpy.ops.render.render(write_still=True)
        log("WROTE", name)

    shot("lion-headon.png", 0.20, 0, 0)
    shot("lion-threequarter.png", 0.20, 38, 6)
    shot("lion-frombelow.png", 0.20, 8, -30)
    shot("lion-context.png", 0.42, 14, 4)


if __name__ == "__main__":
    main()
