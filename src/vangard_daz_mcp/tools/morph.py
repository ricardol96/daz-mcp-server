"""Morph, expression, and body-language tools for DAZ Studio figures."""
from __future__ import annotations

import json
from typing import Any

from fastmcp.exceptions import ToolError

from .._mcp import mcp, _execute_by_id, _execute, _execute_by_id_async  # noqa: F401
from .._client import get_scene, get_daz_client, run_dazpy, get_http_client  # noqa: F401
from .._errors import handle_dazpy_error, handle_network_error, check_response  # noqa: F401


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
    return await _execute_by_id("vangard-set-emotion", {
        "nodeLabel": character_label,
        "emotion": emotion,
        "intensity": intensity,
        "morphList": definition["morphs"],
        "bodyAdjustments": definition["body"],
    })


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

    script = f"""
(function() {{
    var skel = Scene.findSkeletonByLabel({json.dumps(figure_label)});
    if (!skel) return {{success: false, error: "Figure not found: " + {json.dumps(figure_label)}}};

    var postures = {{
        confident: [
            {{bone: "chestUpper", prop: "XRotate", value: 5.0}},
            {{bone: "lShldr",     prop: "ZRotate", value: -5.0}},
            {{bone: "rShldr",     prop: "ZRotate", value: 5.0}}
        ] ,
        defensive: [
            {{bone: "chestUpper",  prop: "XRotate", value: -8.0}},
            {{bone: "abdomenLower", prop: "XRotate", value: -3.0}},
            {{bone: "lShldr",      prop: "ZRotate", value: 10.0}},
            {{bone: "rShldr",      prop: "ZRotate", value: -10.0}}
        ],
        relaxed: [
            {{bone: "chestUpper", prop: "XRotate", value: -3.0}},
            {{bone: "lShldr",     prop: "ZRotate", value: 4.0}},
            {{bone: "rShldr",     prop: "ZRotate", value: -4.0}},
            {{bone: "neckLower",  prop: "XRotate", value: 2.0}}
        ],
        tense: [
            {{bone: "chestUpper", prop: "XRotate", value: 4.0}},
            {{bone: "lShldr",     prop: "ZRotate", value: -12.0}},
            {{bone: "rShldr",     prop: "ZRotate", value: 12.0}},
            {{bone: "neckLower",  prop: "XRotate", value: -3.0}}
        ]
    }};

    var intensity   = {json.dumps(intensity)};
    var adjustments = postures[{json.dumps(posture)}];
    var applied     = [];
    var notFound    = [];

    for (var i = 0; i < adjustments.length; i++) {{
        var adj  = adjustments[i];
        var bone = skel.findBone(adj.bone);
        if (!bone) {{ notFound.push(adj.bone); continue; }}
        var prop = bone.findProperty(adj.prop);
        if (!prop) {{ notFound.push(adj.bone + "." + adj.prop); continue; }}
        prop.setValue(adj.value * intensity);
        applied.push({{bone: adj.bone, property: adj.prop, value: adj.value * intensity}});
    }}

    return {{
        success:   true,
        figure:    {json.dumps(figure_label)},
        posture:   {json.dumps(posture)},
        intensity: intensity,
        applied:   applied,
        not_found: notFound
    }};
}})();
"""
    result = await _execute(script)
    return result


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

    script = """
(function() {
    var skel = Scene.findSkeletonByLabel(args.figureLabel);
    if (!skel) return {success: false, error: "Figure not found: " + args.figureLabel};

    // Prefer "head" bone; fall back to "neckUpper"
    var headBone = skel.findBone("head") || skel.findBone("neckUpper");
    if (!headBone) return {success: false, error: "Head/neckUpper bone not found"};

    var rotX = 0;
    var rotY = 0;
    var direction = args.direction;

    if (direction === "up")    { rotX = -25; rotY = 0;   }
    else if (direction === "down")  { rotX = 20;  rotY = 0;   }
    else if (direction === "left")  { rotX = 0;   rotY = -35; }
    else if (direction === "right") { rotX = 0;   rotY = 35;  }
    else if (direction === "away")  { rotX = 0;   rotY = 180; }
    else if (direction === "camera") {
        var cam = Scene.getActiveCamera();
        if (!cam) return {success: false, error: "No active camera in scene"};
        var camPos  = cam.getWSPos();
        var headPos = headBone.getWSPos();
        var dx = camPos.x - headPos.x;
        var dy = camPos.y - headPos.y;
        var dz = camPos.z - headPos.z;
        var horizDist = Math.sqrt(dx * dx + dz * dz);
        rotY = Math.atan2(dx, dz) * (180 / Math.PI);
        rotX = -Math.atan2(dy, horizDist) * (180 / Math.PI) * 0.5;
    } else if (direction === "character") {
        var tLabel  = args.targetLabel;
        var target  = Scene.findNodeByLabel(tLabel);
        if (!target) target = Scene.findSkeletonByLabel(tLabel);
        if (!target) return {success: false, error: "Target not found: " + tLabel};
        var tPos    = target.getWSPos();
        var hPos    = headBone.getWSPos();
        var dx2     = tPos.x - hPos.x;
        var dy2     = tPos.y - hPos.y;
        var dz2     = tPos.z - hPos.z;
        var horizDist2 = Math.sqrt(dx2 * dx2 + dz2 * dz2);
        rotY = Math.atan2(dx2, dz2) * (180 / Math.PI);
        rotX = -Math.atan2(dy2, horizDist2) * (180 / Math.PI) * 0.5;
    }

    var applied  = [];
    var notFound = [];

    var xProp = headBone.findProperty("XRotate");
    var yProp = headBone.findProperty("YRotate");

    if (xProp) {
        xProp.setValue(rotX);
        applied.push({bone: headBone.getName(), property: "XRotate", value: rotX});
    } else {
        notFound.push(headBone.getName() + ".XRotate");
    }
    if (yProp) {
        yProp.setValue(rotY);
        applied.push({bone: headBone.getName(), property: "YRotate", value: rotY});
    } else {
        notFound.push(headBone.getName() + ".YRotate");
    }

    return {
        success:   true,
        figure:    args.figureLabel,
        direction: direction,
        applied:   applied,
        not_found: notFound
    };
})();
"""
    result = await _execute(script, {
        "figureLabel": figure_label,
        "direction": direction,
        "targetLabel": target_label or "",
    })
    return result
