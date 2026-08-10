"""Render the colonnade from any temple .blend at a fixed camera.

Run it against the old base and the new one and the two sets are directly
comparable: same camera, same lights, same framing, so the only difference in
the images is the capitals themselves. A "before" and an "after" shot taken at
whatever camera each happened to have is not evidence of anything.

Run:  blender --background --python scripts/render_capital_compare.py -- <blend> <out-subdir>
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import math                                                       # noqa: E402

import bpy                                                        # noqa: E402
from mathutils import Vector                                      # noqa: E402

from paths import RENDERS, TEMPLE_MODEL                           # noqa: E402

CY = -0.5456366539001465
# Centre of the capital band: the colonnade axis at the capitals' mid-height.
FOCUS = Vector((0.0, CY, 0.1330))
RES_X, RES_Y = 1400, 1000


def log(*a):
    print("[cap-render]", *a)
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
    w.node_tree.nodes["Background"].inputs["Color"].default_value = (0.32, 0.33, 0.36, 1)
    w.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.40

    cam_data = bpy.data.cameras.new("CAP_CAM")
    cam = bpy.data.objects.new("CAP_CAM", cam_data)
    sc.collection.objects.link(cam)
    sc.camera = cam

    def sun(energy, pitch, yaw):
        li = bpy.data.lights.new("s", "SUN")
        li.energy = energy
        o = bpy.data.objects.new("s", li)
        sc.collection.objects.link(o)
        o.rotation_euler = (math.radians(pitch), 0.0, math.radians(yaw))
        return o

    sun(3.4, 48.0, -140.0)
    sun(1.2, 30.0, 40.0)
    return cam


def shot(cam, out, name, yaw_deg, pitch_deg, dist, lens=70):
    yaw, pitch = math.radians(yaw_deg), math.radians(pitch_deg)
    cam.data.type = "PERSP"
    cam.data.lens = lens
    cam.location = FOCUS + Vector((
        -dist * math.sin(yaw) * math.cos(pitch),
        dist * math.cos(yaw) * math.cos(pitch),
        dist * math.sin(pitch)))
    cam.rotation_euler = (FOCUS - cam.location).normalized().to_track_quat('-Z', 'Y').to_euler()
    bpy.context.scene.render.filepath = os.path.join(out, name)
    bpy.ops.render.render(write_still=True)
    log("WROTE", name)


def main():
    blend, out = args()
    os.makedirs(out, exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=blend)
    log(f"rendering {os.path.basename(blend)} -> {os.path.basename(out)}")

    cam = setup()
    shot(cam, out, "colonnade-wide.png", 0, 6, 1.35, lens=50)
    shot(cam, out, "capital-closeup.png", 0, 4, 0.42, lens=85)
    shot(cam, out, "capital-threequarter.png", 22, 14, 0.46, lens=85)
    shot(cam, out, "capital-frombelow.png", 0, -18, 0.48, lens=85)


if __name__ == "__main__":
    main()
