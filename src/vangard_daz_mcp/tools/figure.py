"""Figure/character MCP tools for DAZ Studio.

Covers look-at helpers, reach-toward IK, interactive posing, pose reset,
and pose file save/load via dazpy.
"""
from __future__ import annotations

import math
from typing import Any

from fastmcp.exceptions import ToolError

from dazpy import (
    DazPose,
    align_hand_target,
    build_face_each_other_recipe,
    build_handshake_recipe,
    build_hug_recipe,
    build_touch_recipe,
)
from dazpy.exceptions import NodeNotFoundError

from .._mcp import mcp
from .._client import get_scene, run_dazpy
from .._errors import handle_dazpy_error

# ---------------------------------------------------------------------------
# Skeleton/bone lookup helpers
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


# ---------------------------------------------------------------------------
# Cascading look-at rotation (eyes -> head -> neck -> torso -> hip)
# Generation-agnostic bone candidates: Genesis 9 name first, Genesis 3/8 fallback.
# ---------------------------------------------------------------------------

_LOOK_AT_LEVELS: list[tuple[str, list[tuple[str, ...]], float]] = [
    ("eyes", [("l_eye", "lEye"), ("r_eye", "rEye")], 1.0),
    ("head", [("head",)], 0.6),
    ("neck", [("neck2", "neckUpper"), ("neck1", "neckLower")], 0.3),
    ("torso", [("spine3", "chestUpper"), ("spine2", "chestLower")], 0.15),
    ("full", [("hip",)], 0.1),
]

_LOOK_AT_MODE_LEVELS: dict[str, list[str]] = {
    "eyes": ["eyes"],
    "head": ["eyes", "head"],
    "neck": ["eyes", "head", "neck"],
    "torso": ["eyes", "head", "neck", "torso"],
    "full": ["eyes", "head", "neck", "torso", "full"],
}


def _rotate_bone_toward(bone: Any, target: tuple[float, float, float], scale: float) -> str:
    """Rotate a bone's X/Y local rotation toward a world-space point (absolute, not additive)."""
    pos = bone.position
    dx = target[0] - pos["x"]
    dy = target[1] - pos["y"]
    dz = target[2] - pos["z"]
    dist = math.hypot(dx, dz)
    angle_y = math.degrees(math.atan2(dx, dz)) * scale
    angle_x = math.degrees(math.atan2(dy, dist)) * scale
    cur_euler = bone.local_euler
    cur_z = cur_euler[2] if cur_euler else 0.0
    bone.set_local_rotation(angle_x, angle_y, cur_z)
    return bone.label


def _look_at_cascade(skeleton: Any, target: tuple[float, float, float], mode: str) -> list[str]:
    rotated: list[str] = []
    for level_name in _LOOK_AT_MODE_LEVELS[mode]:
        _, candidate_groups, scale = next(l for l in _LOOK_AT_LEVELS if l[0] == level_name)
        for candidates in candidate_groups:
            bone = _find_bone_any(skeleton, candidates)
            if bone is not None:
                rotated.append(_rotate_bone_toward(bone, target, scale))
    return rotated

# ---------------------------------------------------------------------------
# Bone-group filter map (mirrors server.py _POSE_BONE_GROUPS)
# ---------------------------------------------------------------------------

_POSE_BONE_GROUPS: dict[str, set[str]] = {
    "arms_only": {
        "lShldrBend", "rShldrBend", "lShldrTwist", "rShldrTwist",
        "lForearmBend", "rForearmBend", "lForearmTwist", "rForearmTwist",
        "lHand", "rHand",
        "l_upperarm", "r_upperarm", "l_forearm", "r_forearm",
        "l_hand", "r_hand",
    },
    "legs_only": {
        "lThighBend", "rThighBend", "lThighTwist", "rThighTwist",
        "lShin", "rShin", "lFoot", "rFoot", "lToe", "rToe",
        "l_thigh", "r_thigh", "l_shin", "r_shin", "l_foot", "r_foot",
    },
    "spine": {
        "hip", "pelvis",
        "abdomenLower", "abdomenUpper", "chestLower", "chestUpper",
        "neckLower", "neckUpper", "head",
        "spine1", "spine2", "spine3", "spine4",
        "neck1", "neck2",
    },
}


# ---------------------------------------------------------------------------
# Interactive-pose recipe mapping
# ---------------------------------------------------------------------------

_INTERACTION_DEFAULT_DISTANCE: dict[str, float] = {
    "face-each-other": 100.0,
    "hug": 40.0,
    "shoulder-arm": 30.0,
    "handshake": 60.0,
}

_INTERACTION_RECIPE_BUILDERS: dict[str, Any] = {
    "face-each-other": lambda a, b: build_face_each_other_recipe(a, b),
    "hug": lambda a, b: build_hug_recipe(a, b),
    "shoulder-arm": lambda a, b: build_touch_recipe(a, b),
    "handshake": lambda a, b: build_handshake_recipe(a, b),
}


# ---------------------------------------------------------------------------
# Look-at / reach helpers
# ---------------------------------------------------------------------------

@mcp.tool()
async def daz_look_at_point(
    character_label: str,
    target_x: float,
    target_y: float,
    target_z: float,
    mode: str = "head",
) -> dict[str, Any]:
    """Make character look at a world-space point with configurable body involvement.

    This helper uses cascading rotations from eyes through the body to create
    natural-looking character attention. Different modes control how much of
    the body participates in the look direction.

    Args:
        character_label: Display label or internal name of the character figure.
        target_x: World X coordinate (cm) to look at.
        target_y: World Y coordinate (cm) to look at.
        target_z: World Z coordinate (cm) to look at.
        mode: How much body to involve in the look. Options:
              - "eyes": Only rotate eyes
              - "head": Eyes + head rotation (default)
              - "neck": Eyes + head + neck
              - "torso": Eyes + head + neck + chest
              - "full": Complete body rotation including hip

    Returns:
      - success: true on success
      - character: character label
      - mode: the mode used
      - rotatedBones: list of bone labels that were rotated

    Example:
        # Character looks at point in front of them at eye level
        daz_look_at_point("Genesis 9", 0, 160, 200, mode="head")

        # Full body turn to look behind
        daz_look_at_point("Genesis 9", 0, 140, -150, mode="full")
    """
    if mode not in _LOOK_AT_MODE_LEVELS:
        raise ToolError(
            f"Unknown mode {mode!r}. Valid modes: {', '.join(_LOOK_AT_MODE_LEVELS)}"
        )

    def _run() -> dict[str, Any]:
        skeleton = _find_skeleton(get_scene(), character_label)
        rotated = _look_at_cascade(skeleton, (target_x, target_y, target_z), mode)
        return {
            "success": True,
            "character": character_label,
            "mode": mode,
            "rotatedBones": rotated,
        }

    try:
        return await run_dazpy(_run)
    except Exception as e:
        handle_dazpy_error(e)


@mcp.tool()
async def daz_look_at_character(
    source_label: str,
    target_label: str,
    mode: str = "head",
) -> dict[str, Any]:
    """Make one character look at another character's face.

    Automatically finds the target character's head position and rotates
    the source character to look at it using cascading body rotations.

    Args:
        source_label: Display label of the character who will look.
        target_label: Display label of the character to look at.
        mode: How much body to involve. Options:
              - "eyes": Only rotate eyes
              - "head": Eyes + head rotation (default)
              - "neck": Eyes + head + neck
              - "torso": Eyes + head + neck + chest
              - "full": Complete body rotation including hip

    Returns:
      - success: true on success
      - source: source character label
      - target: target character label
      - mode: the mode used
      - targetPosition: {x, y, z} world coordinates of target's head
      - rotatedBones: list of bone labels that were rotated

    Example:
        # Alice looks at Bob with head turn
        daz_look_at_character("Alice", "Bob", mode="head")

        # Bob turns his whole body to face Alice
        daz_look_at_character("Bob", "Alice", mode="full")
    """
    if mode not in _LOOK_AT_MODE_LEVELS:
        raise ToolError(
            f"Unknown mode {mode!r}. Valid modes: {', '.join(_LOOK_AT_MODE_LEVELS)}"
        )

    def _run() -> dict[str, Any]:
        scene = get_scene()
        source = _find_skeleton(scene, source_label)
        target = _find_skeleton(scene, target_label)

        target_head = _find_bone_any(target, ("head",))
        if target_head is not None:
            head_pos = target_head.position
            target_point = (head_pos["x"], head_pos["y"], head_pos["z"])
        else:
            # Fallback: figure root position + approximate head height for Genesis 9
            root_pos = target.position
            target_point = (root_pos["x"], root_pos["y"] + 163, root_pos["z"])

        rotated = _look_at_cascade(source, target_point, mode)
        return {
            "success": True,
            "source": source_label,
            "target": target_label,
            "mode": mode,
            "targetPosition": {"x": target_point[0], "y": target_point[1], "z": target_point[2]},
            "rotatedBones": rotated,
        }

    try:
        return await run_dazpy(_run)
    except Exception as e:
        handle_dazpy_error(e)


@mcp.tool()
async def daz_reach_toward(
    character_label: str,
    side: str,
    target_x: float,
    target_y: float,
    target_z: float,
) -> dict[str, Any]:
    """Position character's arm to reach toward a world-space point.

    Uses pseudo-IK approximation to calculate shoulder and elbow rotations
    that position the hand near the target point. Automatically adjusts
    elbow bend based on target distance.

    Args:
        character_label: Display label or internal name of the character.
        side: Which arm to use: "left" or "right".
        target_x: World X coordinate (cm) to reach toward.
        target_y: World Y coordinate (cm) to reach toward.
        target_z: World Z coordinate (cm) to reach toward.

    Returns:
      - success: true on success
      - character: character label
      - side: which arm was posed
      - targetDistance: distance in cm from shoulder to target
      - bones: list of bone labels that were rotated

    Example:
        # Reach right hand toward point in front at chest height
        daz_reach_toward("Genesis 9", "right", 50, 130, 80)

        # Reach left hand toward object on left side
        daz_reach_toward("Genesis 9", "left", -60, 100, 50)

    Note:
        Uses dazpy's damped-least-squares IK solver (align_hand_target) over
        the shoulder-forearm-hand chain, rather than a fixed trig heuristic.
    """
    if side not in ("left", "right"):
        raise ToolError(f"side must be 'left' or 'right', got {side!r}")

    prefix = "l" if side == "left" else "r"
    shoulder_candidates = (f"{prefix}_upperarm", f"{prefix}ShldrBend", f"{prefix}Shldr")
    anchor = f"{prefix}_hand"

    def _run() -> dict[str, Any]:
        skeleton = _find_skeleton(get_scene(), character_label)

        target_distance = None
        shoulder = _find_bone_any(skeleton, shoulder_candidates)
        if shoulder is not None:
            pos = shoulder.position
            target_distance = math.dist(
                (pos["x"], pos["y"], pos["z"]), (target_x, target_y, target_z)
            )

        result = align_hand_target(skeleton, (target_x, target_y, target_z), source_anchor=anchor)

        return {
            "success": True,
            "character": character_label,
            "side": side,
            "targetDistance": target_distance,
            "bones": result.chain,
        }

    try:
        return await run_dazpy(_run)
    except Exception as e:
        handle_dazpy_error(e)


@mcp.tool()
async def daz_interactive_pose(
    char1_label: str,
    char2_label: str,
    interaction_type: str = "face-each-other",
    distance: float | None = None,
) -> dict[str, Any]:
    """Coordinate two characters for interactive poses.

    Applies complementary poses to two characters for common interaction
    scenarios. Handles both positioning and pose application.

    Args:
        char1_label: Display label of first character.
        char2_label: Display label of second character.
        interaction_type: Type of interaction. Options:
            - "face-each-other": Position and rotate to face each other (default)
            - "hug": Both characters hug with arms around each other
            - "shoulder-arm": Char1 puts arm around char2's shoulders
            - "handshake": Both extend right hands for handshake
        distance: Optional spacing between characters in cm (default varies by type:
                  face=100, hug=40, shoulder-arm=30, handshake=60).

    Returns:
      - success: true on success
      - char1: first character label
      - char2: second character label
      - interactionType: the interaction type used
      - applied: list of pose components that were applied

    Example:
        # Position characters facing each other at conversation distance
        daz_interactive_pose("Alice", "Bob", "face-each-other", distance=120)

        # Create tight hug
        daz_interactive_pose("Alice", "Bob", "hug", distance=30)

        # Bob puts arm around Alice's shoulders
        daz_interactive_pose("Bob", "Alice", "shoulder-arm")

    Note:
        These are simplified interaction poses. For natural-looking results,
        you may need to fine-tune positions and rotations using daz_set_property
        or load artist-created pose presets. Arm/hand posing is generation-agnostic
        (dazpy's anchor system resolves the right bone names per figure family).
    """
    if interaction_type not in _INTERACTION_RECIPE_BUILDERS:
        raise ToolError(
            f"Unknown interaction_type {interaction_type!r}. "
            f"Valid values: {', '.join(_INTERACTION_RECIPE_BUILDERS)}"
        )

    spacing = distance if distance is not None else _INTERACTION_DEFAULT_DISTANCE[interaction_type]

    def _run() -> dict[str, Any]:
        scene = get_scene()
        char1 = _find_skeleton(scene, char1_label)
        char2 = _find_skeleton(scene, char2_label)

        pos1 = char1.position
        pos2 = char2.position
        mid_x = (pos1["x"] + pos2["x"]) / 2
        mid_z = (pos1["z"] + pos2["z"]) / 2
        char1.set_position(mid_x - spacing / 2, pos1["y"], mid_z)
        char2.set_position(mid_x + spacing / 2, pos2["y"], mid_z)

        hip1 = char1.find_bone("hip")
        hip2 = char2.find_bone("hip")
        hip1_euler = hip1.local_euler
        hip2_euler = hip2.local_euler
        hip1.set_local_rotation(hip1_euler[0] if hip1_euler else 0.0, 90.0, hip1_euler[2] if hip1_euler else 0.0)
        hip2.set_local_rotation(hip2_euler[0] if hip2_euler else 0.0, -90.0, hip2_euler[2] if hip2_euler else 0.0)

        applied = ["facing"]
        recipe = _INTERACTION_RECIPE_BUILDERS[interaction_type](char1_label, char2_label)
        scene.apply_interaction_recipe(recipe, align_limb_targets=True)
        applied.append(interaction_type)

        return {
            "success": True,
            "char1": char1_label,
            "char2": char2_label,
            "interactionType": interaction_type,
            "applied": applied,
        }

    try:
        return await run_dazpy(_run)
    except Exception as e:
        handle_dazpy_error(e)


# ---------------------------------------------------------------------------
# Pose reset / save / load
# ---------------------------------------------------------------------------

@mcp.tool()
async def daz_reset_pose(
    node_label: str,
    zero_transforms: bool = False,
) -> dict[str, Any]:
    """Zero all bone rotations on a figure, returning it to its rest pose.

    Recursively walks the node's skeleton and sets XRotate, YRotate, and
    ZRotate to 0 on every bone. Optionally also zeroes the root node's
    translation and scale.

    Args:
        node_label: Display label of the figure whose pose should be cleared.
        zero_transforms: If True, also zero the root XYZ translation and reset
                         Scale to 1.0 (default False — only rotations are reset).

    Returns:
        Dict with node, bones_reset (count), and transforms_zeroed.

    Examples:
        daz_reset_pose("Genesis 9")
        daz_reset_pose("Genesis 9", zero_transforms=True)  # also move to origin

    Notes:
        - This does not affect morph values. Use daz_set_morph or daz_set_property
          to zero morphs individually.
        - Keyframes on bone properties are not removed; use daz_clear_animation
          if you also need to strip animation data.
    """
    def _run() -> dict[str, Any]:
        skeleton = _find_skeleton(get_scene(), node_label)
        rotations = skeleton.bone_rotations()
        skeleton.set_bone_rotations({name: (0.0, 0.0, 0.0) for name in rotations})

        if zero_transforms:
            skeleton.set_local_position(0.0, 0.0, 0.0)
            scale_prop = skeleton.find_property("Scale")
            if scale_prop is not None:
                scale_prop.value = 1.0

        return {
            "node": node_label,
            "bones_reset": len(rotations),
            "transforms_zeroed": zero_transforms,
        }

    try:
        return await run_dazpy(_run)
    except Exception as e:
        handle_dazpy_error(e)


@mcp.tool()
async def daz_save_pose(
    figure_label: str,
    pose_name: str,
    output_path: str,
) -> dict[str, Any]:
    """Capture all bone rotations and translations from a figure and save to a JSON pose file.

    Walks the entire bone hierarchy of the named figure, reads XRotate/YRotate/ZRotate
    and XTranslate/YTranslate/ZTranslate for each bone, and writes the result as a JSON
    file at ``output_path``.  The file can later be loaded with ``daz_load_pose``.

    Args:
        figure_label: Display label of the source figure (e.g. ``"Genesis 9"``).
        pose_name: Human-readable name stored inside the pose file (e.g. ``"T-Pose"``).
        output_path: Absolute path where the ``.json`` pose file will be written
            (e.g. ``"C:/poses/hero_idle.json"``).

    Returns:
        Dict with keys:
        - success: true on success
        - figure: confirmed figure label
        - pose_name: name stored in the file
        - bone_count: number of bones captured
        - file: absolute path written

    Examples:
        daz_save_pose("Genesis 9", "Hero Idle", "C:/poses/hero_idle.json")
        daz_save_pose("Victoria 9", "Sitting Pose", "D:/assets/sitting.json")
    """
    def _run() -> dict[str, Any]:
        scene = get_scene()
        skel = scene.find_skeleton_by_label(figure_label)
        pose = DazPose.capture(skel)
        pose.save(output_path)
        return {
            "success": True,
            "figure": figure_label,
            "pose_name": pose_name,
            "bone_count": len(pose.bones),
            "file": output_path,
        }

    try:
        return await run_dazpy(_run)
    except ToolError:
        raise
    except Exception as e:
        handle_dazpy_error(e)


@mcp.tool()
async def daz_load_pose(
    figure_label: str,
    pose_path: str,
    bone_group: str = "full",
) -> dict[str, Any]:
    """Load a saved pose JSON file and apply it to a figure.

    Reads a pose file created by ``daz_save_pose`` and applies bone rotations
    and translations to the named figure.  The optional ``bone_group`` filter
    limits which bones are updated.

    Args:
        figure_label: Display label of the target figure (e.g. ``"Genesis 9"``).
        pose_path: Absolute path to the ``.json`` pose file created by
            ``daz_save_pose`` (e.g. ``"C:/poses/hero_idle.json"``).
        bone_group: Which bones to apply.  Options:
            - ``"full"`` (default) — all bones in the file
            - ``"arms_only"`` — shoulders, forearms, hands
            - ``"legs_only"`` — thighs, shins, feet
            - ``"spine"`` — hip, pelvis, spine chain, neck, head

    Returns:
        Dict with keys:
        - success: true on success
        - figure: confirmed figure label
        - pose_name: name from the pose file
        - bones_applied: number of bones whose values were written
        - bones_skipped: number of bones not found on the figure

    Examples:
        daz_load_pose("Genesis 9", "C:/poses/hero_idle.json")
        daz_load_pose("Genesis 9", "C:/poses/hero_idle.json", bone_group="arms_only")
        daz_load_pose("Clone 1", "C:/poses/sitting.json", bone_group="spine")
    """
    if bone_group != "full" and bone_group not in _POSE_BONE_GROUPS:
        raise ToolError(
            f"Unknown bone_group {bone_group!r}. "
            "Valid values: full, arms_only, legs_only, spine"
        )

    def _run() -> dict[str, Any]:
        scene = get_scene()
        skel = scene.find_skeleton_by_label(figure_label)
        pose = DazPose.load(pose_path)

        if bone_group != "full":
            allowed = _POSE_BONE_GROUPS[bone_group]
            skipped = len([k for k in pose.bones if k not in allowed])
            filtered_bones = {k: v for k, v in pose.bones.items() if k in allowed}
            filtered_pose = DazPose(
                figure=pose.figure,
                bones=filtered_bones,
                morphs={},
                props={},
            )
            filtered_pose.apply(skel)
            return {
                "success": True,
                "figure": figure_label,
                "pose_name": pose.figure,
                "bones_applied": len(filtered_bones),
                "bones_skipped": skipped,
            }

        pose.apply(skel)
        return {
            "success": True,
            "figure": figure_label,
            "pose_name": pose.figure,
            "bones_applied": len(pose.bones),
            "bones_skipped": 0,
        }

    try:
        return await run_dazpy(_run)
    except ToolError:
        raise
    except Exception as e:
        handle_dazpy_error(e)
