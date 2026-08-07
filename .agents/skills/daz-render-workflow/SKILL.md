---
name: daz-render-workflow
description: Use when building a DAZ Studio scene and rendering an image via this MCP server. Covers the reliable path (inspect asset → load base → apply character → add environment/lighting → render with daz_render_shot) and the known failure traps (partial presets, broken environment .duf with missing textures, resolution through daz_set_render_output).
---

# DAZ Render Workflow

Goal: produce an attractive, correctly-lit rendered image from library assets without
burning time on failed loads or broken assets. All reasoning is deterministic via the
asset-intelligence tools; do not guess paths or load files blindly.

## Golden path (preferred, one shot)

For any character render use this order:

1. `daz_inspect_asset(preset_path)` — classify before opening: returns `kind`,
   `requires_base`, `fits_base`, and texture-existence summary.
   - `kind == "character_set"` (e.g. Carmen, many shop characters) REQUIRES loading a
     base figure first. `fits_base` tells you which generation (e.g. "Genesis 8 Female").
   - `kind == "full_character"` loads standalone; do NOT load a base under it.
   - `kind` in `hair`/`clothing` must be fitted onto the loaded figure.
2. `daz_list_base_figures(generation=<fits_base>)` to locate the base .duf, or let
   `daz_load_character(preset_path)` auto-resolve + load the base for you (it inspects,
   resolves, loads base with `merge=False`, then applies the preset with `merge=True`).
3. Load environment/lighting. Simple reliable sources:
   - `Light Presets/Iray HDR Outdoor Environments/DTHDR-OutdoorA.duf` adds HDR sky +
     several preset cameras.
   - Avoid environment .daz/.duf sets whose textures may not resolve (see Traps).
4. `daz_scene_health()` before rendering: check `render_ready.figure`, `.lights`,
   `.camera`. Add a camera, light, or HDR if missing.
5. Render: `daz_render_shot(output_path, width=1280, height=720, camera=<label>,
   engine="iray")`. It configures output + dimensions, triggers an async render,
   waits, and verifies the file exists. Returns `file_size_bytes` for a sanity check.

## Resolution

- Width/height come from `daz_set_render_output` / `daz_render_shot` — plain
  `daz_render` uses whatever is currently in the Render Settings panel.
- Camera labels are literal strings like `"Camera 1 [Front]"` (from HDR set) or
  `"Perspective"`. Pick the camera in `daz_scene_health`/scene info before rendering.

## Traps / anti-patterns

- Loading a `character_set` preset ON ITS OWN silently creates a partial figure.
  Always put it onto a base (`daz_load_character` handles this).
- A `.duf` environment with references like `/Maps/12_52.jpg` that don't exist on disk
  imports as an empty node and wastes a render. `daz_inspect_asset` shows
  `textures.missing_paths` before you ever load it — check it.
- After `daz_load_file`, inspect `node_delta`: near-zero for a figure/environment means
  the asset didn't actually import. `daz_load_file` returns a `warning` for this.
- `merge=False` REPLACES the whole scene (resets cameras/lights). Load base and env
  order matters: base first (replace), then env/lighting (merge).