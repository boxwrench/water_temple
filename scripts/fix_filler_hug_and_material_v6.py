"""Make the frieze backing fillers actually hidden, and put the new decoration
on the temple's own cast-stone material.

Two defects, both of which made the new frieze read as stuck onto the building
rather than cast with it:

1. **The fillers were visible as raised plates.** v5 already fitted them to each
   element's silhouette, but with `N_SLICES = 20` and `BUCKET_SCALE = 1.6` it
   took min/max z over a window +-1.6 slice-widths wide -- a max-filter spanning
   about +-16% of the element's entire angular span. That *dilates* the
   silhouette: wherever the outline is short next to something tall, the filler
   gets built up to the tall height. `Z_MARGIN` then pushed another 1mm outward
   on top. Because each filler was dilated past its own element and the elements
   already overlap in theta, adjacent fillers merged into one continuous raised
   band running the full 360 degrees.

   Fix: many more slices, and *decouple the two neighbourhood widths*, because
   they want opposite things. The z profile wants a tight window so it hugs the
   real outline. The back radius wants a wide window, because it takes the
   minimum (deepest) radius nearby and a wide window there is the conservative
   direction -- it keeps the filler tucked further in. Then inset z slightly
   instead of outsetting it, so a filler can only ever sit *inside* its
   element's silhouette, never proud of it.

2. **The fillers had no material at all**, so they rendered in Blender's default
   grey, and the frieze elements were still on the bright near-white `*_CLAY`
   preview material from the assembly study while the whole temple is on
   `Raised cast-stone ornament` (0.305, 0.315, 0.32). Both now use the temple's
   material, so any residual sliver blends instead of announcing itself.

Never touches the v5 file: opens it, immediately saves to a new working file,
and edits there.

Run:  blender --background --python scripts/fix_filler_hug_and_material_v6.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import math                                                     # noqa: E402

import bmesh                                                    # noqa: E402
import bpy                                                      # noqa: E402

from paths import chain_blend, chain_render                     # noqa: E402

SRC_BLEND = chain_blend("frieze-ring-v5")
OUT_BLEND = chain_blend("frieze-ring-v6")
OUT_RENDER = chain_render("cornice-frieze-ring-v6")

CY = -0.5456366539001465

WALL_EMBED_R = 0.280
OVERLAP = 0.003

# The temple's own ornament material -- what every other piece of decoration on
# the building already uses.
TEMPLE_ORNAMENT_MAT = "Raised cast-stone ornament"

N_SLICES = 72          # was 20
Z_BUCKET_SCALE = 0.55  # tight: the z profile must hug the real outline
R_BUCKET_SCALE = 2.5   # wide: min-radius over a wide window is the safe direction
Z_INSET = 0.0008       # shrink, never grow -- a filler may hide, never protrude

FRIEZE_PREFIXES = ("LION_", "SCROLL_L", "SCROLL_R", "ANTHEMION_")


def log(*a):
    print("[fix-v6]", *a)
    sys.stdout.flush()


def is_frieze_element(ob):
    return (ob.type == "MESH"
            and ob.name.startswith(FRIEZE_PREFIXES)
            and not ob.name.startswith("FRIEZE_BACKING_FILLER"))


def remove_old_fillers():
    """Drop the v5 frieze fillers. The separate molding filler ring is kept --
    the user approved the molding and it is not part of this defect."""
    old = [o for o in bpy.data.objects
           if o.name.startswith("FRIEZE_BACKING_FILLER_") and "MOLDING" not in o.name]
    for ob in old:
        data = ob.data
        bpy.data.objects.remove(ob, do_unlink=True)
        if data.users == 0:
            bpy.data.meshes.remove(data)
    log(f"removed {len(old)} dilated v5 fillers")


def cylindrical_points(ob):
    """Element vertices as (theta, z, r), unwrapped across the +-pi seam.

    Unwrapping matters: an object straddling the seam otherwise reports a false
    full-360-degree angular range and the filler is built around the whole drum.
    """
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
    return pts


def near(pts, tb, width):
    """Points within `width` of boundary angle tb, widening until non-empty.

    v5 fell back to the *entire* point set when a bucket came up empty, which
    silently rebuilt that slice at the element's full extent -- the worst
    possible failure for a filler that is supposed to hug.
    """
    for k in (1.0, 2.0, 4.0, 8.0):
        got = [p for p in pts if abs(p[0] - tb) <= width * k]
        if got:
            return got
    return pts


def build_fitted_filler(ob, mat):
    pts = cylindrical_points(ob)
    thetas = [p[0] for p in pts]
    t_min, t_max = min(thetas), max(thetas)
    slice_w = (t_max - t_min) / N_SLICES

    boundaries = [t_min + slice_w * i for i in range(N_SLICES + 1)]
    z_lo, z_hi, r_out = [], [], []
    for tb in boundaries:
        z_near = near(pts, tb, slice_w * Z_BUCKET_SCALE)
        r_near = near(pts, tb, slice_w * R_BUCKET_SCALE)
        lo = min(p[1] for p in z_near) + Z_INSET
        hi = max(p[1] for p in z_near) - Z_INSET
        if hi < lo:                      # slice thinner than twice the inset
            lo = hi = (lo + hi) / 2.0
        z_lo.append(lo)
        z_hi.append(hi)
        r_out.append(min(p[2] for p in r_near) + OVERLAP)

    bm = bmesh.new()
    bi, bo, ti, to = [], [], [], []
    for i, tb in enumerate(boundaries):
        ct, st = math.cos(tb), math.sin(tb)
        bi.append(bm.verts.new((WALL_EMBED_R * ct, CY + WALL_EMBED_R * st, z_lo[i])))
        bo.append(bm.verts.new((r_out[i] * ct, CY + r_out[i] * st, z_lo[i])))
        ti.append(bm.verts.new((WALL_EMBED_R * ct, CY + WALL_EMBED_R * st, z_hi[i])))
        to.append(bm.verts.new((r_out[i] * ct, CY + r_out[i] * st, z_hi[i])))
    bm.verts.ensure_lookup_table()
    for i in range(len(boundaries) - 1):
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
    mesh.materials.append(mat)
    new_ob = bpy.data.objects.new(mesh.name, mesh)
    bpy.context.scene.collection.objects.link(new_ob)
    new_ob["cornice_master_component"] = True
    return (t_min, t_max), max(z_hi)


MOLDING_PREFIX = "LEAF-AND-TONGUE"
MOLDING_OVERLAP = 0.0008
MOLDING_Z_SAMPLES = 32
MOLDING_SEGMENTS = 180


def rebuild_molding_filler(mat):
    """Rebuild the shelf molding's backing ring so it stops at the molding's
    BACK, not its front.

    The v4 ring ran out to r 0.2994 while the leaf-and-tongue tongues sit at
    r 0.2984-0.2996 -- it was buried flush with the molding's face, leaving
    0.0002 of relief and effectively erasing the dentil band. That went
    unnoticed because the ring carried no material and rendered at Blender's
    default near-white, so the 0.305-grey molding read as dark teeth against a
    bright ring: a material contrast masquerading as depth.

    The outer radius is a single conservative value: the minimum radius over
    ALL molding geometry. Tracking the back radius per z band -- the obvious
    refinement -- is wrong here, because the molding is NOT rotationally uniform
    at the tongue band: it is a repeating pattern of separate tongues with gaps
    between them. A per-band radius follows the tongues' own backs and so fills
    those gaps, which is the same erasure by a subtler route. One flat radius
    behind everything leaves every part of the molding standing proud.
    """
    old = [o for o in bpy.data.objects if o.name.startswith("FRIEZE_BACKING_FILLER_MOLDING")]
    for ob in old:
        data = ob.data
        bpy.data.objects.remove(ob, do_unlink=True)
        if data.users == 0:
            bpy.data.meshes.remove(data)

    samples = []
    for o in bpy.data.objects:
        if o.type == "MESH" and o.name.startswith(MOLDING_PREFIX):
            m = o.matrix_world
            for v in o.data.vertices:
                w = m @ v.co
                samples.append((w.z, math.hypot(w.x, w.y - CY)))
    if not samples:
        log("no molding objects found -- skipping molding filler")
        return

    z0 = min(s[0] for s in samples)
    z1 = max(s[0] for s in samples)
    r_back = min(s[1] for s in samples)
    r_out = r_back + MOLDING_OVERLAP
    r_front = max(s[1] for s in samples)

    bm = bmesh.new()
    profile = [(r_out, z0), (r_out, z1)]
    outer = [bm.verts.new((r, CY, z)) for r, z in profile]
    inner = [bm.verts.new((WALL_EMBED_R, CY, z1)),
             bm.verts.new((WALL_EMBED_R, CY, z0))]
    loop = outer + inner
    edges = [bm.edges.new((loop[i], loop[(i + 1) % len(loop)])) for i in range(len(loop))]
    bmesh.ops.spin(bm, geom=edges + loop, cent=(0.0, CY, 0.0), axis=(0.0, 0.0, 1.0),
                   angle=2 * math.pi, steps=MOLDING_SEGMENTS, use_duplicate=False)
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-6)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])

    mesh = bpy.data.meshes.new("FRIEZE_BACKING_FILLER_MOLDING")
    bm.to_mesh(mesh)
    bm.free()
    mesh.materials.append(mat)
    ob = bpy.data.objects.new(mesh.name, mesh)
    bpy.context.scene.collection.objects.link(ob)
    ob["cornice_master_component"] = True
    log(f"molding filler rebuilt: z[{z0:.4f},{z1:.4f}] r[{WALL_EMBED_R:.4f},{r_out:.4f}]  "
        f"molding back r={r_back:.4f} front r={r_front:.4f}  ->  relief now "
        f"{r_front - r_out:.4f} (was {r_front - 0.2994:.4f})")


def merged_coverage(spans):
    """Merge the fillers' angular spans to answer: is this a continuous ring?"""
    norm = []
    for a, b in spans:
        a %= 2 * math.pi
        b %= 2 * math.pi
        if b < a:
            norm += [(a, 2 * math.pi), (0.0, b)]
        else:
            norm.append((a, b))
    norm.sort()
    merged = []
    for a, b in norm:
        if merged and a <= merged[-1][1] + 1e-9:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    covered = sum(b - a for a, b in merged)
    return merged, math.degrees(covered)


def main():
    os.makedirs(OUT_RENDER, exist_ok=True)

    bpy.ops.wm.open_mainfile(filepath=SRC_BLEND)
    bpy.ops.wm.save_as_mainfile(filepath=OUT_BLEND)

    mat = bpy.data.materials.get(TEMPLE_ORNAMENT_MAT)
    if mat is None:
        raise SystemExit(f"temple material {TEMPLE_ORNAMENT_MAT!r} not found")

    # --- diagnose the v5 state before replacing it ---
    old_spans = [cylindrical_points(o) for o in bpy.data.objects
                 if o.name.startswith("FRIEZE_BACKING_FILLER_") and "MOLDING" not in o.name]
    old_spans = [(min(p[0] for p in pts), max(p[0] for p in pts)) for pts in old_spans]
    _, old_deg = merged_coverage(old_spans)
    log(f"v5 fillers covered {old_deg:.1f} of 360 degrees of the drum")

    remove_old_fillers()

    targets = [o for o in bpy.data.objects if is_frieze_element(o)]
    log(f"rebuilding fillers for {len(targets)} frieze elements "
        f"({N_SLICES} slices, z bucket {Z_BUCKET_SCALE}, r bucket {R_BUCKET_SCALE}, "
        f"inset {Z_INSET})")

    spans = []
    top_by_kind = {}
    for ob in targets:
        span, top_z = build_fitted_filler(ob, mat)
        spans.append(span)
        kind = ob.name.split("_")[0]
        top_by_kind[kind] = max(top_by_kind.get(kind, -1e9), top_z)

    merged, new_deg = merged_coverage(spans)
    log(f"new fillers cover {new_deg:.1f} of 360 degrees in {len(merged)} arc(s)")

    # Headline check: no filler may reach above the element it hides. Seeded at
    # -inf, not 0, so a correctly-inset filler reports its real (negative)
    # clearance instead of being floored at zero and looking borderline.
    worst = -1e9
    for ob in targets:
        pts = cylindrical_points(ob)
        el_top = max(p[1] for p in pts)
        f = bpy.data.objects.get(f"FRIEZE_BACKING_FILLER_{ob.name}")
        f_top = max((f.matrix_world @ v.co).z for v in f.data.vertices)
        worst = max(worst, f_top - el_top)
    log(f"worst filler-above-element overhang: {worst:+.5f} (must be <= 0)")

    rebuild_molding_filler(mat)

    # --- put the new decoration on the temple's own material ---
    recoloured = 0
    for ob in bpy.data.objects:
        if ob.type != "MESH":
            continue
        if is_frieze_element(ob) or ob.name.startswith("FRIEZE_BACKING_FILLER_"):
            ob.data.materials.clear()
            ob.data.materials.append(mat)
            recoloured += 1
    log(f"put {recoloured} frieze/filler objects on {TEMPLE_ORNAMENT_MAT!r}")

    # Capture the name before removing -- touching m.name afterwards raises
    # ReferenceError, the datablock is already gone.
    for m in list(bpy.data.materials):
        if m.name.endswith("_CLAY") and m.users == 0:
            name = m.name
            bpy.data.materials.remove(m)
            log(f"removed unused preview material {name}")

    bpy.ops.wm.save_as_mainfile(filepath=OUT_BLEND)
    log("SAVED", OUT_BLEND)


if __name__ == "__main__":
    main()
