"""Wardrobe tools: fitting, unfitting, and inspecting clothing/hair items."""
from __future__ import annotations

from typing import Any

from fastmcp.exceptions import ToolError

from .._mcp import mcp, _execute_by_id
from .._client import get_http_client
from .._errors import handle_network_error, check_response


@mcp.tool()
async def daz_list_fitted_items(figure_label: str) -> dict[str, Any]:
    """List all clothing, hair, and prop nodes currently fitted to a figure.

    Returns every scene node that either follows the named figure (figure-based
    conforming clothing and hair) or is directly parented to it (props and
    accessories).  Each item includes its display label, internal name, type
    classification (``clothing``, ``hair``, or ``prop``), and element ID.

    Args:
        figure_label: Display label of the base figure (e.g. ``"Genesis 9"``).

    Returns:
        Dict with keys:
        - figure: confirmed figure label
        - fitted_count: total number of fitted items
        - fitted_items: list of {label, name, type, element_id}

    Examples:
        daz_list_fitted_items("Genesis 9")
        daz_list_fitted_items("Victoria 9")
    """
    return await _execute_by_id("vangard-list-fitted-items", {"figureLabel": figure_label})


@mcp.tool()
async def daz_fit_clothing(clothing_label: str, figure_label: str) -> dict[str, Any]:
    """Fit a clothing or prop item to a base figure.

    For figure-based conforming clothing (items that are themselves a DzFigure),
    this sets the follow target so the clothing deforms with the figure's pose.
    For props and accessories, it parents the item to the figure.

    The clothing item must already be loaded into the scene.  Use
    ``daz_load_file`` or ``daz_load_product`` to add it first.

    Args:
        clothing_label: Display label of the clothing/prop node to fit.
        figure_label: Display label of the target base figure.

    Returns:
        Dict with keys:
        - success: true on success
        - clothing: confirmed clothing label
        - figure: confirmed figure label
        - method: which API was used (``setFollowTarget``, ``followSkeleton``,
          or ``addNodeChild`` for the parenting fallback)

    Examples:
        daz_fit_clothing("Sci-Fi Bodysuit", "Genesis 9")
        daz_fit_clothing("Leather Jacket", "Genesis 8 Female")
    """
    return await _execute_by_id(
        "vangard-fit-clothing",
        {"clothingLabel": clothing_label, "figureLabel": figure_label},
    )


@mcp.tool()
async def daz_unfit_item(item_label: str) -> dict[str, Any]:
    """Remove the fitting relationship between a clothing/prop item and its figure.

    Clears any follow-target relationship (conforming clothing) and detaches the
    item from its parent figure (props), leaving it as a free-standing scene node
    at its current world position.

    Args:
        item_label: Display label of the item to unfit.

    Returns:
        Dict with keys:
        - success: true on success
        - item: confirmed item label
        - previous_figure: label of the figure it was detached from (or null)
        - actions: list of operations performed

    Examples:
        daz_unfit_item("Sci-Fi Bodysuit")
        daz_unfit_item("Hat Prop")
    """
    return await _execute_by_id("vangard-unfit-item", {"itemLabel": item_label})


@mcp.tool()
async def daz_run_dforce_simulation(
    node_label: str | None = None,
    start_frame: int = 0,
    end_frame: int | None = None,
) -> dict[str, Any]:
    """Run dForce cloth or hair simulation for a frame range.

    Triggers the DAZ Studio simulation engine (``DzSimulationMgr``) for all
    simulatable nodes in the scene, or limits the simulation to a single node
    when ``node_label`` is provided (the node is selected before the sim runs).

    dForce modifiers must already be present on the target clothing or hair
    node.  Use ``daz_set_dforce_property`` to tune modifier settings before
    calling this tool.

    Args:
        node_label: Display label of the clothing or hair node to simulate.
            When omitted the entire scene is simulated.
        start_frame: First frame of the simulation range (default 0).
        end_frame: Last frame of the simulation range.  When omitted the
            scene's current end frame is used.

    Returns:
        Dict with keys:
        - success: true on success
        - node: node label that was targeted, or "all simulatable nodes"
        - start_frame: effective start frame
        - end_frame: effective end frame

    Examples:
        daz_run_dforce_simulation("Outfit", 0, 60)
        daz_run_dforce_simulation(start_frame=0, end_frame=120)
    """
    args: dict[str, Any] = {"startFrame": start_frame}
    if node_label is not None:
        args["nodeLabel"] = node_label
    if end_frame is not None:
        args["endFrame"] = end_frame
    return await _execute_by_id("vangard-run-dforce-simulation", args)


@mcp.tool()
async def daz_bake_simulation(node_label: str | None = None) -> dict[str, Any]:
    """Bake dForce simulation results to keyframes.

    Converts the in-memory dForce simulation cache to actual keyframes on the
    simulated vertices/bones so the result is preserved when the scene is saved
    or the simulation cache is cleared.

    Call this after ``daz_run_dforce_simulation`` to lock down the simulated
    shape.  The node selection behaviour mirrors ``daz_run_dforce_simulation``:
    when ``node_label`` is given the node is selected first; otherwise all
    currently simulated nodes are baked.

    Args:
        node_label: Display label of the node to bake.  When omitted all
            simulated nodes are baked.

    Returns:
        Dict with keys:
        - success: true on success
        - node: node label that was targeted, or "all"
        - method: the DazScript method used to bake

    Examples:
        daz_bake_simulation("Outfit")
        daz_bake_simulation()
    """
    args: dict[str, Any] = {}
    if node_label is not None:
        args["nodeLabel"] = node_label
    return await _execute_by_id("vangard-bake-simulation", args)


@mcp.tool()
async def daz_set_dforce_property(
    node_label: str,
    property_name: str,
    value: float,
) -> dict[str, Any]:
    """Set a dForce modifier property on a scene node.

    Locates the dForce modifier attached to the named node (checking both
    node-level and shape-level modifiers) and sets the named property to the
    given value.  Common property names include:

    - ``"Dynamics Strength"`` — 0–1, overall simulation influence
    - ``"Stretch Stiffness"`` — resistance to stretching
    - ``"Shear Stiffness"`` — resistance to shearing deformation
    - ``"Bend Stiffness"`` — resistance to bending
    - ``"Gravity Scale"`` — multiplier on the scene gravity (1.0 = normal)
    - ``"Density"`` — simulated mass per unit area
    - ``"Global Damping"`` — velocity damping applied each timestep

    If the property name is not found exactly, a case-insensitive fallback
    search is attempted.  On failure the error lists all available properties.

    Args:
        node_label: Display label of the clothing or hair node.
        property_name: Internal name of the dForce modifier property to set.
        value: Numeric value to apply.

    Returns:
        Dict with keys:
        - success: true on success
        - node: confirmed node label
        - modifier: class name of the dForce modifier that was modified
        - property: confirmed property name (may differ from input if fuzzy-matched)
        - old_value: value before the change
        - new_value: value that was set

    Examples:
        daz_set_dforce_property("Outfit", "Dynamics Strength", 1.0)
        daz_set_dforce_property("Hair", "Gravity Scale", 0.5)
        daz_set_dforce_property("Dress", "Bend Stiffness", 0.2)
    """
    return await _execute_by_id(
        "vangard-set-dforce-property",
        {"nodeLabel": node_label, "propertyName": property_name, "value": value},
    )


@mcp.tool()
async def daz_get_figure_info(figure_label: str) -> dict[str, Any]:
    """Return diagnostic information about a loaded figure.

    Detects the Genesis generation and biological sex from the figure's internal
    name and label, lists all morphs that currently have a non-zero value, counts
    the number of clothing/prop items fitted to the figure, and reports the active
    subdivision level.

    This is the recommended first call when working with an unfamiliar figure, as
    it determines which morph names, bone names, and fitting approaches apply.

    Args:
        figure_label: Display label of the figure to inspect
            (e.g. ``"Genesis 9"`` or ``"Victoria 9"``).

    Returns:
        Dict with keys:
        - label: confirmed display label
        - name: internal node name
        - generation: ``"Genesis9"``, ``"Genesis8"``, ``"Genesis3"``, ``"Genesis2"``,
          ``"Genesis"``, or ``"other"``
        - sex: ``"female"``, ``"male"``, or ``"unknown"``
        - active_morphs: list of {name, label, value, path} for morphs with |value| > 0.0005
        - active_morph_count: length of active_morphs list
        - fitted_item_count: number of clothing/prop nodes following or parented to this figure
        - subdivision_level: current SubDivision Level value (0 if property absent)

    Examples:
        daz_get_figure_info("Genesis 9")
        daz_get_figure_info("Victoria 9")
        daz_get_figure_info("Michael 8")
    """
    return await _execute_by_id("vangard-get-figure-info", {"figureLabel": figure_label})


@mcp.tool()
async def daz_set_subdivision(node_label: str, level: int) -> dict[str, Any]:
    """Set the SubDivision Level property on a figure or prop.

    Higher subdivision levels smooth geometry at the cost of memory and render
    time.  Level 0 is base mesh; levels 1–4 progressively refine the mesh.
    DAZ Studio's default render subdivision is typically 1 or 2.

    Args:
        node_label: Display label of the figure or prop to adjust
            (e.g. ``"Genesis 9"`` or ``"Car Prop"``).
        level: Desired subdivision level.  Clamped to the range 0–4.

    Returns:
        Dict with keys:
        - success: true on success
        - node: confirmed node label
        - property: name of the subdivision property that was set
        - old_level: previous value
        - new_level: value after update

    Examples:
        daz_set_subdivision("Genesis 9", 2)
        daz_set_subdivision("Car Prop", 0)
        daz_set_subdivision("Hair", 1)

    Notes:
        Raises ToolError if the node has no subdivision property (e.g. a light
        or camera).  Use ``daz_get_figure_info`` to check the current level first.
    """
    if level < 0 or level > 4:
        raise ToolError(f"Subdivision level must be between 0 and 4, got {level}")
    return await _execute_by_id("vangard-set-subdivision", {"nodeLabel": node_label, "level": level})


@mcp.tool()
async def daz_export_fbx(
    output_path: str,
    node_labels: list[str] | None = None,
    include_morphs: bool = True,
    apply_current_pose: bool = True,
    scale_factor: float = 1.0,
) -> dict[str, Any]:
    """Export scene nodes to an FBX file via DAZ Studio's Filmbox exporter.

    Selects the specified nodes (or all scene nodes if none are given) and
    calls ``DzExportMgr.doExport`` with the ``"Filmbox"`` exporter.  Returns a
    graceful error if the FBX exporter plugin is not installed in DAZ Studio.

    FBX is the standard interchange format for game engines (Unreal, Unity) and
    VFX pipelines (Maya, 3ds Max, Blender).

    Args:
        output_path: Absolute path for the output ``.fbx`` file
            (e.g. ``"C:/exports/hero.fbx"``).  The parent directory must exist.
        node_labels: List of node display labels to export.  Pass ``None`` or an
            empty list to export all nodes in the scene.
        include_morphs: Whether to bake morph targets into the export (default True).
        apply_current_pose: Whether to export the current frame's pose (default True).
        scale_factor: Uniform scale applied to exported geometry (default 1.0).
            Use ``0.01`` to convert DAZ's centimetres to metres for Unity/Unreal.

    Returns:
        Dict with keys:
        - success: true on success
        - format: ``"Filmbox"``
        - output_path: path written
        - exported_nodes: list of node labels included in the export
        - node_count: number of exported nodes
        - include_morphs, apply_current_pose, scale_factor: echoed settings

    Examples:
        daz_export_fbx("C:/exports/hero.fbx")
        daz_export_fbx("C:/exports/hero.fbx", node_labels=["Genesis 9", "Sci-Fi Suit"])
        daz_export_fbx("C:/exports/hero.fbx", scale_factor=0.01, include_morphs=False)

    Notes:
        Raises ToolError if the FBX exporter is not installed.  The error message
        lists available exporters so you can choose an alternative format.
    """
    return await _execute_by_id(
        "vangard-export-scene",
        {
            "outputPath": output_path,
            "nodeLabels": node_labels or [],
            "format": "Filmbox",
            "includeMorphs": include_morphs,
            "applyCurrentPose": apply_current_pose,
            "scaleFactor": scale_factor,
        },
    )


@mcp.tool()
async def daz_export_obj(
    output_path: str,
    node_labels: list[str] | None = None,
    apply_current_pose: bool = True,
    scale_factor: float = 1.0,
) -> dict[str, Any]:
    """Export scene nodes to a Wavefront OBJ file via DAZ Studio's OBJ exporter.

    Selects the specified nodes (or all scene nodes if none are given) and
    calls ``DzExportMgr.doExport`` with the ``"Wavefront Object"`` exporter.
    Returns a graceful error if the OBJ exporter plugin is not installed.

    OBJ is a widely supported geometry-only format suitable for Blender,
    ZBrush, Marvelous Designer, and other tools that need a static mesh.
    It does not carry animations or morph targets.

    Args:
        output_path: Absolute path for the output ``.obj`` file
            (e.g. ``"C:/exports/hero_base.obj"``).  Parent directory must exist.
        node_labels: List of node display labels to export.  Pass ``None`` or an
            empty list to export all nodes in the scene.
        apply_current_pose: Whether to export the geometry in the current
            frame's posed state (default True).
        scale_factor: Uniform scale applied to exported geometry (default 1.0).

    Returns:
        Dict with keys:
        - success: true on success
        - format: ``"Wavefront Object"``
        - output_path: path written
        - exported_nodes: list of node labels included in the export
        - node_count: number of exported nodes
        - apply_current_pose, scale_factor: echoed settings

    Examples:
        daz_export_obj("C:/exports/hero_base.obj")
        daz_export_obj("C:/exports/suit.obj", node_labels=["Sci-Fi Suit"])
        daz_export_obj("C:/exports/hero_base.obj", scale_factor=0.01)

    Notes:
        OBJ does not support morph targets or animations.  Use ``daz_export_fbx``
        when you need those features.  Raises ToolError if the OBJ exporter is
        not installed.
    """
    return await _execute_by_id(
        "vangard-export-scene",
        {
            "outputPath": output_path,
            "nodeLabels": node_labels or [],
            "format": "Wavefront Object",
            "includeMorphs": False,
            "applyCurrentPose": apply_current_pose,
            "scaleFactor": scale_factor,
        },
    )
