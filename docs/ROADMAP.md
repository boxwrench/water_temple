# Roadmap

Future work that's been decided but deliberately not started. Add the
decision and the reason; leave it here until picked up.

---

## Rebuild the Corinthian capital from primitives

**Not started — explicitly deferred, do not pick this up without being asked.**

The current capital master (donor-sourced, repaired across v0→v11 this
session — see `docs/PIPELINE-GUIDE.md` §13/§15 for the repair and LOD work)
is judged too rough to keep pushing further as-is. Baking its detail onto a
low-poly proxy (`masters/corinthian-capital-lod1-baked.blend`) works and
reads correctly at distance, but the underlying shape itself — the donor's
organic, deeply undercut, non-uniform carving — is the thing making every
downstream step (Collapse decimation, Solidify, Mesh to Volume, even Voxel
Remesh for a bake proxy) fight the geometry rather than simplify it.

The plan: use the current capital purely as visual/dimensional reference and
**rebuild it from primitives** — a parametric/lofted construction (matching
the project's own established pattern for clean, defect-free geometry: the
well's braid and cap course, built as closed swept outlines, audited at 0
boundary edges / 0 non-manifold / 0 duplicates *by construction*, not by
repair — `PIPELINE-GUIDE.md` §9). A primitive-built capital would be
LOD-friendly from the start: clean topology decimates predictably, and there
would be no donor-mesh defects to repair in the first place.

Scope note: this is a real modeling task (loft the bell profile, the
volutes, the acanthus tiers, the abacus), not a quick script — expect it to
be comparable in effort to the anthemion's from-photo build in
`PIPELINE-GUIDE.md` §3.
