"""Rebuild the temple's structure as low-poly lathes instead of decimating it.

The point, in one line: a drum *is* a cylinder, so approximating it with a
decimator is fighting a mesh to recover a shape we can simply state.

Why this exists
---------------
Decimation approximates a surface it does not understand. That is the right tool
for a sculpted lion and the wrong one for an annulus whose true description is
"r 0.2023 -> 0.2860, z 0.1980 -> 0.3130". Collapsing structure wrecks the
silhouette -- the architrave fragments, the fluting shreds -- while a lathe built
from the measured profile costs a few hundred faces and is arguably *more*
faithful than the original, because the profile is sampled rather than collapsed.

It is also what makes a small budget reachable at all. Structure is 45,028 faces:
90% of a 50,000-face target before a single ornament is placed.

Method
------
For each structural object, sample its radial profile in Z bands -- outer radius
and inner radius per band -- simplify that polyline with Ramer-Douglas-Peucker,
close it into one outline, and revolve it. Sampling then simplifying means flat
runs cost two points and mouldings keep their steps.

**Continuous rings vs clustered parts.** Angular *span* is not enough to tell
them apart: `Ten deep-fluted shaft overlays` spans a full 360 degrees and is ten
separate columns, so lathing it about the colonnade axis would weld the
colonnade into one solid ring. So coverage is measured, not span -- what fraction
of 360 one-degree bins actually contain geometry. Continuous rings are lathed
about the colonnade axis; clustered objects are split per column and each cluster
is lathed about its own axis.

Ornament is not touched here; it is decimated separately.

**The rebuilt mesh is authored in world space and needs its object's
transform reset to match.** `polar_points()` reads `ob.matrix_world @ v.co`
and the clustered branch revolves each profile about the true world column
axis, not the object's own origin -- so the geometry that lands in the new
mesh is already in final position. Assigning it to `ob.data` without also
resetting `ob.matrix_world` to identity placed it twice for any object that
still carried its own placement transform: true for the ten per-column
pieces (`Molded column base radial module NN`), false for the single
continuous rings, which is exactly why this shipped for a while with only
some structure visibly flung away from the building and the rest looking
fine. Fixed 2026-08-10.

Run:  blender --background --python scripts/build_lod_structure.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import json                                                       # noqa: E402
import math                                                       # noqa: E402

import bmesh                                                      # noqa: E402
import bpy                                                        # noqa: E402
from mathutils import Matrix, Vector                              # noqa: E402

from paths import LOD, lod_blend                                  # noqa: E402

CY = -0.5456366539001465
SRC = lod_blend("base")
OUT = lod_blend("structure")

# Anything whose name contains one of these is ornament: decimated elsewhere,
# never lathed. A lathe would turn a lion into a torus.
ORNAMENT_KEYS = ("LION", "SCROLL", "ANTHEMION", "Corinthian capital",
                 "WELL braid", "WELL cap", "LEAF-AND-TONGUE", "FRIEZE_BACKING",
                 "Lion scalloped", "Upper cornice 36-degree", "RINCEAUX")

# Dead weight carried in the scene since before the frieze work: a backup copy of
# the superseded cornice master, sitting off to one side of the building. It has
# been invisible in every render because it is outside the framing, and it only
# surfaced here because the lathe rebuilt it into a visible coil. Not part of the
# temple -- dropped from the LOD line entirely.
DEAD_OBJECTS = ("CORNICE_OLD_MASTER_BACKUP", "CORNICE_CLEAN_PREDONOR_MASTER_36DEG")

Z_BANDS = 28          # profile sampling resolution before simplification
SEGMENTS = 40         # revolve segments for a full ring
COL_SEGMENTS = 14     # revolve segments for a single column
RDP_TOL_FRAC = 0.0016 # profile simplification tolerance, fraction of the diagonal
# A real void between parts, in degrees. Continuity is decided by the LARGEST
# angular gap, not by how many bins contain vertices: a continuous ring built
# with 256 segments occupies only 256 of 360 one-degree bins and would read as
# "clustered" on an occupancy test, while its largest gap is a scale-free 1.4
# degrees. Ten columns leave gaps of ~16.
MAX_GAP_DEG = 8.0


def log(*a):
    print("[lod-struct]", *a)
    sys.stdout.flush()


def is_ornament(name):
    return any(k in name for k in ORNAMENT_KEYS)


def polar_points(ob, cx=0.0, cy=CY):
    out = []
    for v in ob.data.vertices:
        w = ob.matrix_world @ v.co
        dx, dy = w.x - cx, w.y - cy
        out.append((math.hypot(dx, dy), w.z, math.atan2(dy, dx)))
    return out


def largest_gap_deg(pts):
    """Widest angular void in the point set, in degrees."""
    ths = sorted(math.degrees(t) % 360.0 for _, _, t in pts)
    if len(ths) < 4:
        return 360.0
    gaps = [ths[i + 1] - ths[i] for i in range(len(ths) - 1)]
    gaps.append(ths[0] + 360.0 - ths[-1])
    return max(gaps)


def rdp(points, tol):
    """Ramer-Douglas-Peucker on a 2-D polyline. Flat runs collapse to their ends."""
    if len(points) < 3:
        return list(points)
    a, b = points[0], points[-1]
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    span = math.hypot(dx, dy)
    worst, idx = -1.0, 0
    for i in range(1, len(points) - 1):
        px, py = points[i]
        if span < 1e-12:
            d = math.hypot(px - ax, py - ay)
        else:
            d = abs(dy * px - dx * py + bx * ay - by * ax) / span
        if d > worst:
            worst, idx = d, i
    if worst <= tol:
        return [a, b]
    return rdp(points[:idx + 1], tol)[:-1] + rdp(points[idx:], tol)


def profile(pts, tol):
    """Closed (r, z) outline: up the outer surface, back down the inner one."""
    zs = [p[1] for p in pts]
    z_lo, z_hi = min(zs), max(zs)
    if z_hi - z_lo < 1e-9:
        return None

    outer, inner = [], []
    for i in range(Z_BANDS):
        a = z_lo + (z_hi - z_lo) * i / Z_BANDS
        b = z_lo + (z_hi - z_lo) * (i + 1) / Z_BANDS
        sel = [p for p in pts if a <= p[1] < b or (i == Z_BANDS - 1 and p[1] == z_hi)]
        if not sel:
            continue
        z = (a + b) / 2.0
        outer.append((max(p[0] for p in sel), z))
        inner.append((min(p[0] for p in sel), z))
    if len(outer) < 2:
        return None

    # Carry the true extremes so the silhouette's top and bottom are exact.
    outer[0] = (outer[0][0], z_lo)
    outer[-1] = (outer[-1][0], z_hi)
    inner[0] = (inner[0][0], z_lo)
    inner[-1] = (inner[-1][0], z_hi)

    outer = rdp(outer, tol)
    inner = rdp(inner, tol)
    loop = outer + list(reversed(inner))

    # Drop consecutive duplicates, which a solid (inner == outer) produces.
    clean = [loop[0]]
    for p in loop[1:]:
        if math.hypot(p[0] - clean[-1][0], p[1] - clean[-1][1]) > 1e-9:
            clean.append(p)
    return clean if len(clean) >= 3 else None


def revolve(bm, prof, segments, cx, cy, t0=0.0, t1=2.0 * math.pi, closed=True):
    n = len(prof)
    rings = []
    steps = segments if closed else segments + 1
    for s in range(steps):
        t = t0 + (t1 - t0) * (s / segments)
        ring = [bm.verts.new(Vector((cx + r * math.cos(t),
                                     cy + r * math.sin(t), z)))
                for r, z in prof]
        rings.append(ring)
    for s in range(len(rings) if closed else len(rings) - 1):
        a = rings[s]
        b = rings[(s + 1) % len(rings)]
        for i in range(n):
            j = (i + 1) % n
            try:
                bm.faces.new((a[i], a[j], b[j], b[i]))
            except ValueError:
                pass


def column_axes():
    """The ten column axes, from the capitals' bell bases."""
    caps = sorted([o for o in bpy.data.objects
                   if o.type == "MESH" and o.name.startswith("Corinthian capital")],
                  key=lambda o: o.name)
    axes = []
    for ob in caps:
        ws = [ob.matrix_world @ v.co for v in ob.data.vertices]
        z_lo = min(w.z for w in ws)
        base = [w for w in ws if w.z <= z_lo + 0.004]
        axes.append(((max(w.x for w in base) + min(w.x for w in base)) / 2.0,
                     (max(w.y for w in base) + min(w.y for w in base)) / 2.0))
    return axes


def rebuild(ob, axes):
    pts = polar_points(ob)
    if not pts:
        return None
    diag = ((max(p[0] for p in pts) - min(p[0] for p in pts)) ** 2
            + (max(p[1] for p in pts) - min(p[1] for p in pts)) ** 2) ** 0.5
    tol = max(diag * RDP_TOL_FRAC, 1e-5)
    gap = largest_gap_deg(pts)

    bm = bmesh.new()
    if gap <= MAX_GAP_DEG:
        prof = profile(pts, tol)
        if not prof:
            bm.free()
            return None
        revolve(bm, prof, SEGMENTS, 0.0, CY)
        kind, nprof = "ring", len(prof)
    else:
        # Clustered: split by nearest column axis and lathe each about its own.
        groups = {i: [] for i in range(len(axes))}
        for v in ob.data.vertices:
            w = ob.matrix_world @ v.co
            best, bd = 0, 1e18
            for i, (ax, ay) in enumerate(axes):
                d = (w.x - ax) ** 2 + (w.y - ay) ** 2
                if d < bd:
                    best, bd = i, d
            groups[best].append((math.hypot(w.x - axes[best][0],
                                            w.y - axes[best][1]), w.z, 0.0))
        made = 0
        for i, g in groups.items():
            if len(g) < 8:
                continue
            prof = profile(g, tol)
            if not prof:
                continue
            revolve(bm, prof, COL_SEGMENTS, axes[i][0], axes[i][1])
            made += 1
        if not made:
            bm.free()
            return None
        kind, nprof = f"{made} columns", 0

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    me = bpy.data.meshes.new(ob.data.name + "_LOD")
    bm.to_mesh(me)
    bm.free()
    me.update()
    for m in ob.data.materials:
        me.materials.append(m)
    return me, kind, nprof, gap


def main():
    os.makedirs(LOD, exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=SRC)
    bpy.ops.wm.save_as_mainfile(filepath=OUT)

    axes = column_axes()
    log(f"{len(axes)} column axes recovered from the capitals")

    for name in DEAD_OBJECTS:
        ob = bpy.data.objects.get(name)
        if ob:
            f = len(ob.data.polygons) if ob.type == "MESH" else 0
            bpy.data.objects.remove(ob, do_unlink=True)
            log(f"dropped dead object {name} ({f:,} faces)")

    targets = [o for o in bpy.data.objects
               if o.type == "MESH" and o.data.vertices and not is_ornament(o.name)]
    log(f"{len(targets)} structural objects to rebuild")
    log("")
    log(f"{'object':44s} {'before':>8s} {'after':>7s} {'gap°':>6s}  how")
    log("-" * 88)

    before_total = after_total = 0
    rows = []
    for ob in sorted(targets, key=lambda o: -len(o.data.polygons)):
        before = len(ob.data.polygons)
        res = rebuild(ob, axes)
        if res is None:
            after_total += before
            before_total += before
            continue
        me, kind, nprof, gap = res
        old = ob.data
        after = len(me.polygons)
        # Never ship a "simplification" that is bigger than what it replaced.
        if after >= before:
            if me.users == 0:
                bpy.data.meshes.remove(me)
            after = before
            kind = "kept (rebuild was larger)"
        else:
            ob.data = me
            # rebuild()/revolve() author the new mesh directly in WORLD space
            # (polar_points() reads ob.matrix_world @ v.co, and clustered
            # profiles revolve about the true world column axis, not the
            # object's own origin). Any object that still carries its own
            # placement transform -- true for the ten per-column pieces like
            # "Molded column base radial module NN", false for the single
            # continuous rings -- would place that geometry twice: once by
            # authoring it in world coordinates, again by matrix_world. This
            # was shipping broken: the column-base rings and one step course
            # rendered flung away from the building (bounding diagonal 2.29
            # against a real ~1.3), confirmed by render before this fix.
            ob.matrix_world = Matrix.Identity(4)
            if old.users == 0:
                bpy.data.meshes.remove(old)
        before_total += before
        after_total += after
        rows.append({"object": ob.name, "before": before, "after": after,
                     "kind": kind, "max_gap_deg": gap})
        if before >= 500:
            log(f"{ob.name[:44]:44s} {before:8,d} {after:7,d} {gap:6.1f}  "
                f"{kind}" + (f", {nprof}-pt profile" if nprof else ""))

    log("")
    log(f"structure {before_total:,} -> {after_total:,} faces "
        f"({100.0 * after_total / max(1, before_total):.1f}%)")

    total = sum(len(o.data.polygons) for o in bpy.data.objects if o.type == "MESH")
    log(f"whole model now {total:,} faces")

    bpy.ops.wm.save_as_mainfile(filepath=OUT)
    log("SAVED " + OUT)
    with open(os.path.join(LOD, "lod-structure-report.json"), "w") as f:
        json.dump({"src": SRC, "out": OUT, "before": before_total,
                   "after": after_total, "objects": rows}, f, indent=2)


if __name__ == "__main__":
    main()
