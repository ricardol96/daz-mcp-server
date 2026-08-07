"""Render tools for the Vangard DAZ MCP server."""
from __future__ import annotations

import asyncio
import os
from typing import Any

import httpx
from fastmcp.exceptions import ToolError

from .._mcp import mcp, _execute_by_id, _execute_by_id_async, _execute_render, _execute_render_batch
from .._client import get_http_client
from .._errors import handle_network_error, check_response


# ---------------------------------------------------------------------------
# Synchronous render tools
# ---------------------------------------------------------------------------

@mcp.tool()
async def daz_render(
    output_path: str | None = None,
) -> dict[str, Any]:
    """Trigger a render in DAZ Studio using the current render settings.

    Render dimensions, format, and other options are whatever is currently
    configured in DAZ Studio's Render Settings panel.

    Args:
        output_path: Optional absolute path for the output image
                     (e.g. "C:/renders/scene.png"). If omitted, DAZ Studio
                     uses its currently configured output path.

    Returns:
      - success: true when the render was launched without error
    """
    args: dict[str, Any] = {}
    if output_path is not None:
        args["outputPath"] = output_path
    return await _execute_by_id("vangard-render", args or None)


@mcp.tool()
async def daz_render_with_camera(
    camera_label: str,
    output_path: str | None = None,
) -> dict[str, Any]:
    """Render from specific camera without changing active viewport camera.

    Renders the scene from the specified camera's viewpoint. The viewport camera
    remains unchanged, making this ideal for multi-camera renders without
    disrupting the user's viewport.

    Args:
        camera_label: Display label of the camera to render from.
        output_path: Optional output file path. If not specified, renders to viewport.

    Returns:
      - success: true on success
      - camera: camera label used for render
      - outputPath: output file path (or null if rendered to viewport)

    Example:
        # Render from specific camera
        daz_render_with_camera("Camera 1", output_path="/path/to/render.png")

        # Render from multiple cameras without changing viewport
        cameras = ["Front", "Side", "Top", "Perspective"]
        for cam in cameras:
            daz_render_with_camera(cam, output_path=f"renders/{cam}.png")

        # Test render from camera (to viewport, no file)
        daz_render_with_camera("Camera 1")

    Note:
        - Viewport camera remains unchanged after render
        - Previous render camera is restored automatically
        - Use for multi-camera batch renders
        - Combine with daz_orbit_camera_around() to set up camera first
    """
    args: dict[str, Any] = {"cameraLabel": camera_label}
    if output_path is not None:
        args["outputPath"] = output_path

    return await _execute_by_id("vangard-render-with-camera", args)


# ---------------------------------------------------------------------------
# Color grading + Iray post-process tools
# ---------------------------------------------------------------------------

@mcp.tool()
async def daz_apply_tone_mapping(
    tone_mapping_enable: int | None = None,
    exposure_value: float | None = None,
    shutter_speed: float | None = None,
    aperture: float | None = None,
    film_iso: int | None = None,
    cm2_factor: float | None = None,
    vignetting: float | None = None,
    white_point_scale: float | None = None,
    white_point_color: list[float] | None = None,
    burn_highlights_per_component: int | None = None,
    burn_highlights: float | None = None,
    crush_blacks: float | None = None,
    saturation: float | None = None,
    gamma: float | None = None,
) -> dict[str, Any]:
    """Set Iray photographic tone-mapping values (color grading).

    This is the primary color-grading surface in DAZ Studio's Iray. It targets
    the "Tonemapper Options" node and configures the photographic tone mapper,
    which is modeled on real camera exposure: Exposure Value (EV), Shutter Speed,
    Aperture, Film ISO, plus grading controls like Saturation, Gamma, Vignetting,
    Burn Highlights, Crush Blacks, and White Point (RGB). Iray's tone mapper
    runs after the path-traced render and is the equivalent of a "color grade"
    pass — the same render at different tone-map settings looks like a
    different photo (cinematic, soft, noir, etc.).

    All arguments are optional; only the ones you pass are written. This lets
    you tweak a single value (e.g. just `saturation=1.4`) without touching the
    rest. Use `daz_apply_photographic_look(preset)` for a one-shot tuned look.

    Args:
        tone_mapping_enable: 0 = off (linear), 1 = on (photographic). Default
            in DAZ is 0; you almost always want 1 to actually grade.
        exposure_value: Brightness in stops (EV). Typical 8–18. Default 13.
            Lower = darker; higher = brighter.
        shutter_speed: Reciprocal exposure time. Higher = darker. Common: 100,
            125, 200. Default 128.
        aperture: f-stop. Lower = brighter. Common: 1.4, 2.0, 2.8, 5.6. Default 8.
        film_iso: Sensor sensitivity. Higher = brighter + more noise. Common:
            100, 200, 400, 800. Default 100.
        cm2_factor: Conversion factor used internally for unit conversion.
            Default 1.0; rarely changed.
        vignetting: 0..1; amount of edge darkening. Default 0.
        white_point_scale: 0..2; how strongly the white-point tint is applied.
            Default 1.0.
        white_point_color: [r, g, b] in 0..1; the white-point tint itself
            (warm = [1.0, 0.92, 0.78], cool = [0.86, 0.90, 1.0],
            neutral = [1.0, 1.0, 1.0]).
        burn_highlights_per_component: 0 = luma burn, 1 = per-channel. Default 1.
        burn_highlights: 0..1; how aggressively to compress highlights.
            Default 1.0 (no extra burn beyond the natural response).
        crush_blacks: 0..1; how much to crush blacks (lift the toe). 0 = no
            crush (linear), 0.4 = filmic. Default 0.
        saturation: 0 = monochrome, 1 = neutral, 1.4 = boosted. Default 1.
        gamma: Display gamma. 1.0 = linear, 2.2 = sRGB. Default 2.2.

    Returns:
        - applied: list of {name, value} actually written
        - not_found: properties that didn't exist (e.g. a property renamed
          across Iray versions)
        - current: snapshot of all tone-mapping properties after the write
    """
    args: dict[str, Any] = {}
    if tone_mapping_enable is not None: args["tone_mapping_enable"] = int(tone_mapping_enable)
    if exposure_value is not None: args["exposure_value"] = float(exposure_value)
    if shutter_speed is not None: args["shutter_speed"] = float(shutter_speed)
    if aperture is not None: args["aperture"] = float(aperture)
    if film_iso is not None: args["film_iso"] = int(film_iso)
    if cm2_factor is not None: args["cm2_factor"] = float(cm2_factor)
    if vignetting is not None: args["vignetting"] = float(vignetting)
    if white_point_scale is not None: args["white_point_scale"] = float(white_point_scale)
    if white_point_color is not None: args["white_point_color"] = list(white_point_color)
    if burn_highlights_per_component is not None: args["burn_highlights_per_component"] = int(burn_highlights_per_component)
    if burn_highlights is not None: args["burn_highlights"] = float(burn_highlights)
    if crush_blacks is not None: args["crush_blacks"] = float(crush_blacks)
    if saturation is not None: args["saturation"] = float(saturation)
    if gamma is not None: args["gamma"] = float(gamma)
    return await _execute_by_id("vangard-apply-tone-mapping", args)


@mcp.tool()
async def daz_apply_photographic_look(preset: str) -> dict[str, Any]:
    """Apply a named photographic color-grade preset (one-shot for tuned Iray looks).

    Presets are tuned combinations of Exposure Value, Shutter, Aperture, ISO,
    Saturation, Gamma, Vignetting, Burn Highlights, Crush Blacks, and a warm
    or cool White Point — the same controls you can set individually with
    `daz_apply_tone_mapping`, but packaged as an opinionated starting point.

    Available presets:
        - golden_hour: warm low-sun look, soft saturation, mild vignetting
        - moody_noir: dark, low-key, desaturated, strong vignetting, cool cast
        - high_key: bright, airy, low contrast, soft skin
        - low_key: dark dramatic key, deep shadows, warm accent
        - vintage_film: faded film, lower saturation, slight cool white
        - fashion_editorial: crisp, neutral, high-detail editorial
        - cinematic_teal_orange: Hollywood blockbuster, mid contrast
        - soft_portrait: beauty/portrait, even, low contrast
        - dramatic_mono: black & white dramatic, high contrast

    Args:
        preset: One of the preset names listed above.

    Returns:
        - preset, description: what was applied
        - applied: list of {name, value} written
        - not_found: any properties that didn't exist on the live Iray

    Example:
        daz_apply_photographic_look("golden_hour")
    """
    return await _execute_by_id("vangard-apply-photographic-look", {"preset": preset})


@mcp.tool()
async def daz_set_environment_visibility(
    environment_mode: int | None = None,
    draw_dome: int | None = None,
    dome_mode: int | None = None,
    environment_intensity: float | None = None,
    dome_rotation: float | None = None,
    environment_map: int | None = None,
    environment_tint: list[float] | None = None,
    draw_ground: int | None = None,
    ss_time: float | None = None,
    ss_sun_disk_intensity: float | None = None,
    ss_latitude: float | None = None,
    ss_longitude: float | None = None,
    ss_day: int | None = None,
    dome_scale_multiplier: float | None = None,
) -> dict[str, Any]:
    """Control how the HDRI environment appears in the render.

    This is what makes the difference between "HDR lighting the scene with
    black background" and "HDR visible as a backdrop behind the subject".
    Targets the "Environment Options" node.

    Args:
        environment_mode: 0 = Dome Only, 1 = Dome and Scene, 2 = Sun-Sky Only,
            3 = Scene Only (lighting only — no visible dome). Most portraits
            want 0 (Dome Only, the HDR shows as background).
        draw_dome: 0 = don't draw the dome (black background), 1 = draw it.
        dome_mode: 0 = Finite Dome (a sphere geometry), 1 = Infinite Dome
            (sky shader). For HDRIs you usually want 1.
        environment_intensity: Multiplier on the environment light. 0 = off,
            1 = scene default. 1.2–1.6 = brighter HDR.
        dome_rotation: Yaw rotation in degrees. Spin the dome around the
            character without reloading the HDR.
        environment_map: 0 = Original, 1 = Spherical, 2 = Mirror Ball.
            Leave at the default the HDR was loaded with unless you want
            a different projection.
        environment_tint: [r, g, b] in 0..1; multiplies the environment light.
        draw_ground: 0 = invisible ground plane, 1 = visible.
        ss_time: Sun-Sky time of day in seconds-from-midnight (0–86400).
        ss_sun_disk_intensity: 0 = no sun disk, >0 = visible sun.
        ss_latitude: Sun-Sky latitude in degrees.
        ss_longitude: Sun-Sky longitude in degrees.
        ss_day: Sun-Sky day of year as Julian date (e.g. 2459000 ≈ mid-2020).
        dome_scale_multiplier: How large the finite dome is. Default 100.

    Returns:
        - applied, not_found, current: see `daz_apply_tone_mapping`.
    """
    args: dict[str, Any] = {}
    if environment_mode is not None: args["environment_mode"] = int(environment_mode)
    if draw_dome is not None: args["draw_dome"] = int(draw_dome)
    if dome_mode is not None: args["dome_mode"] = int(dome_mode)
    if environment_intensity is not None: args["environment_intensity"] = float(environment_intensity)
    if dome_rotation is not None: args["dome_rotation"] = float(dome_rotation)
    if environment_map is not None: args["environment_map"] = int(environment_map)
    if environment_tint is not None: args["environment_tint"] = list(environment_tint)
    if draw_ground is not None: args["draw_ground"] = int(draw_ground)
    if ss_time is not None: args["ss_time"] = float(ss_time)
    if ss_sun_disk_intensity is not None: args["ss_sun_disk_intensity"] = float(ss_sun_disk_intensity)
    if ss_latitude is not None: args["ss_latitude"] = float(ss_latitude)
    if ss_longitude is not None: args["ss_longitude"] = float(ss_longitude)
    if ss_day is not None: args["ss_day"] = int(ss_day)
    if dome_scale_multiplier is not None: args["dome_scale_multiplier"] = float(dome_scale_multiplier)
    return await _execute_by_id("vangard-set-environment-visibility", args)


@mcp.tool()
async def daz_apply_environment_look(preset: str) -> dict[str, Any]:
    """Apply a named environment preset (golden_hour, blue_hour, midday, overcast, night).

    Convenience wrapper over `daz_set_environment_visibility` that sets the
    Environment Mode, Draw Dome, Intensity, Dome Rotation, and Sun-Sky time
    to approximate a real time of day so the HDR backdrop + sun position
    feel coherent.

    Args:
        preset: "golden_hour" | "blue_hour" | "midday" | "overcast" | "night"

    Returns:
        - preset, description, applied, not_found
    """
    return await _execute_by_id("vangard-apply-environment-look", {"preset": preset})


@mcp.tool()
async def daz_set_advanced_iray_settings(
    max_samples: int | None = None,
    render_quality: float | None = None,
    max_time: int | None = None,
    filter_type: int | None = None,
    pixel_size: float | None = None,
    denoiser: int | None = None,
    caustics: int | None = None,
) -> dict[str, Any]:
    """Set advanced Iray render options: samples, denoiser, caustics, pixel filter.

    Args:
        max_samples: Cap on path-tracing samples. Higher = cleaner + slower.
            Typical: 1000 (preview), 5000 (good), 20000 (final), 50000 (hero).
        render_quality: 0..1; DAZ's "Render Quality" slider. 1.0 = max
            convergence aggressiveness.
        max_time: Cap in seconds. 0 = no cap.
        filter_type: Pixel reconstruction filter index. 0=Box, 1=Triangle,
            2=Gaussian, 3=Mitchell, 4=Lanczos. 3 (Mitchell) is a good default.
        pixel_size: Pixel reconstruction size; 1.5–2.5 is a good range for
            smoothing without over-blurring.
        denoiser: 0/1 to enable OptiX/NVIDIA denoiser. Available on
            Iray versions that expose it.
        caustics: 0/1 to enable caustics (slow but lovely for glass/water).

    Returns:
        - applied, not_found, current
    """
    args: dict[str, Any] = {}
    if max_samples is not None: args["max_samples"] = int(max_samples)
    if render_quality is not None: args["render_quality"] = float(render_quality)
    if max_time is not None: args["max_time"] = int(max_time)
    if filter_type is not None: args["filter_type"] = int(filter_type)
    if pixel_size is not None: args["pixel_size"] = float(pixel_size)
    if denoiser is not None: args["denoiser"] = int(denoiser)
    if caustics is not None: args["caustics"] = int(caustics)
    return await _execute_by_id("vangard-set-advanced-iray", args)


@mcp.tool()
async def daz_get_color_grade_settings() -> dict[str, Any]:
    """Snapshot the current Tonemapper, Environment, and Iray render settings.

    Returns a dict with three keys: `tonemapper`, `environment`, `iray`, each
    containing the live numeric property values from those settings nodes.
    Useful before applying a tone-map preset to confirm the prior state.
    """
    return await _execute_by_id("vangard-get-color-grade-settings", None)


# ---------------------------------------------------------------------------
# Viewport screenshots (for iterative scene setup)
#
# Use daz_viewport_screenshot() to grab the active 3D viewport with the
# "NVIDIA Iray" Draw Style so the AI can see what the user sees. The image
# is saved to disk and the tool returns a compact result — never the raw
# pixel bytes — so the AI context stays small. If `gpt_api_key` is set,
    # a short GPT vision critique is also
# returned so the AI can decide what to tweak without you needing to look at
# the image yourself.
#
# Workflow during scene setup:
#   1. daz_apply_lighting_preset("rembrandt")   # or any other tweak
#   2. daz_viewport_screenshot(out)             # capture (waits for Iray to converge)
#   3. Read the returned `critique` and adjust
#   4. Repeat
# ---------------------------------------------------------------------------

def _gpt_critique_screenshot(
    image_path: str,
    question: str = "Critique this DAZ Studio render for composition, lighting, "
                    "exposure, color balance, and any obvious issues. Be concise "
                    "(3-5 short bullet points) and suggest concrete parameter tweaks "
                    "the user can apply to improve it.",
    model: str = "gpt-4o-mini",
    max_tokens: int = 400,
) -> str | None:
    """Return a short GPT vision critique of a local image, or None on failure.

    Reads the OpenAI key from ``gpt_api_key`` in the environment. Returns
    None if the key is missing or the API call fails — never raises, so
    the screenshot tool still works without a key.

    Default model is ``gpt-4o-mini`` ($0.15/$0.60 per 1M tokens). For a
    low-res 480x270 critique the cost is well under $0.0003 per call
    regardless of model. Override with a higher tier if you need better
    critique quality:

      - gpt-4o-mini   ($0.15/$0.60)   — default, good balance
      - gpt-4.1-nano  ($0.10/$0.40)   — cheapest vision model, less nuanced
      - gpt-5-nano    ($0.05/$0.40)   — even cheaper, newer/unproven
      - gpt-5-mini    ($0.25/$2.00)   — strong general model
      - gpt-4o        ($2.50/$10.00)  — best quality, ~25x cost
    """
    import base64
    import os
    api_key = os.environ.get("gpt_api_key")
    if not api_key:
        return None
    try:
        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
    except OSError:
        return None
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": question},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{b64}",
                            "detail": "low",
                        },
                    },
                ],
            }
        ],
    }
    try:
        with httpx.Client(timeout=60.0) as c:
            r = c.post(
                "https://api.openai.com/v1/chat/completions",
                json=payload,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
            )
            r.raise_for_status()
            data = r.json()
        return data["choices"][0]["message"]["content"].strip()
    except Exception:
        return None


@mcp.tool()
async def daz_set_viewport_draw_style(style: str) -> dict[str, Any]:
    """Set the active 3D viewport's Draw Style (preview quality).

    Useful before taking a screenshot so the viewport shows the same look the
    final render will. Pass an alias or a raw DAZ Studio label.

    Aliases (case-insensitive): "wireframe", "wire_bounding_box",
    "smooth_shaded", "texture_shaded", "iray".

    Raw DAZ labels (any of these works): "Wireframe", "Wire Bounding Box",
    "Smooth Shaded", "Texture Shaded", "NVIDIA Iray".

    Args:
        style: Alias or raw label (default: "iray" for photoreal preview).

    Returns:
        - style: the resolved label
        - before, after: the actual viewport state before/after the call
    """
    aliases = {
        "wireframe": "Wireframe",
        "wire_bounding_box": "Wire Bounding Box",
        "smooth_shaded": "Smooth Shaded",
        "texture_shaded": "Texture Shaded",
        "iray": "NVIDIA Iray",
    }
    resolved = aliases.get(style.strip().lower(), style)
    from .._client import get_http_client
    import json
    client = get_http_client()
    script = f"""
        (function(){{
            var iface = App.getInterface();
            var vp = iface.getViewportMgr().getActiveViewport().get3DViewport();
            if (!vp) return null;
            var before = vp.getUserDrawStyle();
            vp.setUserDrawStyle({json.dumps(resolved)});
            return {{before: before, after: vp.getUserDrawStyle()}};
        }})()
    """
    r = await client.post("/execute", json={"script": script})
    r.raise_for_status()
    res = r.json().get("result")
    if not isinstance(res, dict):
        return {"error": f"viewport unavailable (got {type(res).__name__}: {res!r})"}
    if res.get("after") != resolved and res.get("after") == res.get("before"):
        return {"error": f"unknown draw style: {style!r}", "style": style,
                "before": res.get("before"), "after": res.get("after")}
    return {"style": res.get("after"), "before": res.get("before"),
            "after": res.get("after")}


@mcp.tool()
async def daz_get_viewport_draw_style() -> dict[str, Any]:
    """Return the active 3D viewport's current Draw Style label + size."""
    from .._client import get_http_client
    import json as _json
    client = get_http_client()
    script = """
        (function(){
            var iface = App.getInterface();
            var vpm = iface.getViewportMgr();
            if (!vpm) return null;
            var vp = vpm.getActiveViewport();
            if (!vp) return null;
            var threeD = vp.get3DViewport();
            if (!threeD) return null;
            return {
                drawStyle: threeD.getUserDrawStyle(),
                width: threeD.width,
                height: threeD.height
            };
        })()
    """
    r = await client.post("/execute", json={"script": script})
    r.raise_for_status()
    res = r.json().get("result")
    if not isinstance(res, dict):
        return {"available": False}
    return {
        "draw_style": res.get("drawStyle"),
        "size": {"width": res.get("width"), "height": res.get("height")},
        "available": True,
    }


@mcp.tool()
async def daz_viewport_screenshot(
    output_path: str,
    width: int = 480,
    height: int = 270,
    camera: str | None = None,
    iray_samples: int = 800,
    max_time: int = 60,
    tone_preset: str | None = None,
    env_preset: str | None = None,
    critique: bool = True,
    critique_model: str = "gpt-4o-mini",
    critique_focus: str | None = None,
) -> dict[str, Any]:
    """Quick low-resolution Iray "preview" for iterative scene setup.

    This is the iterative-scene-setup workhorse. Sets the viewport's Draw
    Style to NVIDIA Iray, then triggers a fast low-resolution Iray render
    (default 480x270 at 800 samples, ~2-5s) so the AI can see what the user
    sees, then optionally asks GPT-4o-mini for a short text critique so the
    AI can decide what to tweak next WITHOUT having to load the image itself.

    Why a low-res render rather than a literal viewport capture: this DAZ
    Studio instance (BETA SDK6) doesn't expose ``Dz3DViewport.updateGL()``,
    so the live Iray preview framebuffer is empty when grabbed from a
    script. A 480x270 Iray render hits the same engine, same look, finishes
    in seconds, and writes a real PNG to disk — which the GPT-4o-mini
    vision can then critique.

    The image bytes are NEVER returned in the AI context — only the path,
    size, dimensions, and (if requested) a < 400-token critique string. This
    keeps scene-iteration cheap even if you grab 10 screenshots in a row.

    Args:
        output_path: Absolute path for the PNG. Parent directory will be
            created if missing. ".png" or ".jpg" extension.
        width: Preview width in pixels (default 480 — small for speed).
            Use 1920+ for a near-final pass.
        height: Preview height in pixels (default 270).
        camera: Camera node label to render from. If None, uses the current
            active camera.
        iray_samples: Max samples cap. Default 800 — fast for previews.
            Bump to 5000+ when the scene is close to final.
        max_time: Max time in seconds (default 60).
        tone_preset: Optional photographic-look preset to apply first
            (e.g. "golden_hour"). Same as in daz_render_shot.
        env_preset: Optional environment-look preset (e.g. "golden_hour").
        critique: If True AND `gpt_api_key` is set in env, returns a short
            GPT vision critique so the AI can refine the scene without
            seeing the image itself. Costs <$0.0003 per 480x270 call with
            the default model (gpt-4o-mini). Pass `critique_model` to pick
            a different tier.
        critique_focus: Optional extra prompt text for the critique, e.g.
            "Focus on the subject's face — is the lighting too flat?"

    Returns:
        - file_path, file_size_bytes, width, height
        - camera, iray_samples, duration_ms: the actual settings used
        - critique: short text critique (or null if disabled / no key / error)
        - critique_error: present if the critique failed

    Example (iterative setup):
        daz_apply_lighting_preset("rembrandt", subject_label="Genesis 8 Female")
        daz_set_active_camera("HeroCam")
        daz_viewport_screenshot("C:/renders/setup1.png")
        # → returns critique; adjust based on it
        daz_apply_tone_mapping(saturation=1.4, burn_highlights=0.85)
        daz_viewport_screenshot("C:/renders/setup2.png", tone_preset="golden_hour")
        # → returns new critique; iterate
    """
    from .._mcp import _execute_render

    # Set Draw Style to NVIDIA Iray (best preview quality)
    try:
        await daz_set_viewport_draw_style("iray")
    except Exception:
        pass

    # Apply tone_preset / env_preset if provided (so the render shows the look)
    if env_preset:
        try:
            await daz_apply_environment_look(env_preset)
        except Exception:
            pass
    if tone_preset:
        try:
            await daz_apply_photographic_look(tone_preset)
        except Exception:
            pass

    # Build params for the native /render endpoint
    import os as _os
    p_dir = _os.path.dirname(output_path)
    if p_dir:
        _os.makedirs(p_dir, exist_ok=True)

    render_result: dict[str, Any] = {}
    try:
        async_res = await _execute_render({
            "output_path": output_path,
            "width": width,
            "height": height,
            "engine": "iray",
            "iray_samples": iray_samples,
            **({"camera": camera} if camera else {}),
            **({"max_time": max_time} if max_time else {}),
        })
        req_id = async_res.get("request_id")
        if req_id:
            render_result = await daz_get_request_result(req_id, wait=True)
        else:
            render_result = async_res
    except Exception as exc:
        return {
            "error": f"render failed: {exc}",
            "output_path": output_path,
        }

    if render_result.get("error") or render_result.get("success") is False:
        return {
            "error": render_result.get("error", "render failed"),
            "output_path": output_path,
            "render": render_result,
        }

    file_size = _os.path.getsize(output_path) if _os.path.exists(output_path) else 0
    result: dict[str, Any] = {
        "file_path": output_path,
        "file_size_bytes": file_size,
        "width": width,
        "height": height,
        "camera": camera,
        "iray_samples": iray_samples,
        "duration_ms": render_result.get("duration_ms"),
        "render": render_result,
    }
    if critique:
        question = (
            "Critique this DAZ Studio render (Iray photoreal preview). Be "
            "concise: 3-5 short bullet points on composition, lighting, "
            "exposure, color balance, and any obvious issues. Suggest concrete "
            "parameter tweaks the user can apply (e.g. 'increase key light "
            "flux to 4000', 'lower env intensity to 0.5', 'rotate camera "
            "15° left')."
        )
        if critique_focus:
            question += " Extra focus: " + critique_focus
        text = _gpt_critique_screenshot(output_path, question=question,
                                       model=critique_model)
        if text is None:
            if not _os.environ.get("gpt_api_key"):
                result["critique_error"] = "gpt_api_key not set in env"
            else:
                result["critique_error"] = "GPT call failed (see logs)"
        else:
            result["critique"] = text
    return result


@mcp.tool()
async def daz_critique_viewport(
    image_path: str,
    focus: str | None = None,
    model: str = "gpt-4o-mini",
) -> dict[str, Any]:
    """Get a GPT vision critique of an existing local screenshot.

    Use this on a screenshot you already saved (e.g. from a prior
    `daz_viewport_screenshot` call) to get a second opinion or a focused
    critique on a specific concern.

    Args:
        image_path: Absolute path to a PNG/JPG on disk.
        focus: Optional question/topic to focus the critique on, e.g.
            "Is the face well lit?" or "Critique the composition only."
        model: OpenAI vision model (default "gpt-4o-mini" — good balance
            of quality and cost, $0.15/$0.60 per 1M tokens). Use "gpt-4o"
            for higher quality or "gpt-4.1-nano" for the cheapest tier.
            See `_gpt_critique_screenshot` for full tier list.

    Returns:
        - critique: short text critique
        - file_size_bytes, model
        - error: present if the call failed
    """
    if not os.path.exists(image_path):
        return {"error": f"file not found: {image_path}"}
    if not os.environ.get("gpt_api_key"):
        return {"error": "gpt_api_key not set in environment"}
    question = (
        "Critique this DAZ Studio render (saved viewport capture). Be concise: "
        "3-5 short bullet points on composition, lighting, exposure, color, "
        "and any obvious issues. Suggest concrete tweaks the user can apply."
    )
    if focus:
        question = focus
    text = _gpt_critique_screenshot(image_path, question=question, model=model)
    if text is None:
        return {"error": "GPT call failed", "model": model,
                "file_path": image_path,
                "file_size_bytes": os.path.getsize(image_path)}
    return {"critique": text, "model": model, "file_path": image_path,
            "file_size_bytes": os.path.getsize(image_path)}


@mcp.tool()
async def daz_render_shot(
    output_path: str,
    width: int = 1280,
    height: int = 720,
    camera: str | None = None,
    quality: str = "good",
    engine: str = "iray",
    iray_samples: int | None = None,
    tone_preset: str | None = None,
    env_preset: str | None = None,
    max_time: int | None = None,
) -> dict[str, Any]:
    """High-level render helper: configure and render a still, then verify it.

    Wraps scene-health check, render-output/dimension setup, camera selection,
    quality/engine, an optional photographic color-grade preset, an optional
    environment preset, an async render-with-wait, and file verification, so
    the AI can produce a usable, color-graded image in one call.

    Args:
        output_path: Absolute destination path (e.g. "C:/renders/hero.png").
                    Format from extension (.png/.jpg).
        width: Render width in pixels (default 1280).
        height: Render height in pixels (default 720).
        camera: Camera node label to render from (e.g. "Camera 1 [Front]"). If
                omitted, uses the current active viewport camera.
        quality: Render quality preset passed to daz_set_render_quality
                 ("draft", "low", "good", "high", "final", "highest").
        engine: Passed to the async render params ("iray", "nvidia").
        iray_samples: Optional explicit Max Samples cap. If set, overrides the
            quality preset. Use 1000 (preview) / 5000 (good) / 20000+ (final).
        tone_preset: Optional name passed to `daz_apply_photographic_look`
            (e.g. "golden_hour", "moody_noir", "cinematic_teal_orange"). Applies
            BEFORE the render so the final pixels are graded.
        env_preset: Optional name passed to `daz_apply_environment_look`
            (e.g. "golden_hour", "midday"). Sets Environment Mode/Draw Dome so
            the HDR backdrop is visible and the sun position matches.
        max_time: Optional Max Time cap in seconds.

    Returns:
        - output_path, width, height: actual settings used
        - file_exists, file_size_bytes: verification the image was written
        - render: the underlying render result (camera, duration_ms, ...)
        - scene_health: scene-health snapshot before rendering
        - tone_preset_applied, env_preset_applied: which presets were used

    Example:
        daz_render_shot(
            "C:/renders/hero.png", width=1920, height=1080,
            camera="HeroCam", iray_samples=5000,
            tone_preset="golden_hour", env_preset="golden_hour",
        )
    """
    import asyncio
    import os
    from pathlib import Path

    from .._mcp import _execute_render

    # 0) Optional scene-health preamble (best-effort; never fail on it).
    scene_health: dict[str, Any] | None = None
    tone_preset_applied: dict[str, Any] | None = None
    env_preset_applied: dict[str, Any] | None = None
    advanced_applied: dict[str, Any] | None = None
    try:
        from .scene import daz_scene_health

        scene_health = await daz_scene_health()
    except Exception:
        scene_health = None

    # 0.5) Optional color-grade + environment + advanced Iray settings.
    #      Order matters: env preset first (so the HDR backdrop is visible),
    #      then tone-map preset (so the grade applies to the final pixels).
    if env_preset:
        try:
            env_preset_applied = await daz_apply_environment_look(env_preset)
        except Exception as exc:
            env_preset_applied = {"error": str(exc), "preset": env_preset}
    if tone_preset:
        try:
            tone_preset_applied = await daz_apply_photographic_look(tone_preset)
        except Exception as exc:
            tone_preset_applied = {"error": str(exc), "preset": tone_preset}
    if iray_samples is not None or max_time is not None:
        try:
            advanced_applied = await daz_set_advanced_iray_settings(
                max_samples=iray_samples, max_time=max_time
            )
        except Exception as exc:
            advanced_applied = {"error": str(exc)}

    # 1) Configure output + dimensions.
    output_dir = Path(output_path).parent
    if not output_dir.exists():
        output_dir.mkdir(parents=True, exist_ok=True)
    await daz_set_render_output(output_path=output_path, width=width, height=height)

    # 2) Quality (best-effort; some presets may not exist on custom engines).
    #    Skipped if an explicit iray_samples was passed (advanced settings
    #    already wrote Max Samples).
    if quality and iray_samples is None:
        try:
            await daz_set_render_quality(quality)
        except Exception:
            pass

    # 3) Camera + engine go straight into the async render invocation.
    params: dict[str, Any] = {
        "output_path": output_path,
        "width": width,
        "height": height,
        "engine": engine,
    }
    if camera:
        params["camera"] = camera
    if iray_samples is not None:
        params["iray_samples"] = iray_samples

    render_result: dict[str, Any] = {}
    try:
        async_res = await _execute_render(params)
        req_id = async_res.get("request_id")
        if req_id:
            render_result = await daz_get_request_result(req_id, wait=True)
        else:
            render_result = async_res
    except Exception as exc:
        render_result = {
            "error": str(exc),
            "note": "Async render failed; output config was still applied.",
        }

    # 4) Verify output file.
    size = os.path.getsize(output_path) if os.path.exists(output_path) else 0
    return {
        "output_path": output_path,
        "width": width,
        "height": height,
        "file_exists": os.path.exists(output_path),
        "file_size_bytes": size,
        "camera": camera,
        "iray_samples": iray_samples,
        "scene_health": scene_health,
        "tone_preset_applied": tone_preset_applied,
        "env_preset_applied": env_preset_applied,
        "advanced_applied": advanced_applied,
        "render": render_result,
    }


@mcp.tool()
async def daz_get_render_settings() -> dict[str, Any]:
    """Get current render settings and configuration.

    Returns information about the current render configuration, including
    render target, output path, aspect ratio, and render camera.

    Returns:
      - renderToFile: true if rendering to file, false if to viewport
      - outputPath: current output file path (or null)
      - currentCamera: label of current render camera (or null for viewport camera)
      - aspectRatio: aspect ratio value
      - aspectWidth: aspect width component
      - aspectHeight: aspect height component

    Example:
        # Check render settings
        settings = daz_get_render_settings()
        print(f"Render camera: {settings['currentCamera']}")
        print(f"Output: {settings['outputPath']}")
        print(f"Aspect: {settings['aspectWidth']}x{settings['aspectHeight']}")

        # Verify render is configured correctly before batch render
        settings = daz_get_render_settings()
        if not settings['renderToFile']:
            print("Warning: Render is configured for viewport, not file output")

    Note:
        - Aspect ratio determines render dimensions relative to each other
        - Pixel dimensions cannot be set reliably via DazScript
        - currentCamera may be null if using active viewport camera
    """
    return await _execute_by_id("vangard-get-render-settings", {})


@mcp.tool()
async def daz_batch_render_cameras(
    cameras: list[str],
    output_dir: str,
    base_filename: str = "render",
) -> dict[str, Any]:
    """Render from multiple cameras in sequence.

    Renders the same scene from multiple camera angles in a single operation.
    Each camera generates a separate output file with the camera name appended.

    Args:
        cameras: List of camera labels to render from.
        output_dir: Output directory for rendered images.
        base_filename: Base filename (default: "render"). Camera name is appended automatically.

    Returns:
      - success: true on success
      - rendered: Array of {camera, outputPath} objects
      - total: Total number of cameras attempted

    Example:
        # Render from multiple preset cameras
        daz_batch_render_cameras(
            cameras=["Front", "Side", "Top", "Perspective"],
            output_dir="/path/to/renders",
            base_filename="character"
        )
        # Generates: character_Front.png, character_Side.png, etc.

        # Render turntable (8 cameras around character)
        cameras = [f"Cam_{angle}" for angle in [0, 45, 90, 135, 180, 225, 270, 315]]
        daz_batch_render_cameras(cameras, "/path/to/turntable", "frame")

        # Render all cameras in scene
        scene_info = daz_scene_info()
        all_cameras = [cam['label'] for cam in scene_info['cameras']]
        daz_batch_render_cameras(all_cameras, "/path/to/renders")

    Note:
        - Camera names in filenames have non-alphanumeric chars replaced with underscores
        - All renders use current scene state (same lighting, poses, etc.)
        - Previous render camera is restored after batch completes
        - Cameras that don't exist are skipped
    """
    return await _execute_by_id(
        "vangard-batch-render-cameras",
        {
            "cameras": cameras,
            "outputDir": output_dir,
            "baseFilename": base_filename,
        },
    )


@mcp.tool()
async def daz_render_animation(
    output_dir: str,
    start_frame: int | None = None,
    end_frame: int | None = None,
    filename_pattern: str = "frame",
    camera: str | None = None,
) -> dict[str, Any]:
    """Render animation frame range as image sequence.

    Renders each frame of an animation to separate image files. Automatically
    advances through frames and generates zero-padded filenames for proper
    sorting. This is the recommended way to export animations.

    Args:
        output_dir: Output directory for rendered frames.
        start_frame: First frame to render (default: animation range start).
        end_frame: Last frame to render (default: animation range end).
        filename_pattern: Filename pattern (default: "frame"). Frame number is appended.
        camera: Optional camera label to render from (default: current render camera).

    Returns:
      - success: true on success
      - rendered: Array of {frame, outputPath} objects
      - total: Total number of frames rendered
      - frames: {start, end} frame range rendered

    Example:
        # Render entire animation
        daz_render_animation(output_dir="/path/to/animation")
        # Generates: frame_0000.png, frame_0001.png, ..., frame_0119.png

        # Render specific frame range
        daz_render_animation(
            output_dir="/path/to/animation",
            start_frame=30,
            end_frame=60,
            filename_pattern="clip"
        )

        # Render animation from specific camera
        daz_render_animation(
            output_dir="/path/to/animation",
            camera="Camera 1"
        )

        # Render preview (every 5th frame)
        info = daz_get_animation_info()
        for frame in range(info['startFrame'], info['endFrame'] + 1, 5):
            daz_render_animation(
                output_dir="/path/to/preview",
                start_frame=frame,
                end_frame=frame,
                filename_pattern=f"preview_frame"
            )

    Note:
        - Frame numbers are zero-padded to 4 digits (0000, 0001, etc.)
        - Current timeline frame is restored after render completes
        - If camera is specified, render camera is restored after completion
        - Use daz_get_animation_info() to get default frame range
        - Convert to video: ffmpeg -framerate 30 -i frame_%04d.png output.mp4
    """
    args: dict[str, Any] = {
        "outputDir": output_dir,
        "filenamePattern": filename_pattern,
    }
    if start_frame is not None:
        args["startFrame"] = start_frame
    if end_frame is not None:
        args["endFrame"] = end_frame
    if camera is not None:
        args["camera"] = camera

    return await _execute_by_id("vangard-render-animation", args)


# ---------------------------------------------------------------------------
# Async render tools
# ---------------------------------------------------------------------------

@mcp.tool()
async def daz_render_async(
    output_path: str,
    width: int | None = None,
    height: int | None = None,
    camera: str | None = None,
    engine: str | None = None,
    iray_samples: int | None = None,
) -> dict[str, Any]:
    """Start a render asynchronously via the dedicated render endpoint — returns immediately.

    Uses POST /render directly, which supports native render parameters and
    proper cancellation via daz_cancel_request(). Cancel IDs returned here have
    the prefix "rnd-" and are routed to /render/:id/cancel automatically.

    Use daz_get_request_status() to poll and daz_get_request_result() for the result.

    IMPORTANT: The scene is locked while the render runs. Do not modify the
    scene until the request status is "completed", "failed", or "cancelled".

    Args:
        output_path: Absolute file path for the rendered image (required).
        width: Render width in pixels. Must be paired with height.
        height: Render height in pixels. Must be paired with width.
        camera: Camera label to render from (default: active render camera).
        engine: Render engine — "iray", "3delight", or "filament".
        iray_samples: Iray max samples (overrides current quality settings).

    Returns:
        {"request_id": "rnd-XXXXXXXX", "status": "queued", "submitted_at": "..."}
    """
    params: dict[str, Any] = {"output_path": output_path}
    if width is not None:
        params["width"] = width
    if height is not None:
        params["height"] = height
    if camera is not None:
        params["camera"] = camera
    if engine is not None:
        params["engine"] = engine
    if iray_samples is not None:
        params["iray_samples"] = iray_samples
    return await _execute_render(params)


@mcp.tool()
async def daz_render_with_camera_async(
    camera_label: str,
    output_path: str,
    width: int | None = None,
    height: int | None = None,
    engine: str | None = None,
    iray_samples: int | None = None,
) -> dict[str, Any]:
    """Start a camera-specific render asynchronously — returns immediately with a request_id.

    Convenience wrapper over daz_render_async that pins the camera. Renders from
    the specified camera without changing the active viewport camera.

    Args:
        camera_label: Display label of the camera to render from.
        output_path: Absolute file path for the rendered image.
        width: Render width in pixels (must pair with height).
        height: Render height in pixels (must pair with width).
        engine: Render engine — "iray", "3delight", or "filament".
        iray_samples: Iray max samples override.

    Returns:
        {"request_id": "rnd-XXXXXXXX", "status": "queued", "submitted_at": "..."}
    """
    params: dict[str, Any] = {"output_path": output_path, "camera": camera_label}
    if width is not None:
        params["width"] = width
    if height is not None:
        params["height"] = height
    if engine is not None:
        params["engine"] = engine
    if iray_samples is not None:
        params["iray_samples"] = iray_samples
    return await _execute_render(params)


@mcp.tool()
async def daz_batch_render_cameras_async(
    cameras: list[str],
    output_dir: str,
    base_filename: str = "render",
    engine: str | None = None,
    iray_samples: int | None = None,
) -> dict[str, Any]:
    """Queue renders from multiple cameras as a validated batch.

    Uses POST /render/batch which validates ALL cameras before enqueuing any render.
    This is all-or-nothing: if any camera name is invalid the entire batch is rejected.

    Args:
        cameras: List of camera display labels.
        output_dir: Directory where rendered images are saved.
        base_filename: Filename prefix. Output is <base_filename>_<camera>.png.
        engine: Render engine for all variants — "iray", "3delight", or "filament".
        iray_samples: Iray max samples override for all variants.

    Returns:
        {
            "request_ids": ["rnd-XXXXXXXX", ...],
            "total": 3,
            "cameras": ["Cam_0", "Cam_45", "Cam_90"]
        }

    Example:
        batch = await daz_batch_render_cameras_async(
            cameras=["Cam_0", "Cam_45", "Cam_90"],
            output_dir="C:/renders/turntable"
        )
        for req_id in batch["request_ids"]:
            result = await daz_get_request_result(req_id, wait=True)
    """
    base: dict[str, Any] = {}
    if engine is not None:
        base["engine"] = engine
    if iray_samples is not None:
        base["iray_samples"] = iray_samples

    variants = [
        {"output_path": os.path.join(output_dir, f"{base_filename}_{cam}.png"), "camera": cam}
        for cam in cameras
    ]
    body: dict[str, Any] = {"variants": variants}
    if base:
        body["base"] = base

    data = await _execute_render_batch(body)
    return {
        "request_ids": data.get("request_ids", []),
        "total": data.get("total", len(cameras)),
        "cameras": cameras,
    }


@mcp.tool()
async def daz_render_batch(
    variants: list[dict[str, Any]],
    base: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Submit a batch of render variants — validated and queued atomically.

    Uses POST /render/batch. All variants are validated before any render is
    enqueued (all-or-nothing). Renders execute serially but are each independently
    cancellable via daz_cancel_request().

    Args:
        variants: List of render specs. Each must include ``output_path``. Optional
                  per-variant overrides: ``width``, ``height``, ``camera``, ``engine``,
                  ``iray_samples``, ``figure``/``figures``, ``morphs``.
        base: Default settings shared by all variants. Same keys as variants. Overridden
              by any key present in the variant itself.

    Returns:
        {
            "request_ids": ["rnd-XXXXXXXX", ...],
            "total": 5
        }

    Example — product photography with expression variants:
        daz_render_batch(
            base={"figure": "Genesis 9", "width": 1920, "height": 1080},
            variants=[
                {"output_path": "C:/out/neutral.png", "morphs": {"Smile": 0.0}},
                {"output_path": "C:/out/smile.png",   "morphs": {"Smile": 1.0}},
                {"output_path": "C:/out/serious.png", "morphs": {"Brow Down": 0.5}},
            ]
        )
    """
    body: dict[str, Any] = {"variants": variants}
    if base is not None:
        body["base"] = base
    return await _execute_render_batch(body)


@mcp.tool()
async def daz_render_animation_async(
    output_dir: str,
    start_frame: int | None = None,
    end_frame: int | None = None,
    filename_pattern: str = "frame",
    camera: str | None = None,
) -> dict[str, Any]:
    """Start an animation render asynchronously — returns immediately with a request_id.

    Queues a full animation render (all frames as an image sequence). This can
    take hours; use daz_get_request_status() to monitor progress and
    daz_get_request_result() to confirm completion.

    Args:
        output_dir: Directory where frame images are saved.
        start_frame: First frame (default: animation range start).
        end_frame: Last frame (default: animation range end).
        filename_pattern: Filename prefix (default: "frame"). Frame number appended.
        camera: Optional camera label (default: current render camera).

    Returns:
        {"request_id": "script-XXXXXXXX", "status": "queued", "submitted_at": "..."}
    """
    args: dict[str, Any] = {
        "outputDir": output_dir,
        "filenamePattern": filename_pattern,
    }
    if start_frame is not None:
        args["startFrame"] = start_frame
    if end_frame is not None:
        args["endFrame"] = end_frame
    if camera is not None:
        args["camera"] = camera
    return await _execute_by_id_async("vangard-render-animation", args)


# ---------------------------------------------------------------------------
# Request management tools
# ---------------------------------------------------------------------------

@mcp.tool()
async def daz_get_request_status(request_id: str) -> dict[str, Any]:
    """Get the current status of an async request (non-blocking, always fast).

    Safe to call frequently — reads directly from the server's in-memory map
    without executing any DazScript.

    Args:
        request_id: Request ID returned by an async submission tool.

    Returns:
        {
            "request_id": "script-XXXXXXXX",
            "status": "running",   # queued | running | completed | failed | cancelled
            "progress": 0.0,       # 0.0 while running (DAZ single-frame renders have no
                                   # mid-frame progress), 1.0 when complete
            "elapsed_ms": 45000,   # present while running
            "queue_position": 2    # present while queued
        }
    """
    client = get_http_client()
    try:
        response = await client.get(f"/requests/{request_id}/status")
    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.TimeoutException) as exc:
        handle_network_error(exc)
    if response.status_code == 404:
        raise ToolError(f"Request not found: {request_id}")
    check_response(response)
    return response.json()


@mcp.tool()
async def daz_get_request_result(
    request_id: str,
    wait: bool = True,
    timeout_seconds: int = 3600,
) -> dict[str, Any]:
    """Get the result of a completed async request.

    Args:
        request_id: Request ID returned by an async submission tool.
        wait: If True (default), block until the request finishes (up to timeout).
              If False, return immediately with current status even if not done.
        timeout_seconds: Max seconds to wait when wait=True (default 3600 = 1 hour).

    Returns when complete:
        {
            "request_id": "script-XXXXXXXX",
            "status": "completed",
            "success": true,
            "result": {...},        # same as sync tool result
            "output": [...],        # captured DazScript print() output
            "error": null,
            "duration_ms": 267000,
            "completed_at": "2026-04-08T..."
        }

    Raises ToolError if the request failed.
    """
    client = get_http_client()
    params: dict[str, Any] = {
        "wait": "true" if wait else "false",
        "timeout": timeout_seconds,
    }
    try:
        response = await client.get(
            f"/requests/{request_id}/result",
            params=params,
            timeout=timeout_seconds + 10.0,  # slightly longer than server timeout
        )
    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.TimeoutException) as exc:
        handle_network_error(exc)
    check_response(response)

    data = response.json()
    status = data.get("status", "unknown")
    if status == "failed":
        raise ToolError(f"Async request failed: {data.get('error', 'unknown error')}")
    if status == "cancelled":
        return data
    return data


@mcp.tool()
async def daz_cancel_request(request_id: str) -> dict[str, Any]:
    """Cancel a queued or running async request.

    For queued requests: cancellation is immediate.
    For running renders: sends a killRender() signal to DAZ Studio; may take a
    few seconds to take effect as the renderer finishes the current tile.

    Render requests (IDs starting with "rnd-") are routed to POST /render/:id/cancel
    which issues killRender(). Script requests use DELETE /requests/:id.

    Args:
        request_id: Request ID returned by an async submission tool
                    (e.g. "rnd-XXXXXXXX" from daz_render_async,
                     "script-XXXXXXXX" from _execute_by_id_async).

    Returns:
        {"request_id": "...", "status": "cancelled", "cancelled_at": "..."}

    Raises ToolError if the request is already finished (completed/failed/cancelled)
    or not found.
    """
    client = get_http_client()
    try:
        if request_id.startswith("rnd-"):
            response = await client.post(f"/render/{request_id}/cancel")
        else:
            response = await client.delete(f"/requests/{request_id}")
    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.TimeoutException) as exc:
        handle_network_error(exc)
    if response.status_code == 404:
        raise ToolError(f"Request not found: {request_id}")
    check_response(response)
    return response.json()


@mcp.tool()
async def daz_list_requests(
    status_filter: str | None = None,
) -> dict[str, Any]:
    """List all tracked async requests and their current statuses.

    Args:
        status_filter: Optional filter — one of "queued", "running",
                       "completed", "failed", "cancelled". Returns all if omitted.

    Returns:
        {
            "requests": [
                {"request_id": "...", "status": "...", "progress": 0.0, "submitted_at": "..."},
                ...
            ],
            "total": 5,
            "queued": 2,
            "running": 1,
            "completed": 2,
            "failed": 0,
            "cancelled": 0
        }
    """
    client = get_http_client()
    params: dict[str, Any] = {}
    if status_filter is not None:
        params["status"] = status_filter
    try:
        response = await client.get("/requests", params=params)
    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.TimeoutException) as exc:
        handle_network_error(exc)
    check_response(response)
    return response.json()


# ---------------------------------------------------------------------------
# Render quality preset
# ---------------------------------------------------------------------------

@mcp.tool()
async def daz_set_render_quality(preset: str) -> dict[str, Any]:
    """Set the Iray render quality preset.

    Adjusts Max Samples and Render Quality on the active renderer, trading
    speed for quality. Use "draft" for quick composition checks and "final"
    for production renders.

    Presets:
        draft   - Very fast (seconds–2 min). Low quality. For quick checks.
        preview - Fast (2–5 min). Moderate quality. For composition review.
        good    - Slow (10–20 min). Good quality. For client review.
        final   - Very slow (30 min–2 hr). Maximum quality. For final output.

    Args:
        preset: One of "draft", "preview", "good", "final".

    Returns:
        {
            "preset": "draft",
            "propertiesSet": [
                {"property": "Max Samples", "value": 100},
                {"property": "Render Quality", "value": 0.5}
            ],
            "note": "..."    # present only if some properties were not found
        }

    Example:
        # Quick test render
        daz_set_render_quality("draft")
        daz_render("/test.png")

        # Final quality async render
        daz_set_render_quality("final")
        req = await daz_render_async("/final.png")
        result = await daz_get_request_result(req["request_id"], wait=True)
    """
    _presets: dict[str, dict[str, float]] = {
        "draft":   {"maxSamples": 100,  "renderQuality": 0.5},
        "preview": {"maxSamples": 500,  "renderQuality": 0.75},
        "good":    {"maxSamples": 2000, "renderQuality": 0.9},
        "final":   {"maxSamples": 5000, "renderQuality": 1.0},
    }
    if preset not in _presets:
        valid = ", ".join(f'"{k}"' for k in _presets)
        raise ToolError(f"Unknown render quality preset: '{preset}'. Valid presets: {valid}")

    args = {"preset": preset, **_presets[preset]}
    return await _execute_by_id("vangard-set-render-quality", args)


# ---------------------------------------------------------------------------
# Poll helper (not an MCP tool — for use in Python scripts)
# ---------------------------------------------------------------------------

async def daz_wait_for_request(
    request_id: str,
    poll_interval_seconds: float = 5.0,
    timeout_seconds: float = 3600.0,
) -> dict[str, Any]:
    """Poll an async request until it completes (or times out).

    Polls daz_get_request_status() every poll_interval_seconds until the
    request reaches a terminal state, then returns the full result.

    Args:
        request_id: Request ID from an async submission tool.
        poll_interval_seconds: Seconds between status checks (default 5).
        timeout_seconds: Maximum total wait time (default 3600 = 1 hour).

    Returns:
        Full result dict from daz_get_request_result() on success.

    Raises:
        ToolError: If the request failed or was cancelled.
        asyncio.TimeoutError: If the timeout is exceeded.
    """
    import time
    deadline = time.monotonic() + timeout_seconds

    while True:
        status = await daz_get_request_status(request_id)
        state = status.get("status", "unknown")

        if state == "completed":
            return await daz_get_request_result(request_id, wait=False)
        if state == "failed":
            raise ToolError(f"Async request failed: {status.get('error', 'unknown error')}")
        if state == "cancelled":
            return status

        if time.monotonic() >= deadline:
            raise asyncio.TimeoutError(
                f"Async request {request_id!r} did not complete within {timeout_seconds}s"
            )

        await asyncio.sleep(poll_interval_seconds)


# ---------------------------------------------------------------------------
# Render output configuration
# ---------------------------------------------------------------------------

@mcp.tool()
async def daz_set_render_output(
    output_path: str | None = None,
    width: int | None = None,
    height: int | None = None,
) -> dict[str, Any]:
    """Configure render output path and/or image dimensions.

    At least one of ``output_path``, ``width``, or ``height`` must be provided.
    Unspecified parameters are left unchanged.

    Args:
        output_path: Absolute path for the rendered image file, including
                     extension (e.g. ``"C:/renders/hero_shot.png"``). DAZ Studio
                     determines the format from the extension.
        width: Render image width in pixels.
        height: Render image height in pixels.

    Returns:
        Dict with changed (the settings that were modified) and current
        (the full current render output configuration after changes).

    Examples:
        daz_set_render_output(output_path="C:/renders/scene01.png")
        daz_set_render_output(width=3840, height=2160)           # 4K
        daz_set_render_output("C:/out/final.png", 1920, 1080)   # 1080p with path

    Notes:
        - These settings persist in the DAZ Studio render options for the session.
        - Use daz_render or daz_render_async to trigger the render after setting up.
    """
    if output_path is None and width is None and height is None:
        raise ToolError(
            "At least one of output_path, width, or height must be provided."
        )
    return await _execute_by_id(
        "vangard-set-render-output",
        {"outputPath": output_path, "width": width, "height": height},
    )
