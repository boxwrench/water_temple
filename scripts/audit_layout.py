"""Where is everything, really? Spatial audit plus an auto-framed overview.

Every render so far has been aimed at the building. That framing hides anything
that is not in the building -- and 43,098 faces of superseded cornice masters
turned out to be sitting well outside it, visible only as a stray coil at the
edge of frame.

This does the opposite: it frames whatever exists, wherever it is, and lists
objects grouped by where they sit in the colonnade's polar frame. Read-only.

Run:  blender --background --python scripts/audit_layout.py -- <blend> [out-subdir]
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import math                                                       # noqa: E402

import bpy                                                        # noqa: E402
from mathutils import Vector                                      # noqa: E402

from paths import RENDERS, TEMPLE_MODEL, lod_blend                 # noqa: E402

CY = -0.5456366539001465
# The temple's own outermost geometry: the foundation course.
TEMPLE_R = 0.50
TEMPLE_Z = (-0.40, 0.40)


def log(*a):
    print("[layout]", *a)
    sys.stdout.flush()


def args():
    argv = sys.argv
    rest = argv[argv.index("--") + 1:] if "--" in argv else []
    blend = lod_blend("base") if not rest else (
        rest[0] if os.path.isabs(rest[0]) else os.path.join(TEMPLE_MODEL, rest[0]))
    out = os.path.join(RENDERS, rest[1] if len(rest) > 1 else "layout")
    return blend, out


def extents(ob):
    rs, zs = [], []
    lo = Vector((1e18,) * 3)
    hi = Vector((-1e18,) * 3)
    for v in ob.data.vertices:
        w = ob.matrix_world @ v.co
        rs.append(math.hypot(w.x, w.y - CY))
        zs.append(w.z)
        for i in range(3):
            lo[i] = min(lo[i], w[i])
            hi[i] = max(hi[i], w[i])
    return min(rs), max(rs), min(zs), max(zs), lo, hi


def main():
    blend, out = args()
    os.makedirs(out, exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=blend)
    log(f"{os.path.basename(blend)}")

    rows = []
    world_lo = Vector((1e18,) * 3)
    world_hi = Vector((-1e18,) * 3)
    for ob in bpy.data.objects:
        if ob.type != "MESH" or not ob.data.vertices:
            continue
        r0, r1, z0, z1, lo, hi = extents(ob)
        rows.append((r0, r1, z0, z1, len(ob.data.polygons), ob.name))
        for i in range(3):
            world_lo[i] = min(world_lo[i], lo[i])
            world_hi[i] = max(world_hi[i], hi[i])

    inside = [r for r in rows if r[1] <= TEMPLE_R
              and TEMPLE_Z[0] <= r[2] and r[3] <= TEMPLE_Z[1]]
    outside = [r for r in rows if r not in inside]

    log(f"{len(rows)} mesh objects, "
        f"{sum(r[4] for r in rows):,} faces total")
    log(f"world extent  x {world_lo.x:+.4f}..{world_hi.x:+.4f}  "
        f"y {world_lo.y:+.4f}..{world_hi.y:+.4f}  z {world_lo.z:+.4f}..{world_hi.z:+.4f}")
    log(f"the building itself occupies r <= {TEMPLE_R}, z {TEMPLE_Z}")
    log("")
    log(f"IN the building : {len(inside):4d} objects, {sum(r[4] for r in inside):9,d} faces")
    log(f"OUTSIDE it      : {len(outside):4d} objects, {sum(r[4] for r in outside):9,d} faces")

    if outside:
        log("")
        log(f"{'r_min':>8s} {'r_max':>8s} {'z_min':>8s} {'z_max':>8s} {'faces':>8s}  name")
        log("-" * 84)
        for r0, r1, z0, z1, f, n in sorted(outside, key=lambda r: -r[4]):
            log(f"{r0:8.4f} {r1:8.4f} {z0:+8.4f} {z1:+8.4f} {f:8,d}  {n[:40]}")

    # --- auto-framed overview: frame everything that exists ---
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_EEVEE"
    sc.render.resolution_x = 1500
    sc.render.resolution_y = 1000
    sc.render.image_settings.file_format = "PNG"

    w = bpy.data.worlds.get("W") or bpy.data.worlds.new("W")
    sc.world = w
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs["Color"].default_value = (0.30, 0.31, 0.34, 1)
    w.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.45

    for e, p, y in ((3.2, 45.0, -140.0), (1.1, 25.0, 40.0)):
        li = bpy.data.lights.new("s", "SUN")
        li.energy = e
        o = bpy.data.objects.new("s", li)
        sc.collection.objects.link(o)
        o.rotation_euler = (math.radians(p), 0.0, math.radians(y))

    ctr = (world_lo + world_hi) / 2.0
    size = (world_hi - world_lo).length
    cam_data = bpy.data.cameras.new("LAYOUT_CAM")
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = size * 1.05
    cam = bpy.data.objects.new("LAYOUT_CAM", cam_data)
    sc.collection.objects.link(cam)
    sc.camera = cam

    def shot(name, yaw, pitch):
        yaw, pitch = math.radians(yaw), math.radians(pitch)
        d = size * 3.0
        cam.location = ctr + Vector((-d * math.sin(yaw) * math.cos(pitch),
                                     d * math.cos(yaw) * math.cos(pitch),
                                     d * math.sin(pitch)))
        cam.rotation_euler = (ctr - cam.location).normalized().to_track_quat(
            '-Z', 'Y').to_euler()
        sc.render.filepath = os.path.join(out, name)
        bpy.ops.render.render(write_still=True)
        log("WROTE " + name)

    shot("everything-top.png", 0, 89)
    shot("everything-front.png", 0, 12)
    shot("everything-threequarter.png", 35, 30)


if __name__ == "__main__":
    main()
