"""Thicken the drum wall inward so it covers the capitals below it.

Measured (see _inspect_drum.py / _inspect_drum2.py, run against the
propagated-ring milestone): the drum ("Inscription drum with 150-percent
inset quotation") is only 0.004 thick -- inner surface at r=0.282, outer
baseline at r=0.286 (with a third cluster at r=0.2835 for the inset
quotation text, between the two). Meanwhile the Corinthian capitals below
extend from r=0.206 to r=0.300 and the architrave band directly under the
drum spans r=0.203 to r=0.293 -- both far wider than the drum sitting on
top of them, so the capitals are not covered and read as sitting proud of
the wall above instead of holding it up.

Fix: push only the inner-surface vertex ring (the ~2304 vertices at
r~=0.282) inward to match the architrave/capital inner radius. The outer
surface and the inset-quotation surface (r~=0.2835 and r~=0.286) are left
completely untouched, so the carved text is not affected -- this is a pure
thickening, not a resculpt.

Never touches the milestone file: opens it, immediately saves to a new
working file, and edits there.

The object was later rebuilt plain and renamed "Plain drum wall"
(build_plain_drum.py, 2026-08-09) -- same measured radii, so this script's
logic and constants are unaffected, only the object name lookup below changed.

Run:  blender --background --python thicken_drum.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import math

import bpy

from paths import DRUM_INNER_R, chain_blend, chain_render  # noqa: E402

# Reads the propagated ring directly. The original run read the MILESTONE file
# (Pulgas-Water-Temple-MILESTONE-2026-08-08-frieze-ring-propagated.blend), which
# is a plain copy of that same ring kept as a user-requested rollback point --
# so this is equivalent, and it is the only form that works for a chain built
# with a different lion master, where no such milestone copy exists.
MILESTONE = chain_blend("frieze-ring")
OUT_BLEND = chain_blend("frieze-ring-thick-drum")
OUT_RENDER = chain_render("cornice-frieze-ring")

CY = -0.5456366539001465
INNER_SURFACE_R = 0.282     # measured drum inner-surface radius (the too-thin wall)

# The capitals' inner radius, and therefore a DERIVED value -- re-measure it with
# scripts/swap_corinthian_capitals.py (which prints it) whenever the capitals
# change. It was 0.204 for the procedural capitals; the Temple-of-Vesta master
# reaches further in, to 0.19725, because its plan is stretched ~14% to meet both
# the shaft below and the architrave above. Leaving 0.204 here would have left
# the new capitals' inner edge protruding 0.0068 beyond the wall above them --
# exactly the "capitals sitting proud of the wall" defect this script exists to
# fix.
#
# Lives in paths.py now, because fix_drum_wall_and_ring_seating.py and
# fix_top_shelf_and_embed_v3.py need the same number and each used to keep its
# own copy of it.
TARGET_INNER_R = DRUM_INNER_R
TOLERANCE = 0.001


def log(*a):
    print("[thicken-drum]", *a)
    sys.stdout.flush()


def main():
    os.makedirs(OUT_RENDER, exist_ok=True)

    bpy.ops.wm.open_mainfile(filepath=MILESTONE)
    bpy.ops.wm.save_as_mainfile(filepath=OUT_BLEND)

    drum = bpy.data.objects["Plain drum wall"]
    inv = drum.matrix_world.inverted()

    moved = 0
    for v in drum.data.vertices:
        w = drum.matrix_world @ v.co
        dx, dy = w.x - 0.0, w.y - CY
        r = math.hypot(dx, dy)
        if abs(r - INNER_SURFACE_R) < TOLERANCE:
            theta = math.atan2(dy, dx)
            new_w = (TARGET_INNER_R * math.cos(theta), CY + TARGET_INNER_R * math.sin(theta), w.z)
            v.co = inv @ __import__("mathutils").Vector(new_w)
            moved += 1
    drum.data.update()
    log(f"moved {moved} inner-surface vertices from r={INNER_SURFACE_R} to r={TARGET_INNER_R}")

    bpy.ops.wm.save_as_mainfile(filepath=OUT_BLEND)
    log("SAVED", OUT_BLEND)


if __name__ == "__main__":
    main()
