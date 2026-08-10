"""Shared donor hygiene: the steps every ornament master needs, in the order
that does not damage the mesh.

Why this module exists
----------------------
The first two masters (Leeds lion, Tripo lion) were built by ad-hoc code that
imported a glTF donor and went straight to mirroring and decimating. That order
is wrong, and it bakes cracks into the master:

glTF stores normals and UVs *per vertex*, not per face corner. Every shading
seam in the donor is therefore a run of duplicated, exactly-coincident vertices,
and the faces either side of that seam are topologically disjoint -- Blender
sees a crack, not an edge. `donors/lion.glb` arrives with 36,974 such boundary
edges, `donors/leafscroll.glb` with 45,910.

Decimate COLLAPSE operates on connected topology: it collapses edges. Where
there is no edge, only two coincident vertices, it cannot merge across the seam,
so it decimates each side independently and the two sides drift apart. An
invisible zero-width crack becomes a real, visible gap. Welding first restores
the connectivity so the surface decimates as one sheet.

Why the weld is measured, not assumed
-------------------------------------
Not every donor is vertex-split. Measured on the three donors in this repo:

    donor                       raw boundary   after weld 1e-7*diag
    lion.glb                          36,974              200
    leafscroll.glb                    45,910               52
    corinthian-capital...glb             381              465

The capital arrives already stitched. Welding it does not fix anything and
actively makes it worse (780 boundary / 390 non-manifold at 1e-4*diag), because
its near-coincident vertices are distinct geometry rather than duplicates.
So `weld()` trials the candidate thresholds *and* the no-weld baseline, scores
them, and keeps the winner -- including "do nothing" when that scores best.

Thresholds are a fraction of the mesh's own bounding-box diagonal. Donors arrive
at unrelated scales (1.52 vs 3.14 across these three), so a fixed absolute
epsilon would be a different operation on each one.

Nothing here is shape-specific. Symmetry-plane fitting and half-mirroring live
in the lion's own build script, because they are only correct for a symmetric
wall relief -- a radial 3D element like a capital must not be mirrored that way.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bmesh                                                      # noqa: E402
import bpy                                                        # noqa: E402
from mathutils import Matrix, Vector                              # noqa: E402

# Weld thresholds to trial, as a fraction of the bounding-box diagonal. The
# tightest one won on every donor measured, so the list is short on purpose --
# each candidate costs a full trial weld of a multi-million-face mesh.
WELD_CANDIDATES = (1e-7, 1e-6)


def log(*a):
    print("[donor-prep]", *a)
    sys.stdout.flush()


# ---------------------------------------------------------------- measuring


def bounds(ob):
    """Object-space bounds read from the vertices.

    Deliberately not `ob.bound_box`: that is a cached value which does not
    refresh after `mesh.transform()`, so it silently reports pre-transform
    extents. This bit us once already.
    """
    lo = Vector((1e18,) * 3)
    hi = Vector((-1e18,) * 3)
    for v in ob.data.vertices:
        for i in range(3):
            lo[i] = min(lo[i], v.co[i])
            hi[i] = max(hi[i], v.co[i])
    return lo, hi


def integrity(mesh):
    """Cheap topology check: holes and impossible edges.

    Only the two metrics the weld/decimate order actually moves. The full
    battery (degenerates, doubles, loose, flipped) lives in
    scripts/audit_mesh_quality.py and is run against finished files.
    """
    bm = bmesh.new()
    bm.from_mesh(mesh)
    boundary = sum(1 for e in bm.edges if len(e.link_faces) == 1)
    nonmanifold = sum(1 for e in bm.edges if len(e.link_faces) > 2)
    res = {
        "verts": len(bm.verts),
        "faces": len(bm.faces),
        "boundary": boundary,
        "nonmanifold": nonmanifold,
        "score": boundary + nonmanifold,
    }
    bm.free()
    return res


def report(ob, label):
    r = integrity(ob.data)
    log(f"{label:22s} {r['verts']:8d} v  {r['faces']:8d} f   "
        f"boundary {r['boundary']:7d}   nonmanifold {r['nonmanifold']:6d}")
    return r


# ---------------------------------------------------------------- import


def clear_scene():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    for m in list(bpy.data.meshes):
        if m.users == 0:
            bpy.data.meshes.remove(m)


def import_donor(path, name="DONOR", fresh=True):
    """Import a glTF donor as a single mesh object with transforms baked in.

    Diffs bpy.data.objects around the import rather than trusting list ordering:
    with a temple already loaded, a "take the last mesh" heuristic grabs an
    unrelated object. That broke an earlier integration pass.

    Transforms are baked into the mesh data so every later analysis, bisect and
    modifier operates in one honest coordinate system.
    """
    if fresh:
        clear_scene()
    before = set(bpy.data.objects.keys())
    bpy.ops.import_scene.gltf(filepath=path)
    objs = [o for o in bpy.data.objects
            if o.name not in before and o.type == "MESH"]
    if not objs:
        raise SystemExit(f"no mesh in donor: {path}")

    for o in objs:
        o.data.transform(o.matrix_world)
        o.matrix_world = Matrix.Identity(4)

    if len(objs) > 1:
        bpy.ops.object.select_all(action="DESELECT")
        for o in objs:
            o.select_set(True)
        bpy.context.view_layer.objects.active = objs[0]
        bpy.ops.object.join()
        objs = [bpy.context.view_layer.objects.active]

    ob = objs[0]
    ob.name = name
    ob.rotation_mode = "XYZ"
    log(f"imported {os.path.basename(path)} ({len(objs)} object after join)")
    report(ob, "raw donor")
    return ob


# ---------------------------------------------------------------- weld


def _welded_copy(mesh, dist):
    m = mesh.copy()
    bm = bmesh.new()
    bm.from_mesh(m)
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=dist)
    bm.to_mesh(m)
    bm.free()
    m.update()
    return m


def weld(ob, candidates=WELD_CANDIDATES):
    """Merge coincident vertices, if and only if measurement says it helps.

    Returns the chosen relative threshold (0.0 means the mesh was left alone).
    """
    lo, hi = bounds(ob)
    diag = (hi - lo).length
    base = integrity(ob.data)
    best = (base["score"], 0.0, None)

    for rel in candidates:
        m = _welded_copy(ob.data, diag * rel)
        r = integrity(m)
        log(f"  weld trial {rel:.0e}*diag: boundary {r['boundary']:7d}  "
            f"nonmanifold {r['nonmanifold']:6d}  score {r['score']:7d}")
        if r["score"] < best[0]:
            if best[2] is not None:
                bpy.data.meshes.remove(best[2])
            best = (r["score"], rel, m)
        else:
            bpy.data.meshes.remove(m)

    score, rel, m = best
    if m is None:
        log(f"  weld: skipped -- baseline score {base['score']} already best "
            f"(this donor is not vertex-split)")
        return 0.0

    old = ob.data
    m.name = old.name
    ob.data = m
    bpy.data.meshes.remove(old)
    log(f"  weld: kept {rel:.0e}*diag (={diag * rel:.3e}), "
        f"score {base['score']} -> {score}")
    report(ob, "welded")
    return rel


# ---------------------------------------------------------------- decimate


def decimate(ob, target_tris):
    """Collapse-decimate to roughly target_tris, after welding.

    Run this only on welded topology. On split topology COLLAPSE cannot merge
    across the seams and pulls the two sides of every seam apart -- see the
    module docstring.
    """
    ob.data.calc_loop_triangles()
    tris = len(ob.data.loop_triangles)
    if tris <= target_tris:
        log(f"  decimate: not needed ({tris} tris <= target {target_tris})")
        return tris

    bpy.context.view_layer.objects.active = ob
    m = ob.modifiers.new("DECIMATE", "DECIMATE")
    m.decimate_type = "COLLAPSE"
    m.ratio = target_tris / tris
    ratio = m.ratio
    bpy.ops.object.modifier_apply(modifier="DECIMATE")
    ob.data.calc_loop_triangles()
    out = len(ob.data.loop_triangles)
    log(f"  decimate: {tris} -> {out} tris (ratio {ratio:.5f})")
    report(ob, "decimated")
    return out


# ---------------------------------------------------------------- finish


def shade_smooth(ob):
    for p in ob.data.polygons:
        p.use_smooth = True


def stamp_provenance(ob, source_asset, derivation, **extra):
    """Record where the geometry came from and what was done to it.

    Every file in donors/ is the project owner's own work except
    donors/lion_head.glb (Leeds Libraries, CC BY 4.0), so the default license
    fields say so. Pass license=/license_url= to override for a third-party
    donor.
    """
    ob["source_asset"] = source_asset
    ob["derivation"] = derivation
    if "source_url" not in extra:
        ob["source_url"] = "original work -- not sourced from a third party"
    if "license" not in extra:
        ob["license"] = "owned by the project owner; no third-party license"
        ob["license_url"] = ""
    for k, v in extra.items():
        ob[k] = v
    ob.data.calc_loop_triangles()
    ob["triangle_count"] = len(ob.data.loop_triangles)


def save_master(ob, blend_path, master_name):
    """Save a file containing this object and nothing else.

    The Leeds master file drags an entire stale temple along with it (38 MB for
    a 60k-tri mask). Masters built here carry only the master, so appending one
    cannot pull unrelated junk into the temple file.
    """
    ob.name = master_name
    ob.data.name = master_name
    for other in list(bpy.data.objects):
        if other is not ob:
            bpy.data.objects.remove(other, do_unlink=True)
    os.makedirs(os.path.dirname(blend_path), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=blend_path)
    log(f"SAVED {blend_path}  ({master_name})")
