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
   For a one-shot graded render pass `tone_preset="golden_hour"`, `env_preset="golden_hour"`,
   `iray_samples=8000`, `max_time=300`.

## Iterative scene setup with viewport screenshots

For adjusting lighting, camera, color grade BEFORE the final render, take low-res
Iray "previews" via `daz_viewport_screenshot`. This is a fast Iray render at a
small size (default 480x270, ~600 samples, ~8s) that shows exactly what the
final render will look like — same engine, same look, just smaller. The image
is written to disk and the tool returns a compact result:

- `file_path`, `file_size_bytes`, `width`, `height`, `camera`, `iray_samples`,
  `duration_ms`
- `critique` (optional, when `gpt_api_key` is set in env): a < 400-token
  vision critique of the screenshot — so you can iterate without ever
  loading the image into your own context. Default model is **gpt-4o-mini**
  ($0.15/$0.60 per 1M tokens). At 480×270 a single critique costs
  ~$0.0002 (well under a tenth of a cent). Pass `critique_model="gpt-4o"`
  for higher quality at ~25× cost.

Workflow:
1. Set up the scene (env, lighting, camera, tone preset).
2. `daz_viewport_screenshot("C:/renders/preview1.png")` — returns critique.
3. Apply a tweak based on the critique (e.g. raise Key Light flux, lower env
   intensity, swap tone preset).
4. `daz_viewport_screenshot("C:/renders/preview2.png", tone_preset="moody_noir")`
   — returns new critique.
5. Repeat until the critique is clean, then `daz_render_shot(...)` for final.

Why a low-res render rather than a literal viewport capture: this DAZ Studio
BETA SDK6 doesn't expose `Dz3DViewport.updateGL()`, so the live Iray preview
framebuffer is empty when grabbed from a script. A 480x270 Iray render hits
the same engine, finishes in seconds, and writes a real PNG.

Tools:
- `daz_viewport_screenshot(output_path, width=480, height=270, camera=None,
  iray_samples=800, max_time=60, tone_preset=None, env_preset=None,
  critique=True, critique_model="gpt-4o-mini", critique_focus=None)` —
  render the low-res preview + optional GPT critique.
- `daz_set_viewport_draw_style(style)` — set the viewport's preview Draw Style
  ("iray" / "texture_shaded" / "smooth_shaded" / "wireframe" / "wire_bounding_box"
  or a raw DAZ label).
- `daz_get_viewport_draw_style()` — read current Draw Style + viewport size.
- `daz_critique_viewport(image_path, focus=None, model="gpt-4o-mini")` —
  re-critique an existing screenshot (e.g. from a previous call or a saved
  render) with a fresh question.

Vision-model tier guide (cheapest → most capable, all vision-capable):

  | Model           | Input  | Output | Notes                          |
  |-----------------|--------|--------|--------------------------------|
  | gpt-5-nano      | $0.05  | $0.40  | Cheapest; newer/unproven       |
  | gpt-4.1-nano    | $0.10  | $0.40  | Cheaper; fine for simple looks |
  | gpt-4o-mini     | $0.15  | $0.60  | **default**, good balance      |
  | gpt-4.1-mini    | $0.40  | $1.60  |                                |
  | gpt-5-mini      | $0.25  | $2.00  |                                |
  | gpt-4o          | $2.50  | $10.00 | Best quality, ~25× cost        |
  | gpt-5           | $1.25  | $10.00 |                                |

  At 480×270 with detail=low, a single critique is ~500 input + ~200 output
  tokens, so the cost difference between tiers is fractions of a cent. Stick
  with gpt-4o-mini unless you have a specific reason to upgrade.

## Color grading + custom render settings (after step 4, before step 5)

Iray's photographic tone mapper is the primary color-grading surface. The HDR scene
file (e.g. `DTHDR-OutdoorA.duf`) only adds the environment *lighting* by default —
for a backdrop you need to make the dome visible too. Use these tools in order:

- `daz_apply_environment_look(preset)` — set Environment Mode=0 (Dome Only),
  Draw Dome=1, Environment Intensity, Sun-Sky time so the HDR shows as a backdrop.
  Presets: `golden_hour`, `blue_hour`, `midday`, `overcast`, `night`.
- `daz_set_environment_visibility(...)` — fine-grained (Dome Rotation, Dome Scale,
  Environment Tint, Sun-Sky Lat/Long/Time/Intensity/Day).
- `daz_apply_photographic_look(preset)` — tune Exposure Value, Shutter, Aperture,
  Film ISO, Saturation, Gamma, Vignetting, Burn Highlights, Crush Blacks, White Point.
  Presets: `golden_hour`, `moody_noir`, `high_key`, `low_key`, `vintage_film`,
  `fashion_editorial`, `cinematic_teal_orange`, `soft_portrait`, `dramatic_mono`.
- `daz_apply_tone_mapping(...)` — individual knobs when a preset isn't close enough.
- `daz_set_advanced_iray_settings(max_samples=, render_quality=, max_time=,
  filter_type=, pixel_size=, denoiser=, caustics=)` — engine-level overrides.
  Note: `Max Samples`/`Render Quality` properties don't exist on every DAZ version's
  option helper; prefer `iray_samples` in the render params / `daz_render_shot` call.
- `daz_get_color_grade_settings()` — snapshot current Tonemapper / Environment / Iray
  values; useful to confirm a preset was applied or to debug the look.

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