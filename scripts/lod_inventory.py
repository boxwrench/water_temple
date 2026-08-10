"""Where the model's triangles actually live, and what an LOD pass can reach.

Read-only. This runs before any decimation because the answer changes the whole
strategy: the model is built from linked duplicates, so 419 objects share far
fewer unique mesh datablocks. Decimating the datablocks is both cheaper and
correct -- decimating per object would either do the same work 10x over or, if
the meshes were unshared first, multiply the model's memory by 10.

Reports, per unique mesh: faces, how many objects use it, and the total face
count it contributes (faces x users). That last column is what an LOD budget is
actually spent on.

Run:  blender --background --python scripts/lod_inventory.py -- <blend>
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bmesh                                                      # noqa: E402
import bpy                                                        # noqa: E402

from paths import TEMPLE_MODEL, chain_blend                       # noqa: E402


def log(*a):
    print("[lod-inv]", *a)
    sys.stdout.flush()


def args():
    argv = sys.argv
    rest = argv[argv.index("--") + 1:] if "--" in argv else []
    if not rest:
        return chain_blend("frieze-ring-v6")
    return rest[0] if os.path.isabs(rest[0]) else os.path.join(TEMPLE_MODEL, rest[0])


def integrity(me):
    bm = bmesh.new()
    bm.from_mesh(me)
    b = sum(1 for e in bm.edges if len(e.link_faces) == 1)
    nm = sum(1 for e in bm.edges if len(e.link_faces) > 2)
    bm.free()
    return b, nm


def main():
    blend = args()
    bpy.ops.wm.open_mainfile(filepath=blend)
    log(f"{os.path.basename(blend)}")

    mesh_objs = [o for o in bpy.data.objects if o.type == "MESH"]
    users = {}
    for o in mesh_objs:
        users.setdefault(o.data.name, []).append(o.name)

    rows = []
    for me in bpy.data.meshes:
        if me.name not in users:
            continue
        n = len(users[me.name])
        f = len(me.polygons)
        rows.append((f * n, f, n, me.name, me))

    rows.sort(reverse=True)
    total = sum(r[0] for r in rows)

    log(f"{len(mesh_objs)} mesh objects, {len(rows)} unique mesh datablocks, "
        f"{total} faces in the scene")
    log("")
    log(f"{'total faces':>12s} {'%':>6s} {'per copy':>10s} {'uses':>5s}  "
        f"{'boundary':>9s} {'nonmf':>7s}  mesh")
    log("-" * 96)

    cum = 0
    for tot, f, n, name, me in rows[:24]:
        b, nm = integrity(me)
        cum += tot
        log(f"{tot:12d} {100.0 * tot / total:5.1f}% {f:10d} {n:5d}  "
            f"{b:9d} {nm:7d}  {name[:34]}")
    if len(rows) > 24:
        rest = sum(r[0] for r in rows[24:])
        log(f"{rest:12d} {100.0 * rest / total:5.1f}%  ... {len(rows) - 24} more meshes")

    log("")
    log(f"top 24 meshes = {100.0 * cum / total:.1f}% of all faces")

    # What is instanced vs unique -- instanced geometry is where an LOD pass
    # gets leverage, because one decimation lands everywhere it is used.
    shared = [r for r in rows if r[2] > 1]
    single = [r for r in rows if r[2] == 1]
    log(f"instanced meshes: {len(shared)} datablocks -> "
        f"{sum(r[0] for r in shared)} faces ({100.0 * sum(r[0] for r in shared) / total:.1f}%)")
    log(f"one-off meshes:   {len(single)} datablocks -> "
        f"{sum(r[0] for r in single)} faces ({100.0 * sum(r[0] for r in single) / total:.1f}%)")

    log("")
    log("indicative budgets, as a uniform ratio on every mesh:")
    for target in (2_000_000, 500_000, 150_000, 40_000):
        log(f"   {target:>9,} faces -> ratio {target / total:.5f}")


if __name__ == "__main__":
    main()
