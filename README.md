# Pulgas Water Temple viewer

This repository is a GitHub Pages-ready mobile model viewer. Export the finished Blender model as `assets/temple.glb` and enable Pages from the repository's Actions or Pages settings.

The published web variant uses a plain stone drum because the original inscription lettering was fused into a damaged decimated mesh and could not be separated reliably.

Live viewer: https://boxwrench.github.io/water_temple/

The viewer uses Google's `<model-viewer>` component for touch controls, responsive layout, and optional AR. The source Blender files are kept separately because browsers cannot display `.blend` files directly.

## Blender export

Use **File → Export → glTF 2.0 → glTF Binary (.glb)**. Export the temple as `assets/temple.glb`; apply modifiers and embed textures. For phones, optimize textures and geometry before publishing.
