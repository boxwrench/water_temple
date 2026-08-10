"""Render the central well head close up, from any temple .blend.

Fixed camera and lights supplied here rather than taken from the file, so any
two builds are directly comparable. A raking key is the point: the braid's
relief is 0.0022 and only reads through its shadow line.

Run:  blender --background --python scripts/render_well.py -- <blend> <out-subdir>
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import math                                                       # noqa: E402

import bpy                                                        # noqa: E402
from mathutils import Vector                                      # noqa: E402

from paths import RENDERS, TEMPLE_MODEL                           # noqa: E402

CY = -0.5456366539001465
FOCUS = Vector((0.0, CY, -0.2400))     # the well's upper half
RES_X, RES_Y = 1500, 950


def log(*a):
    print("[well-render]", *a)
    sys.stdout.flush()


def args():
    argv = sys.argv
    rest = argv[argv.index("--") + 1:] if "--" in argv else []
    if len(rest) < 2:
        raise SystemExit("usage: -- <blend> <out-subdir>")
    blend = rest[0] if os.path.isabs(rest[0]) else os.path.join(TEMPLE_MODEL, rest[0])
    return blend, os.path.join(RENDERS, rest[1])


def setup():
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_EEVEE"
    sc.render.resolution_x = RES_X
    sc.render.resolution_y = RES_Y
    sc.render.image_settings.file_format = "PNG"

    w = bpy.data.worlds.get("W") or bpy.data.worlds.new("W")
    sc.world = w
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs["Color"].default_value = (0.34, 0.35, 0.37, 1)
    w.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.45

    cam_data = bpy.data.cameras.new("WELL_CAM")
    cam = bpy.data.objects.new("WELL_CAM", cam_data)
    sc.collection.objects.link(cam)
    sc.camera = cam

    def sun(energy, pitch, yaw):
        li = bpy.data.lights.new("s", "SUN")
        li.energy = energy
        o = bpy.data.objects.new("s", li)
        sc.collection.objects.link(o)
        o.rotation_euler = (math.radians(pitch), 0.0, math.radians(yaw))
        return o

    # Low raking key: shallow relief needs a long shadow to read at all.
    sun(3.8, 22.0, -150.0)
    sun(1.0, 55.0, 30.0)
    return cam


def shot(cam, out, name, yaw_deg, pitch_deg, dist, lens, focus=None):
    ctr = FOCUS if focus is None else focus
    yaw, pitch = math.radians(yaw_deg), math.radians(pitch_deg)
    cam.data.type = "PERSP"
    cam.data.lens = lens
    cam.location = ctr + Vector((
        -dist * math.sin(yaw) * math.cos(pitch),
        dist * math.cos(yaw) * math.cos(pitch),
        dist * math.sin(pitch)))
    cam.rotation_euler = (ctr - cam.location).normalized().to_track_quat('-Z', 'Y').to_euler()
    bpy.context.scene.render.filepath = os.path.join(out, name)
    bpy.ops.render.render(write_still=True)
    log("WROTE", name)


def main():
    blend, out = args()
    os.makedirs(out, exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=blend)
    log(f"rendering {os.path.basename(blend)} -> {os.path.basename(out)}")

    cam = setup()
    # Yaw 18.5 puts the camera at theta ~108.5 deg, the centre of the bay
    # between columns 03 (90.19) and 04 (127.24). At yaw 0 it sits at theta 90
    # and looks straight through column 03.
    Y = 18.5
    shot(cam, out, "well-whole.png", Y, 24, 0.52, 55)
    shot(cam, out, "well-braid-closeup.png", Y, 7, 0.30, 110,
         focus=Vector((0.0, CY, -0.2300)))
    shot(cam, out, "well-cap-and-braid.png", Y, 26, 0.34, 78,
         focus=Vector((0.0, CY, -0.2230)))
    shot(cam, out, "well-from-above.png", Y, 54, 0.46, 55,
         focus=Vector((0.0, CY, -0.2180)))


if __name__ == "__main__":
    main()
