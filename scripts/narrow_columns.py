"""Narrow the whole column -- shaft, capital and base -- to a fraction of its
current width, at unchanged height and unchanged position.

Requested after comparing against the real temple: the columns read a little
thick. This scales each column horizontally about its own vertical axis, so:

  * heights are untouched (z is never scaled),
  * the ten column axes do not move, so the radial alignment survives,
  * the colonnade radius is unchanged -- the columns get thinner in place rather
    than closing up or spreading out.

Two mechanisms, because the data is shared two different ways
-------------------------------------------------------------
The ten capitals are ten objects sharing ONE mesh datablock -- that is what makes
them cheap. Narrowing them therefore has to go through each object's `scale`; a
mesh edit would apply the same change ten times to the same geometry.

The ten shafts are the mirror image: one object containing all ten, so there is
no per-object scale to use and each vertex has to be assigned to its nearest
column axis and scaled about that.

Same visual operation, opposite implementations, decided purely by how the data
happens to be shared. Objects whose mesh has exactly one user are edited
per-vertex; anything shared falls back to object scale.

Column axes are read off the capitals' bell bases (a circle, so the mean of its
extremes is its centre) rather than assumed from an ideal layout: the measured
colonnade is not perfectly regular -- axis radii run 0.2477 to 0.2574 and bay
angles 35.3 to 37.1 degrees -- and regenerating it would visibly move things.

Prints the new capital inner radius, which is what thicken_drum.py's
TARGET_INNER_R has to be set to.

Run:  blender --background --python scripts/narrow_columns.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import json                                                       # noqa: E402
import math                                                       # noqa: E402

import bpy                                                        # noqa: E402
from mathutils import Matrix, Vector                              # noqa: E402

from paths import (CORNICE_WITH_NEW_CAPITALS,                      # noqa: E402
                    CORNICE_COLUMNS_NARROWED, RENDERS)

CY = -0.5456366539001465

# Requested: 90% of current width, same height.
NARROW = 0.90

CAPITAL_PREFIX = "Corinthian capital radial module"
BASE_PREFIX = "Molded column base radial module"
SHAFT_NAME = "Ten deep-fluted shaft overlays"
BASE_BAND = 0.004

OUT_RENDER = os.path.join(RENDERS, "columns-narrowed")


def log(*a):
    print("[narrow]", *a)
    sys.stdout.flush()


def column_axes():
    """The ten column axes, as (x, y) in world space, from the capitals' bases."""
    caps = sorted([o for o in bpy.data.objects
                   if o.type == "MESH" and o.name.startswith(CAPITAL_PREFIX)],
                  key=lambda o: o.name)
    axes = []
    for ob in caps:
        ws = [ob.matrix_world @ v.co for v in ob.data.vertices]
        z_lo = min(w.z for w in ws)
        base = [w for w in ws if w.z <= z_lo + BASE_BAND]
        ax = (max(w.x for w in base) + min(w.x for w in base)) / 2.0
        ay = (max(w.y for w in base) + min(w.y for w in base)) / 2.0
        axes.append((ax, ay))
    return caps, axes


def nearest_axis(x, y, axes):
    best, bd = 0, 1e18
    for i, (ax, ay) in enumerate(axes):
        d = (x - ax) ** 2 + (y - ay) ** 2
        if d < bd:
            best, bd = i, d
    return best


def radial_extent(ob):
    lo, hi = 1e9, -1e9
    for v in ob.data.vertices:
        w = ob.matrix_world @ v.co
        r = math.hypot(w.x, w.y - CY)
        lo = min(lo, r)
        hi = max(hi, r)
    return lo, hi


def narrow_by_vertex(ob, axes, k):
    """Scale each vertex horizontally about its own column's axis.

    For the shaft object only: it holds all ten shafts in one mesh, so the
    narrowing genuinely differs per vertex and no single object transform can
    express it. Requires an unshared mesh, or the edit would land more than once.
    """
    if ob.data.users != 1:
        raise SystemExit(f"{ob.name}: mesh shared by {ob.data.users} objects -- "
                         f"a per-vertex edit would apply it more than once")
    mw = ob.matrix_world
    inv = mw.inverted()
    counts = [0] * len(axes)
    for v in ob.data.vertices:
        w = mw @ v.co
        i = nearest_axis(w.x, w.y, axes)
        ax, ay = axes[i]
        v.co = inv @ Vector((ax + (w.x - ax) * k, ay + (w.y - ay) * k, w.z))
        counts[i] += 1
    ob.data.update()
    return counts


def narrow_by_matrix(ob, axes, k):
    """Scale an object horizontally about its column axis, via its world matrix.

    The capitals and the bases are each ten objects sharing one mesh datablock,
    so the mesh must not be touched. Multiplying `ob.scale` is not enough either:
    that scales about the object's own origin, which for the bases is not the
    column axis.

    Composing in world space sidesteps both problems --

        M' = T(axis) @ S(k, k, 1) @ T(-axis) @ M

    -- which is exactly "scale the world about this column's axis", whatever the
    object's own origin and orientation happen to be.
    """
    lo, hi = object_plan_centre(ob)
    i = nearest_axis(lo, hi, axes)
    ax, ay = axes[i]
    t = Matrix.Translation(Vector((ax, ay, 0.0)))
    s = Matrix.Diagonal(Vector((k, k, 1.0, 1.0)))
    ob.matrix_world = t @ s @ t.inverted() @ ob.matrix_world
    return i


def object_plan_centre(ob):
    """World-space horizontal centre of an object, from its bounding box."""
    xs, ys = [], []
    for c in ob.bound_box:
        w = ob.matrix_world @ Vector(c)
        xs.append(w.x)
        ys.append(w.y)
    return (min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0


def main():
    os.makedirs(OUT_RENDER, exist_ok=True)

    bpy.ops.wm.open_mainfile(filepath=CORNICE_WITH_NEW_CAPITALS)
    bpy.ops.wm.save_as_mainfile(filepath=CORNICE_COLUMNS_NARROWED)

    caps, axes = column_axes()
    log(f"{len(axes)} column axes, from the capitals' bell bases:")
    for i, (ax, ay) in enumerate(axes, start=1):
        r = math.hypot(ax, ay - CY)
        log(f"  {i:02d}  x {ax:+.5f}  y {ay:+.5f}   r {r:.5f}  "
            f"theta {math.degrees(math.atan2(ay - CY, ax)):+8.3f}")

    before = {}
    for ob in bpy.data.objects:
        if ob.type == "MESH" and (ob.name.startswith(CAPITAL_PREFIX)
                                  or ob.name.startswith(BASE_PREFIX)
                                  or ob.name == SHAFT_NAME):
            before[ob.name] = radial_extent(ob)

    # --- capitals and bases: one mesh shared by ten objects, so the narrowing
    #     goes into each object's world matrix and the mesh is never touched ---
    for ob in bpy.data.objects:
        if ob.type != "MESH":
            continue
        if ob.name.startswith(CAPITAL_PREFIX) or ob.name.startswith(BASE_PREFIX):
            i = narrow_by_matrix(ob, axes, NARROW)
            log(f"{ob.name[:44]:44s} scaled x/y by {NARROW} about axis {i + 1:02d} "
                f"(mesh shared by {ob.data.users})")
    bpy.context.view_layer.update()

    # --- shafts: all ten in one unshared mesh, so this one is per-vertex ---
    shaft = bpy.data.objects.get(SHAFT_NAME)
    if shaft:
        counts = narrow_by_vertex(shaft, axes, NARROW)
        log(f"{SHAFT_NAME[:44]:44s} narrowed per-vertex across "
            f"{sum(1 for c in counts if c)} axes ({sum(counts)} verts)")
    bpy.context.view_layer.update()

    log("")
    log(f"{'object':44s} {'r_min before':>13s} {'after':>9s} "
        f"{'r_max before':>13s} {'after':>9s}")
    cap_r_min = 1e9
    for name, (b_lo, b_hi) in sorted(before.items()):
        ob = bpy.data.objects[name]
        a_lo, a_hi = radial_extent(ob)
        log(f"{name[:44]:44s} {b_lo:13.5f} {a_lo:9.5f} {b_hi:13.5f} {a_hi:9.5f}")
        if name.startswith(CAPITAL_PREFIX):
            cap_r_min = min(cap_r_min, a_lo)

    log("")
    log(f"==> TARGET_INNER_R for thicken_drum.py: {cap_r_min:.4f}")

    arch = bpy.data.objects.get("Continuous lower entablature architrave")
    if arch:
        a_lo, a_hi = radial_extent(arch)
        log(f"architrave radial {a_lo:.5f}..{a_hi:.5f} (unchanged -- not a column part)")

    bpy.ops.wm.save_as_mainfile(filepath=CORNICE_COLUMNS_NARROWED)
    log("SAVED", CORNICE_COLUMNS_NARROWED)

    with open(os.path.join(OUT_RENDER, "narrow_report.json"), "w") as f:
        json.dump({"narrow": NARROW, "out": CORNICE_COLUMNS_NARROWED,
                   "target_inner_r": cap_r_min,
                   "axes": [{"x": a[0], "y": a[1]} for a in axes]}, f, indent=2)


if __name__ == "__main__":
    main()
