"""Single source of truth for the project layout.

Every script imports from here rather than repeating absolute paths. The project
moved once already (from OneDrive\\Desktop\\temple to Downloads\\temple) and left
several scripts broken; keeping the layout in one file means the next move is a
one-line change.

Layout:
  masters/       approved, reusable ornament geometry
  temple-model/  the building itself
  donors/        third-party and generated source assets -- never edited in place
  reference/     input imagery
  scripts/       build and analysis code (this directory)
  renders/       review output
  trace/         measured trace data
  docs/          specs
"""

import math
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MASTERS = os.path.join(ROOT, "masters")
TEMPLE_MODEL = os.path.join(ROOT, "temple-model")
DONORS = os.path.join(ROOT, "donors")
REFERENCE = os.path.join(ROOT, "reference")
RENDERS = os.path.join(ROOT, "renders")
TRACE = os.path.join(ROOT, "trace")
DOCS = os.path.join(ROOT, "docs")

# Resolution tiers for other uses (game / real-time). LOD0 is the full model;
# lower tiers are decimated from a single repaired base, never from each other.
LOD = os.path.join(ROOT, "lod")

# --- approved masters ---
# The anthemion plaque, welded. The procedural build left 31,450 boundary edges
# and 10,514 duplicate verts on 80,000 faces, and ten copies went into the ring.
# A weld merges coincident vertices without moving any (bounds shift measured at
# 0.000e+00), so the approved shape is untouched.
#
# The pre-weld original was deleted 2026-08-08 once this superseded it.
# scripts/weld_anthemion_master.py is kept as the record of how this was made,
# but its input is gone, so it is spent -- re-deriving it would mean rebuilding
# the plaque from trace/ first.
ANTHEMION_MASTER_V2 = os.path.join(MASTERS, "anthemion-plaque-master-v2.blend")

ANTHEMION_MASTER = ANTHEMION_MASTER_V2

# Resolution tiers (scripts/build_anthemion_lods.py), decimated straight from
# ANTHEMION_MASTER -- no repair or visibility-cull step needed first, see that
# script's docstring. Ratios are gentler than the leafscroll/lion's .25/.1/.05:
# this is the deepest, sharpest relief of the four masters (many thin,
# close-set undercut petals), and at .10 it was already crystalline while .05
# collapsed into an unrecognizable crumpled mass. Rendered and confirmed clean
# at every tier below instead.
ANTHEMION_MASTER_LOD1 = os.path.join(MASTERS, "anthemion-plaque-master-lod1.blend")  # ratio 0.50, 39,999 faces
ANTHEMION_MASTER_LOD2 = os.path.join(MASTERS, "anthemion-plaque-master-lod2.blend")  # ratio 0.25, 20,000 faces
ANTHEMION_MASTER_LOD3 = os.path.join(MASTERS, "anthemion-plaque-master-lod3.blend")  # ratio 0.15, 12,000 faces

# The scroll had no master until 2026-08-08: the frieze re-imported the raw
# 1.42M-face donor twice per module, so the ring carried twenty copies of it
# (~93% of the whole model's faces) complete with the donor's split-seam holes.
# The master keeps the donor's own axes, so orient_leafscroll() is unaffected --
# only the density changes.
LEAFSCROLL_MASTER_V1 = os.path.join(MASTERS, "leafscroll-master.blend")

# -v2 is a mesh-integrity repair (scripts/repair_leafscroll.py): 26 tiny
# sliver-triangle defects, each a closed 3-edge boundary loop plus its own
# pair of non-manifold edges (52 + 52), welded away via the same scoped
# self-collapse technique proven on the capital -- boundary 52 -> 0,
# non-manifold 52 -> 0, 0 loose/degenerate/duplicate. Confirmed pixel-
# identical to v1 by render (the defects were far below visible scale).
LEAFSCROLL_MASTER_V2 = os.path.join(MASTERS, "leafscroll-master-v2.blend")

# -v3 is v2 with the invisible back half removed (scripts/strip_leafscroll_
# interior.py): orient_leafscroll() seats the scroll flush against the
# cornice wall, so only the raw +X hemisphere is ever a valid viewpoint --
# multi-viewpoint BVH raycast (314 viewpoints, 2 radii, filtered to the +X
# hemisphere) found 47,482 of 199,844 faces (23.8%) are never visible from
# any such viewpoint. A straightforward flat-plane cut through the same
# invisible mass was tried first and rejected (scripts/simplify_leafscroll_
# depth.py -- the organic acanthus relief has no depth where a cross-section
# is simple enough to cap without starburst artifacts, same failure shape as
# Solidify on the capital). Visibility culling needs no cap: it only removes
# whole invisible faces and leaves the boundary open, same as CAPITAL_MASTER_
# RENDER. Result: 199,844 -> 152,362 faces, 0 non-manifold/loose/duplicate,
# confirmed via a 9-angle render sweep plus a matched-camera pixel-diff
# against v2 (the only differences were sub-pixel AA/shading noise at
# stripped-edge triangulation, checked by cropping and comparing directly).
# This is an open shell where the back was removed -- fine for real-time/
# render use, NOT for STL/printing (same split as the capital's two tracks;
# revisit if the scroll ever needs a print-safe version).
LEAFSCROLL_MASTER_V3 = os.path.join(MASTERS, "leafscroll-master-v3.blend")

LEAFSCROLL_MASTER = LEAFSCROLL_MASTER_V3
LEAFSCROLL_MASTER_OBJECT = "LEAFSCROLL_MASTER"

# Resolution tiers (scripts/build_leafscroll_lods.py), straight Collapse
# decimation of LEAFSCROLL_MASTER with no reconstruction needed -- unlike the
# capital, this mesh degrades gracefully under decimation at every ratio
# tested (0.5/0.25/0.1/0.05, confirmed by rendering each, not just checking
# face counts). That is very likely because this is a shallow relief carving
# with a consistent front-facing normal, unlike the capital's deep undercut/
# folded-back acanthus geometry -- Collapse struggles specifically with
# undercuts, not organic detail in general. 0 non-manifold at every tier.
LEAFSCROLL_MASTER_LOD1 = os.path.join(MASTERS, "leafscroll-master-lod1.blend")  # ratio 0.25, 38,089 faces
LEAFSCROLL_MASTER_LOD2 = os.path.join(MASTERS, "leafscroll-master-lod2.blend")  # ratio 0.10, 15,235 faces
LEAFSCROLL_MASTER_LOD3 = os.path.join(MASTERS, "leafscroll-master-lod3.blend")  # ratio 0.05,  7,618 faces

# -v10 is a mesh-integrity repair chain on the original donor capital, all via
# scoped local welds (never a mesh-wide weld, never a fill operator -- see
# scripts/repair_capital_seam.py, repair_capital_leafgaps3.py,
# repair_capital_leafgaps4.py, repair_capital_final_cleanup.py,
# repair_capital_loose.py for the per-step record). Same shape, same
# shaft/interior hollow, far cleaner mesh: 575 boundary edges -> 11, 120
# non-manifold -> 1, 74 loose verts / 7 loose edges -> 0. Three "rebuild the
# whole surface" alternatives were tried and rejected first -- Solidify
# (both modes) spikes catastrophically on this mesh's sharp undercuts, and
# Mesh to Volume -> Volume to Mesh produces a visibly torn/fragmented result
# despite reporting perfect numeric closure -- so this mesh's zero-thickness,
# deeply-undercut leaf geometry needs the scoped-weld approach, not a
# volumetric one. v0 through v9 were superseded intermediate repair steps;
# deleted (this repo has no git, so this and other "older iteration" cleanups
# noted throughout this file happened only once each file's successor was
# confirmed working, 2026-08-09).
CAPITAL_MASTER_V10 = os.path.join(MASTERS, "corinthian-capital-master-v10.blend")

CAPITAL_MASTER = CAPITAL_MASTER_V10
CAPITAL_MASTER_OBJECT = "CORINTHIAN_CAPITAL_MASTER"

# CAPITAL_MASTER_RENDER is v10 with every face that is never visible from any
# realistic outside viewpoint removed (scripts/strip_capital_interior.py):
# same silhouette and detail (confirmed via a 14-angle before/after render
# comparison, pixel-identical), 248,899 -> 152,249 faces. It is a single-
# sided open shell where the invisible backside used to be, which is exactly
# right for real-time/game use and exactly wrong for STL/printing -- use
# CAPITAL_MASTER (closed, v10) for anything that needs a solid mesh, and
# this one as the base for every real-time LOD tier. Stripping the interior
# also more than doubled how far Decimate's Collapse algorithm can reduce
# this mesh before hitting its structural floor (23,403 faces on v10 -> 9,156
# on this file), which is why it goes first in the LOD chain rather than
# decimating v10 directly.
CAPITAL_MASTER_RENDER = os.path.join(MASTERS, "corinthian-capital-master-v11.blend")

# CAPITAL_MASTER_LOD1: the straight-decimate route was rejected (first attempt,
# scripts/build_capital_lod1.py -- itself deleted 2026-08-09 in a cleanup pass,
# before its rejected-approach status was checked; see docs/PIPELINE-GUIDE.md
# S15 for the finding, which survives there and in ROADMAP.md). Blender's
# Collapse decimate degrades badly on this mesh's deep acanthus/volute carving
# even at mild ratios (still spiky at 76,123 faces, only 2x reduction), so it
# is not viable at any ratio, not just near the structural floor.
#
# What worked instead: bake the real surface detail onto a smooth low-poly
# proxy as a normal map, rather than decimating the organic surface directly.
# scripts/build_capital_proxy.py builds the proxy (coarse Voxel Remesh of
# CAPITAL_MASTER, which tessellates evenly and has bounded local curvature,
# then Collapse decimate on THAT smooth result -- not the spiky original --
# down to masters/corinthian-capital-proxy-lod1.blend, 3,842 faces).
# scripts/bake_capital_normal.py then UV-unwraps it and bakes a 2048x2048
# normal map from CAPITAL_MASTER_RENDER (Cycles, selected-to-active) onto it.
# Result: 0 boundary/non-manifold, reads as full detail under render --
# volutes, rosette and acanthus leaves all legible, no spikes. This was built
# and verified 2026-08-09 but never wired to this constant until the same day's
# repo cleanup found the file sitting unreferenced in masters/ -- a real,
# confirmed-working asset that documentation had simply fallen behind.
CAPITAL_MASTER_LOD1 = os.path.join(MASTERS, "corinthian-capital-lod1-baked.blend")
CAPITAL_MASTER_LOD1_OBJECT = "CORINTHIAN_CAPITAL_PROXY_LOD1"

# LION_MASTER / LION_MASTER_OBJECT are the pair the frieze scripts actually
# load, so swapping the lion is a change here and nowhere else.
#
# masters/Leeds-lion-mask-master.blend (the original third-party asset, built
# from donors/lion_head.glb, Leeds Libraries, CC BY 4.0) was deleted 2026-08-09
# as a superseded iteration once the Tripo lion was fully promoted -- this
# comment is now the only place that attribution lives. The raw donor file
# (donors/lion_head.glb) is untouched, so the asset itself is still there if
# the Leeds mask is ever wanted back; it would just need re-welding, same as
# the Tripo lion's own -v1 rebuild path (see below).
LION_MASTER_LEEDS_OBJECT = "LEEDS_LION_MASK_MASTER"
# The object name is shared by every Tripo lion master, which is what makes
# swapping between them a one-line change. The pre-weld -v1 file was deleted
# 2026-08-08; build_tripo_lion_master.py rebuilds it from donors/lion.glb if it
# is ever wanted back.
LION_MASTER_TRIPO_OBJECT = "TRIPO_LION_MASK_MASTER"

# -v2 is the same lion, same half, same proportions, rebuilt on the fixed recipe
# (weld before decimate -- see donor_prep.py). Identical shape, far better mesh:
# 31,051 boundary holes -> 246, 5,174 duplicate verts -> 0, 45 loose -> 0. Object
# name is deliberately the same, so this is a one-line swap either way.
LION_MASTER_TRIPO_V2 = os.path.join(MASTERS, "Tripo-lion-mask-master-v2.blend")

# -v3 is scripts/repair_masters.py's easy pass on v2: the narrow 1e-7..1e-6 weld
# search that built v2 left real cracks a wider search closes. 246 boundary -> 100,
# 251 non-manifold -> 100, same shape (weld only merges truly coincident verts).
# v2 is kept on disk, superseded but not deleted -- this repo has no git, so a
# deletion here would not be recoverable the way earlier "delete the superseded
# file" cleanups were.
LION_MASTER_TRIPO_V3 = os.path.join(MASTERS, "Tripo-lion-mask-master-v3.blend")

# -v4 closes v3's remaining 100 boundary / 100 non-manifold edges
# (scripts/repair_lion.py): same defect shape as the leafscroll's (a sliver
# triangle at each of 51 spots contributing one closed boundary loop plus
# its own pair of non-manifold edges), same union-find scoped self-collapse
# fix -- boundary 100 -> 0, non-manifold 100 -> 0, faces 99,787 -> 99,506,
# confirmed shape-identical by render. v3 kept on disk, superseded but not
# deleted.
LION_MASTER_TRIPO_V4 = os.path.join(MASTERS, "Tripo-lion-mask-master-v4.blend")

# -v5 is v4 with multi-viewpoint visibility culling applied
# (scripts/strip_lion_interior.py, prep_lion()'s 180deg Z rotation makes raw
# -Y the visible/front axis -- opposite sign from the leafscroll's 90deg
# rotation). Yield was tiny: 99,506 -> 99,099 faces (0.4%), because this mask
# is a thin shell with almost no backing mass, unlike the leafscroll's solid
# molding strip -- confirmed harmless (0 non-manifold, clean render) and kept
# for consistency even though the real reduction lever for this asset is
# decimation, not culling.
LION_MASTER_TRIPO_V5 = os.path.join(MASTERS, "Tripo-lion-mask-master-v5.blend")

LION_MASTER = LION_MASTER_TRIPO_V5
LION_MASTER_OBJECT = LION_MASTER_TRIPO_OBJECT

# Resolution tiers (scripts/build_lion_lods.py), straight Collapse decimation
# of LION_MASTER at the same ratios as the leafscroll's, chosen after
# rendering each candidate: 0.5/0.25 read as essentially full detail, 0.1 is
# visibly but coherently faceted, 0.05 is the roughest usable tier (mane
# curls get spiky, rougher than the leafscroll's equivalent tier but not
# broken -- this mask has real sculptural undercuts, unlike the leafscroll's
# shallow relief). 0 non-manifold at every tier.
LION_MASTER_LOD1 = os.path.join(MASTERS, "Tripo-lion-mask-master-lod1.blend")  # ratio 0.25, 24,777 faces
LION_MASTER_LOD2 = os.path.join(MASTERS, "Tripo-lion-mask-master-lod2.blend")  # ratio 0.10,  9,911 faces
LION_MASTER_LOD3 = os.path.join(MASTERS, "Tripo-lion-mask-master-lod3.blend")  # ratio 0.05,  4,955 faces

# --- the temple ---
# CORNICE_CLEAN is the preserved pre-donor state: do not overwrite it.
CORNICE_CLEAN = os.path.join(TEMPLE_MODEL, "Pulgas-Water-Temple-live-cornice-refined.blend")
CORNICE_WITH_LION = os.path.join(TEMPLE_MODEL, "Pulgas-Water-Temple-live-cornice-with-lion.blend")

# --- the upstream sequence, which runs BEFORE the frieze chain ---
#
#   CORNICE_WITH_LION                     (preserved original)
#     -> swap_corinthian_capitals.py  ->  CORNICE_WITH_NEW_CAPITALS
#     -> narrow_columns.py            ->  CORNICE_COLUMNS_NARROWED
#     -> detail_central_well.py       ->  CORNICE_WELL_DETAILED  == CHAIN_BASE
#
# It runs upstream because thicken_drum.py derives the drum's inner radius from
# the capitals', so a capital change invalidates the chain from step 2 onward.
#
# Only the two ends are kept on disk. The two middle files were deleted
# 2026-08-08 as reproducible -- re-run the three scripts in the order above to
# regenerate them, which takes a couple of minutes. Anything that reads a middle
# file will fail until you do.
CORNICE_WITH_NEW_CAPITALS = os.path.join(
    TEMPLE_MODEL, "Pulgas-Water-Temple-live-cornice-with-lion-newcapitals.blend")

# Columns narrowed to 90% width at unchanged height and position, requested
# after comparison with the real temple. Runs after the capital swap and, like
# it, upstream of the frieze chain.
CORNICE_COLUMNS_NARROWED = os.path.join(
    TEMPLE_MODEL, "Pulgas-Water-Temple-live-cornice-with-lion-newcapitals-narrow90.blend")

# Central well head detailed: chevron braid band a quarter down from the top on
# both faces, plus a separate cap course of twelve flat stones. Adds only new
# geometry -- the well wall itself is untouched.
CORNICE_WELL_DETAILED = os.path.join(
    TEMPLE_MODEL,
    "Pulgas-Water-Temple-live-cornice-with-lion-newcapitals-narrow90-well.blend")

# Replaces "Inscription drum with 150-percent inset quotation" (the real
# Pulgas Water Temple's engraved Isaiah 43:19-20 quotation) with a plain,
# unlettered wall (scripts/build_plain_drum.py) -- requested 2026-08-09.
# Rebuilt from primitives rather than edited in place: pushing the inset-text
# vertices back out to the wall radius and dissolving the now-coplanar faces
# left shading/faceting ghosts of the old letters even after clearing the
# mesh's baked custom split normals -- same failure family as the leafscroll's
# rejected flat-plane cut and the capital's Solidify spikes, fighting existing
# topology instead of replacing it. The rebuild is a plain outer wall tube
# plus top/bottom rim annuli at the exact measured radii (r=0.282 inner,
# r=0.286 outer, z 0.198-0.313), 0 boundary/non-manifold/loose beyond the two
# inner-rim circles thicken_drum.py and fix_drum_wall_and_ring_seating.py
# already expect to find there. 45,786 -> 1,080 faces. The object was renamed
# "Plain drum wall" (the old name stopped being true); both of those two
# scripts' lookups were updated to match.
CORNICE_PLAIN_DRUM = os.path.join(
    TEMPLE_MODEL,
    "Pulgas-Water-Temple-live-cornice-with-lion-newcapitals-narrow90-well-plaindrum.blend")

CHAIN_BASE = CORNICE_PLAIN_DRUM

# The drum's inner-wall radius. This is DERIVED from the capitals' inner radius:
# the drum has to be thick enough to cover the capitals below it, or they read as
# sitting proud of the wall they are supposed to be holding up. Three chain steps
# need it (thicken_drum, fix_drum_wall_and_ring_seating, fix_top_shelf_and_embed_v3)
# and each used to carry its own copy of 0.204 -- so the capital swap moved one
# and left the other two behind, and the chain broke at step 4 looking for a
# vertex ring that was no longer where it expected.
#
# Re-measure, do not guess: swap_corinthian_capitals.py and narrow_columns.py
# both print the value at the end of their run.
#   0.204   procedural capitals (original)
#   0.1972  Temple-of-Vesta capitals at full width
#   0.2023  the same capitals with columns narrowed to 90%
DRUM_INNER_R = 0.2023

# --- reference imagery ---
REF_CORNICE_PHOTO = os.path.join(REFERENCE, "pulgas-cornice-photo.png")
REF_ANTHEMION = os.path.join(REFERENCE, "anthemion-plaque-reference.png")
REF_TEMPLE = os.path.join(REFERENCE, "pulgas-temple-reference.png")

# --- donors ---
LION_DONOR_GLB = os.path.join(DONORS, "lion_head.glb")


# --- the frieze build chain ---
# The chain is a linked list of .blend checkpoints: frieze-v1 -> frieze-ring ->
# frieze-ring-thick-drum -> -v2 -> -v3 -> -v4 -> -v5, each script opening the
# previous file and saving to the next. Every filename is derived here.
#
# CHAIN_SUFFIX used to also carry a lion-master tag ("-tripo2") and a
# base-chain tag ("-newcap90well-plaindrum"), back when more than one lion
# and more than one upstream base were live candidates being compared side
# by side -- the whole point of "put the build's identity in the filename"
# (see docs/PIPELINE-GUIDE.md S17) is that two builds that can actually
# differ must not overwrite each other. Retired 2026-08-10: the Leeds lion
# and every superseded base file are gone, LION_MASTER and CHAIN_BASE each
# resolve to exactly one file, and a tag that can only ever take one value
# is not identity, it's noise. If a second lion or base candidate is ever
# built again for real comparison, reintroduce a tag for it then -- do not
# pre-emptively restore this dict for a variant that does not exist yet.

# --- frieze element scale ---
# FRIEZE_SCALE multiplies every element's size. The angular layout (36 deg
# lion-to-lion, 18 deg lion-to-anthemion) is architecturally fixed to the ten
# column axes and deliberately does NOT scale, so reducing this shrinks the
# ornaments in place and opens the gaps between them rather than moving anything.
# Elements are seated bottom-down on Z_BASELINE, so shrinking pulls the top of
# the ring away from the structure's top (z 0.395) and leaves the bottom put.
#
# ANTHEMION_SCALE is a second, independent knob for the anthemion alone -- it is
# the tallest element and therefore the one that sets the ring's top edge.
FRIEZE_SCALE = 0.90
ANTHEMION_SCALE = 1.0


def _pct_tag(prefix, value):
    return "" if abs(value - 1.0) < 1e-9 else f"-{prefix}{round(value * 100)}"


# What's left of the chain's identity: the two knobs that can still actually
# differ between runs. Tags vanish entirely at their default (1.0 = 100%), so
# an unscaled build's filename carries no suffix at all.
CHAIN_SUFFIX = _pct_tag("s", FRIEZE_SCALE) + _pct_tag("a", ANTHEMION_SCALE)


def chain_blend(stem):
    """Path to a checkpoint in the frieze chain, e.g. chain_blend('frieze-ring-v5')."""
    return os.path.join(
        TEMPLE_MODEL, f"Pulgas-Water-Temple-live-cornice-{stem}{CHAIN_SUFFIX}.blend")


def chain_render(stem):
    """Matching render output directory for a chain step."""
    return os.path.join(RENDERS, f"{stem}{CHAIN_SUFFIX}")


def lod_blend(tier):
    """Path to a resolution tier, e.g. lod_blend("base") or lod_blend("lod2")."""
    return os.path.join(LOD, f"Pulgas-Water-Temple-{tier}{CHAIN_SUFFIX}.blend")


def round_sig(n, sig=2):
    """Round n to `sig` significant figures. round_sig(569412, 2) -> 570000."""
    if n <= 0:
        return 0
    d = math.ceil(math.log10(n))
    power = sig - d
    factor = 10 ** power
    return round(n * factor) / factor


def triangle_label(n_triangles):
    """Total triangle count -> a rounded human tag, e.g. 569412 -> "570k",
    7397068 -> "7.4m". Two significant figures -- precise enough to tell tiers
    apart, coarse enough that a rebuild which shifts the true count by a few
    hundred triangles does not rename the file.
    """
    r = round_sig(n_triangles, 2)
    if r >= 1_000_000:
        val = r / 1_000_000
        s = f"{val:.1f}".rstrip("0").rstrip(".")
        return f"{s}m"
    if r >= 1_000:
        return f"{int(r // 1000)}k"
    return str(int(r))


def lod_tri_blend(n_triangles):
    """Path to an LOD tier named by its actual measured triangle count, e.g.
    lod570k -- see triangle_label(). Named after the fact (from the real
    decimation result), not before it, so the filename is never a target that
    the build missed.
    """
    return lod_blend(f"lod{triangle_label(n_triangles)}")


def ensure(path):
    os.makedirs(path, exist_ok=True)
    return path
