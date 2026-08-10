"""Replace the ten procedural Corinthian capitals with the new capital master.

This runs UPSTREAM of the frieze chain. The capitals live in the base temple
file, not in the chain, and `thicken_drum.py` derives the drum's inner radius
from the capital's inner radius -- so a capital swap invalidates the chain from
step 2 onwards and has to be done before it, not patched on afterwards.

Never touches CORNICE_WITH_LION: opens it, immediately saves to a new base file,
edits there. Point paths.CORNICE_WITH_LION at the output to rebuild the chain on
the new capitals.

Placement: measured, not assumed
--------------------------------
Each new capital inherits its position from the old one it replaces -- angle,
column-centre radius and seating height are all read off the outgoing capital's
own bottom band immediately before it is deleted. The ten columns are not
perfectly evenly spaced (measured gaps run 35.32 to 37.05 degrees), so
regenerating positions from an idealised 36-degree layout would visibly shift
them. Inheriting per column is what makes "ten-column radial alignment survives
the swap" true by construction rather than by hope.

The fit is deliberately non-uniform, and this is the one real judgement call
-------------------------------------------------------------------------------
The slot is bounded below by the shaft top and above by the architrave, both
protected geometry. Measured, that slot wants a bell-base-to-height ratio of
0.8198; the donor's is 0.7197. Uniform scaling can satisfy only one boundary:

  * fit by height      -> bell base 0.0595 against a 0.0667 shaft top: the column
                          oversails its own capital by 0.0072, which reads as a
                          mistake from any angle.
  * fit by bell base   -> height 0.0927, topping out at z 0.1843 and driving
                          0.0100 into the architrave above it.

So the plan and the height are scaled independently: k_z fills the slot exactly,
k_xy matches the outgoing capital's bell base exactly. Roughly a 14% horizontal
stretch. Capitals are routinely proportioned to their order, so this is an
ordinary architectural adaptation, and it is the only fit that leaves every
protected surface untouched.

Because the only rotation applied is about Z, a non-uniform (kx = ky, kz) scale
commutes with it and introduces no shear. That would NOT hold if the capitals
were tilted.

Run:  blender --background --python scripts/swap_corinthian_capitals.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import json                                                       # noqa: E402
import math                                                       # noqa: E402

import bpy                                                        # noqa: E402
from mathutils import Vector                                      # noqa: E402

from paths import (CAPITAL_MASTER, CAPITAL_MASTER_OBJECT,          # noqa: E402
                    CORNICE_WITH_LION, CORNICE_WITH_NEW_CAPITALS,
                    RENDERS)

CY = -0.5456366539001465
OLD_PREFIX = "Corinthian capital radial module"
NEW_NAME = "Corinthian capital radial module {:02d}"
OUT_RENDER = os.path.join(RENDERS, "capital-swap")

# Thickness of the band used to read a capital's bell base, in model units.
BASE_BAND = 0.004


def log(*a):
    print("[capital-swap]", *a)
    sys.stdout.flush()


def measure_old(ob):
    """Angle, column-centre radius, seating height and bell width of a capital.

    The bell base is read from a thin band at the object's bottom rather than
    from the bounding box: the box is dominated by the abacus, which is both
    wider and square, and would give a meaningless "width" for the round base
    that actually meets the shaft.
    """
    ws = [ob.matrix_world @ v.co for v in ob.data.vertices]
    z_lo = min(w.z for w in ws)
    z_hi = max(w.z for w in ws)
    base = [w for w in ws if w.z <= z_lo + BASE_BAND]

    # Column axis: centre of the bell base in plan, which is a circle, so the
    # mean of its extremes is its centre.
    bx = (max(w.x for w in base) + min(w.x for w in base)) / 2.0
    by = (max(w.y for w in base) + min(w.y for w in base)) / 2.0
    theta = math.atan2(by - CY, bx - 0.0)
    radius = math.hypot(bx - 0.0, by - CY)

    # Bell diameter measured across the base circle.
    bell = max(2.0 * math.hypot(w.x - bx, w.y - by) for w in base)

    # Radial extent of the whole capital, for the TARGET_INNER_R report.
    rs = [math.hypot(w.x, w.y - CY) for w in ws]

    return {
        "name": ob.name, "theta": theta, "radius": radius,
        "z_lo": z_lo, "z_hi": z_hi, "height": z_hi - z_lo,
        "bell": bell, "r_min": min(rs), "r_max": max(rs),
        # Inherit the material along with the position. A master arrives with no
        # material and would otherwise render at Blender's default near-white,
        # which reads as a lighting or geometry fault rather than as the missing
        # material it actually is.
        "materials": [s.material for s in ob.material_slots if s.material],
    }


def append_master(new_name):
    with bpy.data.libraries.load(CAPITAL_MASTER, link=False) as (src, dst):
        dst.objects = [CAPITAL_MASTER_OBJECT]
    ob = bpy.data.objects[CAPITAL_MASTER_OBJECT]
    ob.name = new_name
    bpy.context.scene.collection.objects.link(ob)
    # Appended objects arrive in QUATERNION mode, where assigning rotation_euler
    # is a silent no-op. This has bitten this project before.
    ob.rotation_mode = "XYZ"
    return ob


def radial_extent(ob):
    lo, hi = 1e9, -1e9
    for v in ob.data.vertices:
        w = ob.matrix_world @ v.co
        r = math.hypot(w.x, w.y - CY)
        lo = min(lo, r)
        hi = max(hi, r)
    return lo, hi


def main():
    os.makedirs(OUT_RENDER, exist_ok=True)

    bpy.ops.wm.open_mainfile(filepath=CORNICE_WITH_LION)
    bpy.ops.wm.save_as_mainfile(filepath=CORNICE_WITH_NEW_CAPITALS)

    old = [o for o in bpy.data.objects
           if o.type == "MESH" and o.name.startswith(OLD_PREFIX)]
    if len(old) != 10:
        raise SystemExit(f"expected 10 capitals, found {len(old)}")
    old.sort(key=lambda o: o.name)

    slots = [measure_old(o) for o in old]
    log(f"{'old capital':>34s} {'theta':>9s} {'radius':>8s} {'z_lo':>8s} "
        f"{'height':>8s} {'bell':>8s} {'r_min':>8s} {'r_max':>8s}")
    for s in slots:
        log(f"{s['name'][-34:]:>34s} {math.degrees(s['theta']):9.3f} "
            f"{s['radius']:8.5f} {s['z_lo']:8.5f} {s['height']:8.5f} "
            f"{s['bell']:8.5f} {s['r_min']:8.5f} {s['r_max']:8.5f}")

    old_r_min = min(s["r_min"] for s in slots)
    old_r_max = max(s["r_max"] for s in slots)
    log(f"outgoing capitals: radial {old_r_min:.5f}..{old_r_max:.5f}")

    # Master metadata, stamped by build_capital_master.py in its unit-height frame.
    probe = append_master("CAPITAL_PROBE")
    bell_u = float(probe["bell_base_width"])
    abacus_u = float(probe["abacus_width"])
    log(f"master (unit height): bell {bell_u:.5f}  abacus {abacus_u:.5f}  "
        f"abacus/bell {abacus_u / bell_u:.4f}")
    master_mesh = probe.data
    bpy.data.objects.remove(probe, do_unlink=True)

    # All ten capitals share this one mesh datablock, so the material goes on
    # the mesh once rather than per object.
    inherited = slots[0]["materials"]
    master_mesh.materials.clear()
    for m in inherited:
        master_mesh.materials.append(m)
    log(f"material inherited from the outgoing capitals: "
        f"{[m.name for m in inherited] or '<none found>'}")

    placed = []
    for i, s in enumerate(slots, start=1):
        # Delete the outgoing capital only after its slot has been measured.
        ob_old = bpy.data.objects[s["name"]]
        data_old = ob_old.data
        bpy.data.objects.remove(ob_old, do_unlink=True)
        if data_old.users == 0:
            bpy.data.meshes.remove(data_old)

        ob = bpy.data.objects.new(NEW_NAME.format(i), master_mesh)
        bpy.context.scene.collection.objects.link(ob)
        ob.rotation_mode = "XYZ"

        k_z = s["height"]                 # master is unit height
        k_xy = s["bell"] / bell_u         # bell base matches the outgoing one
        ob.scale = (k_xy, k_xy, k_z)
        # +X of the master is an abacus face; rotating by theta points it
        # radially outward, which is how the old modules were oriented.
        ob.rotation_euler = (0.0, 0.0, s["theta"])
        ob.location = (s["radius"] * math.cos(s["theta"]),
                       CY + s["radius"] * math.sin(s["theta"]),
                       s["z_lo"])
        bpy.context.view_layer.update()

        r_lo, r_hi = radial_extent(ob)
        placed.append({"name": ob.name, "k_xy": k_xy, "k_z": k_z,
                       "stretch": k_xy / k_z,
                       "theta_deg": math.degrees(s["theta"]),
                       "r_min": r_lo, "r_max": r_hi,
                       "z_lo": s["z_lo"], "z_hi": s["z_lo"] + k_z})
        ob["cornice_master_component"] = True

    log("")
    log(f"{'new capital':>34s} {'k_xy':>9s} {'k_z':>9s} {'stretch':>8s} "
        f"{'r_min':>8s} {'r_max':>8s} {'z_hi':>8s}")
    for p in placed:
        log(f"{p['name'][-34:]:>34s} {p['k_xy']:9.6f} {p['k_z']:9.6f} "
            f"{p['stretch']:8.4f} {p['r_min']:8.5f} {p['r_max']:8.5f} "
            f"{p['z_hi']:8.5f}")

    new_r_min = min(p["r_min"] for p in placed)
    new_r_max = max(p["r_max"] for p in placed)
    new_z_hi = max(p["z_hi"] for p in placed)

    # The whole point of doing this before the chain: thicken_drum.py's
    # TARGET_INNER_R is the capital's inner radius and must be re-derived here.
    log("")
    log(f"incoming capitals: radial {new_r_min:.5f}..{new_r_max:.5f}  "
        f"top z {new_z_hi:.5f}")
    log(f"  vs outgoing:     radial {old_r_min:.5f}..{old_r_max:.5f}")
    log("")
    log(f"==> TARGET_INNER_R for thicken_drum.py: {new_r_min:.4f}  "
        f"(was 0.204, derived from the old capitals' {old_r_min:.4f})")

    # Clearance checks against the two protected neighbours.
    arch = bpy.data.objects.get("Continuous lower entablature architrave")
    if arch:
        a_lo, a_hi = radial_extent(arch)
        az = [(arch.matrix_world @ v.co).z for v in arch.data.vertices]
        log(f"architrave: radial {a_lo:.5f}..{a_hi:.5f}  z {min(az):.5f}..{max(az):.5f}")
        log(f"  capital top {new_z_hi:.5f} vs architrave bottom {min(az):.5f}  "
            f"-> clearance {min(az) - new_z_hi:+.5f}")

    shaft = bpy.data.objects.get("Ten deep-fluted shaft overlays")
    if shaft:
        sz = [(shaft.matrix_world @ v.co).z for v in shaft.data.vertices]
        log(f"shaft top z {max(sz):.5f} vs capital bottom "
            f"{min(p['z_lo'] for p in placed):.5f}  -> overlap "
            f"{max(sz) - min(p['z_lo'] for p in placed):+.5f}")

    bpy.ops.wm.save_as_mainfile(filepath=CORNICE_WITH_NEW_CAPITALS)
    log("SAVED", CORNICE_WITH_NEW_CAPITALS)

    with open(os.path.join(OUT_RENDER, "swap_report.json"), "w") as f:
        json.dump({"out": CORNICE_WITH_NEW_CAPITALS,
                   "master": CAPITAL_MASTER,
                   # Materials are Blender IDs, not JSON -- record their names.
                   "old_slots": [{k: ([m.name for m in v] if k == "materials" else v)
                                  for k, v in s.items()} for s in slots],
                   "placed": placed,
                   "target_inner_r": new_r_min,
                   "old_target_inner_r": old_r_min}, f, indent=2)


if __name__ == "__main__":
    main()
