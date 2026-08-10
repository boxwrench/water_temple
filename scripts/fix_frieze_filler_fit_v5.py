"""Replace the crude rectangular frieze backing-fillers from v4 with
silhouette-fitted ones.

The v4 fillers were built from each object's flat bounding box (theta range
x z range x r range). That works fine for the lion (roughly rectangular
footprint) but the anthemion tapers -- narrower at the sides of its angular
span than at the center -- so a bounding-box filler is taller than the
actual carving out near the edges and pokes out past the silhouette as a
visible flat plate (confirmed in the v4 render, and per user: "you extend
behind the anthemion only").

Fix: slice each object into angular bins and take the local z min/max (and
local back radius) per bin, then build a filler that follows that stepped
profile instead of one flat rectangle. This hugs the actual silhouette so
it stays hidden regardless of how the object's outline tapers.

The molding fix and its filler ring from v4 are left untouched (user
confirmed "the moulding is ok").

Never touches the v4 file: opens it, immediately saves to a new working
file, and edits there.

Run:  blender --background --python fix_frieze_filler_fit_v5.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import math

import bpy
import bmesh

from paths import chain_blend, chain_render  # noqa: E402

SRC_BLEND = chain_blend("frieze-ring-v4")
OUT_BLEND = chain_blend("frieze-ring-v5")
OUT_RENDER = chain_render("cornice-frieze-ring-v5")

CY = -0.5456366539001465

WALL_EMBED_R = 0.280
OVERLAP = 0.003
Z_MARGIN = 0.001       # small -- fitted profile already hugs the silhouette
N_SLICES = 20
BUCKET_SCALE = 1.6     # neighborhood width per boundary, relative to slice width -- smooths sampling noise


def log(*a):
    print("[fix-v5]", *a)
    sys.stdout.flush()


def remove_old_fillers():
    old = [o for o in bpy.data.objects if o.name.startswith("FRIEZE_BACKING_FILLER_") and "MOLDING" not in o.name]
    log(f"removing {len(old)} old bounding-box frieze fillers")
    for ob in old:
        data = ob.data
        bpy.data.objects.remove(ob, do_unlink=True)
        if data.users == 0:
            bpy.data.meshes.remove(data)


def build_fitted_filler(ob):
    mat = ob.matrix_world
    pts = []
    for v in ob.data.vertices:
        w = mat @ v.co
        pts.append([math.atan2(w.y - CY, w.x), w.z, math.hypot(w.x, w.y - CY)])

    thetas = [p[0] for p in pts]
    if max(thetas) - min(thetas) > math.pi:
        for p in pts:
            if p[0] < 0:
                p[0] += 2 * math.pi
        thetas = [p[0] for p in pts]
    t_min, t_max = min(thetas), max(thetas)
    slice_w = (t_max - t_min) / N_SLICES
    bucket = slice_w * BUCKET_SCALE

    boundaries = [t_min + slice_w * i for i in range(N_SLICES + 1)]
    z_lo, z_hi, r_out = [], [], []
    for tb in boundaries:
        near = [p for p in pts if abs(p[0] - tb) <= bucket]
        if not near:
            near = pts
        z_lo.append(min(p[1] for p in near) - Z_MARGIN)
        z_hi.append(max(p[1] for p in near) + Z_MARGIN)
        r_out.append(min(p[2] for p in near) + OVERLAP)

    bm = bmesh.new()
    bi, bo, ti, to = [], [], [], []
    for i, tb in enumerate(boundaries):
        ct, st = math.cos(tb), math.sin(tb)
        bi.append(bm.verts.new((WALL_EMBED_R * ct, CY + WALL_EMBED_R * st, z_lo[i])))
        bo.append(bm.verts.new((r_out[i] * ct, CY + r_out[i] * st, z_lo[i])))
        ti.append(bm.verts.new((WALL_EMBED_R * ct, CY + WALL_EMBED_R * st, z_hi[i])))
        to.append(bm.verts.new((r_out[i] * ct, CY + r_out[i] * st, z_hi[i])))
    bm.verts.ensure_lookup_table()
    n = len(boundaries)
    for i in range(n - 1):
        bm.faces.new((bo[i], bo[i + 1], to[i + 1], to[i]))
        bm.faces.new((bi[i + 1], bi[i], ti[i], ti[i + 1]))
        bm.faces.new((bi[i], bo[i], bo[i + 1], bi[i + 1]))
        bm.faces.new((ti[i + 1], to[i + 1], to[i], ti[i]))
    bm.faces.new((bi[0], bo[0], to[0], ti[0]))
    bm.faces.new((bi[-1], ti[-1], to[-1], bo[-1]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])

    mesh = bpy.data.meshes.new(f"FRIEZE_BACKING_FILLER_{ob.name}")
    bm.to_mesh(mesh)
    bm.free()
    new_ob = bpy.data.objects.new(mesh.name, mesh)
    bpy.context.scene.collection.objects.link(new_ob)
    new_ob["cornice_master_component"] = True
    log(f"fitted filler for {ob.name}: {N_SLICES} slices, "
        f"z range overall [{min(z_lo):.4f},{max(z_hi):.4f}]")


def main():
    os.makedirs(OUT_RENDER, exist_ok=True)

    bpy.ops.wm.open_mainfile(filepath=SRC_BLEND)
    bpy.ops.wm.save_as_mainfile(filepath=OUT_BLEND)

    remove_old_fillers()

    prefixes = ("LION_", "SCROLL_L", "SCROLL_R", "ANTHEMION_")
    targets = [o for o in bpy.data.objects if o.name.startswith(prefixes)]
    log(f"building fitted fillers for {len(targets)} frieze objects")
    for ob in targets:
        build_fitted_filler(ob)

    bpy.ops.wm.save_as_mainfile(filepath=OUT_BLEND)
    log("SAVED", OUT_BLEND)


if __name__ == "__main__":
    main()
