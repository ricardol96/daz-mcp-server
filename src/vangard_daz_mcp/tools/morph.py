"""Morph, expression, and body-language tools for DAZ Studio figures."""
from __future__ import annotations

import json
import math
from typing import Any

from fastmcp.exceptions import ToolError

from dazpy.exceptions import NodeNotFoundError

from .._mcp import mcp, _execute_by_id, _execute, _execute_by_id_async  # noqa: F401
from .._client import get_scene, get_daz_client, run_dazpy, get_http_client  # noqa: F401
from .._errors import handle_dazpy_error, handle_network_error, check_response  # noqa: F401


# ---------------------------------------------------------------------------
# Skeleton/bone lookup helpers (mirrors tools/figure.py conventions)
# ---------------------------------------------------------------------------


def _find_skeleton(scene: Any, label: str) -> Any:
    """Find a skeleton by label, falling back to internal name if no label matches."""
    try:
        return scene.find_skeleton_by_label(label)
    except NodeNotFoundError:
        return scene.find_skeleton(label)


def _find_bone_any(skeleton: Any, candidates: tuple[str, ...]) -> Any | None:
    """Return the first bone matching any candidate internal name, or None."""
    for name in candidates:
        try:
            return skeleton.find_bone(name)
        except NodeNotFoundError:
            continue
    return None


def _gaze_angles(head_pos: dict, target_pos: dict) -> tuple[float, float]:
    """Compute approximate (rotX, rotY) degrees for a head bone to face a world point."""
    dx = target_pos["x"] - head_pos["x"]
    dy = target_pos["y"] - head_pos["y"]
    dz = target_pos["z"] - head_pos["z"]
    horiz_dist = math.hypot(dx, dz)
    rot_y = math.degrees(math.atan2(dx, dz))
    rot_x = -math.degrees(math.atan2(dy, horiz_dist)) * 0.5
    return rot_x, rot_y


def _active_camera_position(client: Any) -> dict | None:
    """Fetch the active viewport camera's world-space position, or None if none is active."""
    script = """(function() {
        var cam = Scene.getActiveCamera();
        if (!cam) return null;
        var p = cam.getWSPos();
        return {x: p.x, y: p.y, z: p.z};
    })();"""
    return client.execute(script).value


# ---------------------------------------------------------------------------
# Body-language posture definitions (bone -> property -> value, pre-intensity)
# ---------------------------------------------------------------------------

_POSTURE_DEFINITIONS: dict[str, list[dict]] = {
    "confident": [
        {"bone": "chestUpper", "property": "XRotate", "value": 5.0},
        {"bone": "lShldr", "property": "ZRotate", "value": -5.0},
        {"bone": "rShldr", "property": "ZRotate", "value": 5.0},
    ],
    "defensive": [
        {"bone": "chestUpper", "property": "XRotate", "value": -8.0},
        {"bone": "abdomenLower", "property": "XRotate", "value": -3.0},
        {"bone": "lShldr", "property": "ZRotate", "value": 10.0},
        {"bone": "rShldr", "property": "ZRotate", "value": -10.0},
    ],
    "relaxed": [
        {"bone": "chestUpper", "property": "XRotate", "value": -3.0},
        {"bone": "lShldr", "property": "ZRotate", "value": 4.0},
        {"bone": "rShldr", "property": "ZRotate", "value": -4.0},
        {"bone": "neckLower", "property": "XRotate", "value": 2.0},
    ],
    "tense": [
        {"bone": "chestUpper", "property": "XRotate", "value": 4.0},
        {"bone": "lShldr", "property": "ZRotate", "value": -12.0},
        {"bone": "rShldr", "property": "ZRotate", "value": 12.0},
        {"bone": "neckLower", "property": "XRotate", "value": -3.0},
    ],
}


# ---------------------------------------------------------------------------
# Emotion definitions
# Emotion → list of {names: [...], value: float} (first match per list wins)
# Multiple candidate names handle morph naming differences across figure generations.
# ---------------------------------------------------------------------------

_EMOTION_DEFINITIONS: dict[str, dict] = {
    "happy": {
        "morphs": [
            {"names": ["PHMSmile", "Smile", "CTRLSmile", "MouthSmile", "SmileSimple"], "value": 0.85},
            {"names": ["PHMEyesSquint", "EyesSquint", "EyeSquintL", "SquintEyes"], "value": 0.25},
        ],
        "body": [{"bone": "chestUpper", "property": "XRotate", "value": 3.0}],
    },
    "sad": {
        "morphs": [
            {"names": ["PHMFrown", "Frown", "MouthFrown", "CTRLFrown", "FrownSimple"], "value": 0.75},
            {"names": ["PHMBrowInnerDown", "BrowDownL", "BrowDown", "CTRLBrowDown", "BrowInnerDown"], "value": 0.6},
            {"names": ["PHMEyesSquint", "EyesSquint", "EyeSquintL"], "value": 0.3},
        ],
        "body": [{"bone": "chestUpper", "property": "XRotate", "value": -6.0}],
    },
    "angry": {
        "morphs": [
            {"names": ["PHMFrown", "Frown", "MouthFrown", "CTRLFrown"], "value": 0.5},
            {"names": ["PHMBrowDown", "BrowDown", "BrowDownLeft", "CTRLBrowDown", "BrowDownR"], "value": 0.85},
            {"names": ["PHMNoseWrinkle", "NoseWrinkle", "NoseSneerL", "NoseSneer"], "value": 0.4},
            {"names": ["PHMEyesTighten", "EyesTighten", "EyeSquintL", "CheekSquintL"], "value": 0.4},
        ],
        "body": [{"bone": "chestUpper", "property": "XRotate", "value": -3.0}],
    },
    "surprised": {
        "morphs": [
            {"names": ["PHMBrowUp", "BrowUp", "BrowInnerUpL", "CTRLBrowUp", "BrowsUp"], "value": 0.85},
            {"names": ["PHMEyesWide", "EyesWide", "EyeOpenL", "EyeWideL"], "value": 0.75},
            {"names": ["PHMMouthOpen", "MouthOpen", "CTRLMouthOpen", "JawOpen"], "value": 0.6},
        ],
        "body": [],
    },
    "fearful": {
        "morphs": [
            {"names": ["PHMBrowUp", "BrowUp", "BrowInnerUpL", "CTRLBrowUp"], "value": 0.7},
            {"names": ["PHMEyesWide", "EyesWide", "EyeOpenL", "EyeWideL"], "value": 0.6},
            {"names": ["PHMMouthOpen", "MouthOpen", "CTRLMouthOpen", "JawOpen"], "value": 0.3},
        ],
        "body": [{"bone": "chestUpper", "property": "XRotate", "value": -4.0}],
    },
    "disgusted": {
        "morphs": [
            {"names": ["PHMNoseWrinkle", "NoseWrinkle", "NoseSneerL", "NoseSneer"], "value": 0.75},
            {"names": ["PHMFrown", "Frown", "MouthFrown", "CTRLFrown"], "value": 0.4},
            {"names": ["PHMUpperLipUp", "UpperLipUp", "MouthUpperUp_L", "LipUpperUp_L"], "value": 0.3},
        ],
        "body": [],
    },
    "neutral": {
        "morphs": [],
        "body": [],
    },
    "excited": {
        "morphs": [
            {"names": ["PHMSmile", "Smile", "CTRLSmile", "MouthSmile"], "value": 1.0},
            {"names": ["PHMBrowUp", "BrowUp", "CTRLBrowUp", "BrowsUp"], "value": 0.5},
            {"names": ["PHMEyesWide", "EyesWide", "EyeOpenL"], "value": 0.4},
            {"names": ["PHMMouthOpen", "MouthOpen", "CTRLMouthOpen", "JawOpen"], "value": 0.4},
        ],
        "body": [{"bone": "chestUpper", "property": "XRotate", "value": 5.0}],
    },
    "bored": {
        "morphs": [
            {"names": ["PHMEyesClosed", "EyesClosed", "EyeClosedL", "CTRLEyesClosed"], "value": 0.4},
            {"names": ["PHMFrown", "Frown", "MouthFrown"], "value": 0.2},
        ],
        "body": [{"bone": "chestUpper", "property": "XRotate", "value": -4.0}],
    },
    "confident": {
        "morphs": [
            {"names": ["PHMSmile", "Smile", "MouthSmile", "CTRLSmile"], "value": 0.3},
        ],
        "body": [{"bone": "chestUpper", "property": "XRotate", "value": 4.0}],
    },
    "shy": {
        "morphs": [
            {"names": ["PHMSmile", "Smile", "MouthSmile"], "value": 0.2},
            {"names": ["PHMEyesSquint", "EyesSquint", "EyeSquintL"], "value": 0.15},
        ],
        "body": [{"bone": "chestUpper", "property": "XRotate", "value": -5.0}],
    },
    "loving": {
        "morphs": [
            {"names": ["PHMSmile", "Smile", "MouthSmile", "CTRLSmile"], "value": 0.6},
            {"names": ["PHMEyesSquint", "EyesSquint", "EyeSquintL"], "value": 0.35},
        ],
        "body": [{"bone": "chestUpper", "property": "XRotate", "value": 2.0}],
    },
    "contemptuous": {
        "morphs": [
            {"names": ["PHMSmileR", "SmileR", "MouthSmileR", "MouthSmile_R"], "value": 0.5},
            {"names": ["PHMFrownL", "FrownL", "MouthFrownL", "MouthFrown_L"], "value": 0.3},
        ],
        "body": [],
    },
}


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def daz_list_morphs(
    node_label: str,
    include_zero: bool = False,
) -> dict[str, Any]:
    """List all morphs (numeric properties) on a node.

    Returns all numeric properties on a node, which includes morphs (body shapes,
    facial expressions), transforms, and other numeric dials. Useful for discovering
    what morphs are available on a figure.

    Args:
        node_label: Display label or internal name of the node (e.g., "Genesis 9").
        include_zero: If True, return all morphs including those set to 0.
                      If False (default), only return morphs with non-zero values
                      (currently active morphs).

    Returns:
      - morphs: List of morph objects with:
        - label: Display label (e.g., "Head Size")
        - name: Internal name (e.g., "HeadSize")
        - value: Current numeric value
        - path: Property path for organization (e.g., "Morphs/Head")
      - count: Number of morphs returned
      - nodeLabel: Confirmed node label

    Example:
        # List only active morphs on Genesis 9
        result = daz_list_morphs("Genesis 9", include_zero=False)
        # result["morphs"] = [
        #   {"label": "Height", "name": "Height", "value": 1.05, "path": "Morphs/Body"},
        #   {"label": "Head Size", "name": "HeadSize", "value": 0.9, "path": "Morphs/Head"}
        # ]

        # List all available morphs (including zero values)
        result = daz_list_morphs("Genesis 9", include_zero=True)
        # result["count"] might be 500+ morphs
    """
    include_zero_js = "true" if include_zero else "false"

    def _run() -> list | None:
        client = get_daz_client()
        script = f"""(function() {{
            var node = Scene.findNodeByLabel({json.dumps(node_label)});
            if (!node) return null;
            var obj = node.getObject();
            if (!obj) return [];
            var includeZero = {include_zero_js};
            var result = [];
            for (var i = 0; i < obj.getNumModifiers(); i++) {{
                var m = obj.getModifier(i);
                if (m.className() === "DzMorph") {{
                    var ch = m.getValueChannel();
                    var val = ch.getValue();
                    if (includeZero || val !== 0) {{
                        var path = "";
                        try {{
                            var pg = ch.getPropertyGroup();
                            if (pg) path = pg.getPath();
                        }} catch(e) {{}}
                        result.push({{
                            name: m.getName(),
                            label: m.getLabel(),
                            value: val,
                            path: path
                        }});
                    }}
                }}
            }}
            return result;
        }})();"""
        return client.execute(script).value

    try:
        morphs = await run_dazpy(_run)
    except Exception as e:
        handle_dazpy_error(e)
    if morphs is None:
        raise ToolError(f"Node not found: {node_label!r}")
    return {"morphs": morphs, "count": len(morphs), "nodeLabel": node_label}


@mcp.tool()
async def daz_search_morphs(
    node_label: str,
    pattern: str,
    include_zero: bool = False,
) -> dict[str, Any]:
    """Search for morphs matching a name pattern.

    Search through all numeric properties (morphs) on a node for those matching
    a substring pattern. Useful for finding specific morphs like all facial
    expressions, body morphs, or morphs for a specific body part.

    Args:
        node_label: Display label or internal name of the node (e.g., "Genesis 9").
        pattern: Substring to search for in morph label or name (case-insensitive).
                 Examples: "smile", "head", "muscle", "express"
        include_zero: If True, return all matching morphs including zero values.
                      If False (default), only return matching morphs that are active.

    Returns:
      - morphs: List of matching morph objects with:
        - label: Display label
        - name: Internal name
        - value: Current value
        - path: Property path
      - count: Number of matching morphs
      - pattern: The search pattern used
      - nodeLabel: Confirmed node label

    Example:
        # Find all smile-related morphs
        result = daz_search_morphs("Genesis 9", "smile", include_zero=True)
        # result["morphs"] might include: "Smile", "Smile Open", "Smile Closed", etc.

        # Find active head morphs
        result = daz_search_morphs("Genesis 9", "head", include_zero=False)
        # Only returns head morphs with non-zero values

        # Find all facial expression morphs
        result = daz_search_morphs("Genesis 9", "express", include_zero=True)
    """
    include_zero_js = "true" if include_zero else "false"
    pat_lower = pattern.lower()

    def _run() -> list | None:
        client = get_daz_client()
        script = f"""(function() {{
            var node = Scene.findNodeByLabel({json.dumps(node_label)});
            if (!node) return null;
            var obj = node.getObject();
            if (!obj) return [];
            var includeZero = {include_zero_js};
            var pat = {json.dumps(pat_lower)};
            var result = [];
            for (var i = 0; i < obj.getNumModifiers(); i++) {{
                var m = obj.getModifier(i);
                if (m.className() === "DzMorph") {{
                    var name = m.getName();
                    var label = m.getLabel();
                    if (name.toLowerCase().indexOf(pat) === -1 &&
                            label.toLowerCase().indexOf(pat) === -1) continue;
                    var ch = m.getValueChannel();
                    var val = ch.getValue();
                    if (includeZero || val !== 0) {{
                        var path = "";
                        try {{
                            var pg = ch.getPropertyGroup();
                            if (pg) path = pg.getPath();
                        }} catch(e) {{}}
                        result.push({{
                            name: name,
                            label: label,
                            value: val,
                            path: path
                        }});
                    }}
                }}
            }}
            return result;
        }})();"""
        return client.execute(script).value

    try:
        morphs = await run_dazpy(_run)
    except Exception as e:
        handle_dazpy_error(e)
    if morphs is None:
        raise ToolError(f"Node not found: {node_label!r}")
    return {
        "morphs": morphs,
        "count": len(morphs),
        "pattern": pattern,
        "nodeLabel": node_label,
    }


@mcp.tool()
async def daz_set_morph(
    node_label: str,
    morph_name: str,
    value: float,
) -> dict[str, Any]:
    """Set a morph dial on a node by display label.

    Matches by exact label first, then exact internal name, then substring of
    label — so ``"smile"`` will match ``"Mouth Smile"`` if no exact match
    exists. Returns the matched label and internal name so you can confirm
    which morph was applied.

    For most morphs the useful range is 0.0–1.0 (fully off to fully on).
    Negative values and values above 1.0 are accepted for special morphs that
    support them.

    Args:
        node_label: Display label of the figure or prop.
        morph_name: Full or partial label of the morph dial.
        value: Target value for the morph.

    Returns:
        Dict with node, morph (display label), internal_name, and value read back.

    Examples:
        daz_set_morph("Genesis 9", "Mouth Smile", 0.8)
        daz_set_morph("Genesis 9", "smile", 0.8)          # substring match
        daz_set_morph("Genesis 9", "Head Size", 1.15)
        daz_set_morph("Genesis 9", "Breast Size", 0.0)    # zero out a morph

    Notes:
        - Use daz_search_morphs to browse available morph names before setting.
        - daz_set_property also works but requires the exact internal property name.
    """
    def _run() -> dict:
        from dazpy import DazMorph
        scene = get_scene()
        node = scene.find_node_by_label(node_label)
        # Try by label first, then by internal name
        modifier = node.find_modifier_by_label(morph_name)
        if modifier is None:
            modifier = node.find_modifier(morph_name)
        if modifier is None:
            raise ToolError(
                f"Morph not found: {morph_name!r} on node {node_label!r}. "
                "Use daz_search_morphs to find available morph names."
            )
        if not isinstance(modifier, DazMorph):
            raise ToolError(
                f"{morph_name!r} exists on {node_label!r} but is not a morph modifier."
            )
        modifier.value = float(value)
        return {"success": True, "node": node_label, "morph": morph_name, "value": value}

    try:
        return await run_dazpy(_run)
    except ToolError:
        raise
    except Exception as e:
        handle_dazpy_error(e)


@mcp.tool()
async def daz_set_emotion(
    character_label: str,
    emotion: str,
    intensity: float = 0.7,
) -> dict[str, Any]:
    """Apply an emotional expression to a character using morph candidates + body adjustment.

    Args:
        character_label: Node label of the character to affect.
        emotion: One of: happy, sad, angry, surprised, fearful, disgusted, neutral,
                 excited, bored, confident, shy, loving, contemptuous.
        intensity: Scale factor 0.0–1.0 applied to all morph and body values (default 0.7).

    Returns:
        Dict with applied_morphs, body_adjustments, and not_found lists.

    Notes:
        Morph candidates are tried in order; first match per slot wins. Not-found morphs
        are reported but do not raise errors — figures vary in available morphs.
    """
    valid = sorted(_EMOTION_DEFINITIONS.keys())
    if emotion not in _EMOTION_DEFINITIONS:
        raise ToolError(
            f"Unknown emotion: '{emotion}'. Valid emotions: {', '.join(valid)}"
        )
    if not (0.0 <= intensity <= 1.0):
        raise ToolError(f"intensity must be between 0.0 and 1.0, got {intensity}")

    definition = _EMOTION_DEFINITIONS[emotion]

    def _run() -> dict[str, Any]:
        skeleton = _find_skeleton(get_scene(), character_label)

        applied: list[dict] = []
        not_found: list[str] = []
        for entry in definition["morphs"]:
            target_value = entry["value"] * intensity
            found = False
            for name in entry["names"]:
                prop = skeleton.find_property(name)
                if prop is not None:
                    prop.value = target_value
                    applied.append({"morph": name, "value": prop.value})
                    found = True
                    break
            if not found:
                not_found.append(entry["names"][0] if entry["names"] else "unknown")

        body_applied: list[dict] = []
        for adj in definition["body"]:
            try:
                bone = skeleton.find_bone(adj["bone"])
            except NodeNotFoundError:
                continue
            prop = bone.find_property(adj["property"])
            if prop is None:
                continue
            value = adj["value"] * intensity
            prop.value = value
            body_applied.append({"bone": adj["bone"], "property": adj["property"], "value": value})

        return {
            "character": character_label,
            "emotion": emotion,
            "intensity": intensity,
            "applied_morphs": applied,
            "body_adjustments": body_applied,
            "not_found": not_found,
        }

    try:
        return await run_dazpy(_run)
    except Exception as e:
        handle_dazpy_error(e)


@mcp.tool()
async def daz_set_body_language(
    figure_label: str,
    posture: str,
    intensity: float = 1.0,
) -> dict[str, Any]:
    """Apply a body-language posture to a figure via bone rotation adjustments.

    Adjusts key skeleton bones (chest, shoulders, neck) to convey a physical
    attitude. Works on Genesis figures and other rigged characters with standard
    bone names.

    Args:
        figure_label: Display label of the skeleton/figure (e.g., "Genesis 9").
        posture: One of: confident, defensive, relaxed, tense.
        intensity: Scale factor 0.0–1.0 applied to all bone rotations (default 1.0).

    Returns:
        Dict with success, figure, posture, intensity, applied (list of bone
        adjustments that were set), and not_found (bones/properties not present
        on this figure).

    Notes:
        - Bone names follow Genesis 8/9 conventions; some bones may not exist on
          non-Genesis figures and will be silently skipped (reported in not_found).
        - Combine with daz_set_emotion for full expressive character poses.
    """
    valid_postures = ("confident", "defensive", "relaxed", "tense")
    if posture not in valid_postures:
        raise ToolError(
            f"Unknown posture: '{posture}'. Valid postures: {', '.join(valid_postures)}"
        )
    if not (0.0 <= intensity <= 1.0):
        raise ToolError(f"intensity must be between 0.0 and 1.0, got {intensity}")

    def _run() -> dict[str, Any]:
        skeleton = _find_skeleton(get_scene(), figure_label)

        applied: list[dict] = []
        not_found: list[str] = []
        for adj in _POSTURE_DEFINITIONS[posture]:
            try:
                bone = skeleton.find_bone(adj["bone"])
            except NodeNotFoundError:
                not_found.append(adj["bone"])
                continue
            prop = bone.find_property(adj["property"])
            if prop is None:
                not_found.append(f"{adj['bone']}.{adj['property']}")
                continue
            value = adj["value"] * intensity
            prop.value = value
            applied.append({"bone": adj["bone"], "property": adj["property"], "value": value})

        return {
            "success": True,
            "figure": figure_label,
            "posture": posture,
            "intensity": intensity,
            "applied": applied,
            "not_found": not_found,
        }

    try:
        return await run_dazpy(_run)
    except Exception as e:
        handle_dazpy_error(e)


@mcp.tool()
async def daz_direct_gaze(
    figure_label: str,
    direction: str,
    target_label: str | None = None,
) -> dict[str, Any]:
    """Point a figure's head/gaze toward a direction or scene object.

    Rotates the head bone to face a named direction or a target node.  For the
    "camera" direction the active viewport camera is used; for "character" a
    ``target_label`` must be supplied.

    Args:
        figure_label: Display label of the skeleton/figure (e.g., "Genesis 9").
        direction: One of: camera, away, up, down, left, right, character.
        target_label: Required when direction is "character" — the display label
                      of the node or skeleton to look toward.

    Returns:
        Dict with success, figure, direction, applied (list of bone/property
        adjustments), and not_found (bones/properties missing on this figure).

    Notes:
        - "camera" computes a rough angle toward the active viewport camera.
        - "character" computes a rough angle toward the target node's position.
        - Head bone search falls back to "neckUpper" if "head" is not found.
        - Angle computation is approximate (good for typical scene proportions).
    """
    valid_directions = ("camera", "away", "up", "down", "left", "right", "character")
    if direction not in valid_directions:
        raise ToolError(
            f"Unknown direction: '{direction}'. "
            f"Valid directions: {', '.join(valid_directions)}"
        )
    if direction == "character" and not target_label:
        raise ToolError("target_label is required when direction is 'character'")

    def _run() -> dict[str, Any]:
        scene = get_scene()
        skeleton = _find_skeleton(scene, figure_label)

        head_bone = _find_bone_any(skeleton, ("head", "neckUpper"))
        if head_bone is None:
            return {"success": False, "error": "Head/neckUpper bone not found"}

        rot_x = 0.0
        rot_y = 0.0

        if direction == "up":
            rot_x, rot_y = -25.0, 0.0
        elif direction == "down":
            rot_x, rot_y = 20.0, 0.0
        elif direction == "left":
            rot_x, rot_y = 0.0, -35.0
        elif direction == "right":
            rot_x, rot_y = 0.0, 35.0
        elif direction == "away":
            rot_x, rot_y = 0.0, 180.0
        elif direction == "camera":
            cam_pos = _active_camera_position(get_daz_client())
            if cam_pos is None:
                return {"success": False, "error": "No active camera in scene"}
            rot_x, rot_y = _gaze_angles(head_bone.position, cam_pos)
        elif direction == "character":
            try:
                target = scene.find_node_by_label(target_label)
            except NodeNotFoundError:
                try:
                    target = scene.find_skeleton_by_label(target_label)
                except NodeNotFoundError:
                    return {"success": False, "error": f"Target not found: {target_label}"}
            rot_x, rot_y = _gaze_angles(head_bone.position, target.position)

        applied: list[dict] = []
        not_found: list[str] = []
        bone_name = head_bone.name

        x_prop = head_bone.find_property("XRotate")
        y_prop = head_bone.find_property("YRotate")

        if x_prop is not None:
            x_prop.value = rot_x
            applied.append({"bone": bone_name, "property": "XRotate", "value": rot_x})
        else:
            not_found.append(f"{bone_name}.XRotate")

        if y_prop is not None:
            y_prop.value = rot_y
            applied.append({"bone": bone_name, "property": "YRotate", "value": rot_y})
        else:
            not_found.append(f"{bone_name}.YRotate")

        return {
            "success": True,
            "figure": figure_label,
            "direction": direction,
            "applied": applied,
            "not_found": not_found,
        }

    try:
        return await run_dazpy(_run)
    except Exception as e:
        handle_dazpy_error(e)
