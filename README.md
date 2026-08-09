# Pulgas Water Temple viewer

![Pulgas Water Temple browser viewer](docs/viewer-preview.png)

Live viewer: [boxwrench.github.io/water_temple](https://boxwrench.github.io/water_temple/)

## About the temple

The Pulgas Water Temple is a stone structure in Redwood City, California, designed by architect William G. Merchant. The San Francisco Water Department built it to commemorate the 1934 completion of the Hetch Hetchy Aqueduct. The permanent temple was completed in 1938 and consists of a circle of fluted Corinthian columns supporting a large masonry ring; the original ring carried a quotation from Isaiah 43:20. A reflecting pool lined with cypress trees completes the setting. Water no longer flows through the temple, having been diverted to a nearby treatment plant. [Read more on Wikipedia](https://en.wikipedia.org/wiki/Pulgas_Water_Temple).

## This project

This is a browser presentation of a Blender reconstruction/study of the temple. The workflow is:

1. Build and refine the architectural parts in Blender, including the columns, Corinthian capitals, cornice, frieze, well, and ornamental details.
2. Keep editable `.blend` source files and experimental LOD variants in `source/`.
3. Export the selected model to a binary glTF `.glb` for efficient browser delivery.
4. Present the model with Google's [`<model-viewer>`](https://modelviewer.dev/) component, using responsive HTML/CSS, touch orbit, pinch zoom, shadows, auto-rotate, and optional AR.
5. Publish the static viewer and model through GitHub Pages.

The published web variant uses a plain stone drum because the original inscription lettering was fused into a damaged decimated mesh and could not be separated reliably.

## Blender export

Use **File > Export > glTF 2.0 > glTF Binary (.glb)**. Export the temple as `assets/temple.glb`; apply modifiers and embed textures. For phones, optimize textures and geometry before publishing.
