"""Content-library intelligence: content roots, base-figure discovery, and DUF classification.

All discovery logic here is *deterministic* — the AI should not need to reason
about which content library is which, whether a character requires a base figure,
or whether a DUF's textures resolve. These tools answer those questions directly.
"""
from __future__ import annotations

import json as _json
import os
import re
from pathlib import Path
from typing import Any

from .._mcp import mcp, _execute_by_id


# ---------------------------------------------------------------------------
# Tool — registered content roots
# ---------------------------------------------------------------------------


@mcp.tool()
async def daz_list_content_libraries() -> dict[str, Any]:
    """List every content library directory registered in DAZ Studio.

    DAZ Studio reads from multiple content roots (e.g. a per-user "My Library"
    for third-party items and a shared "My DAZ 3D Library" for DAZ3D shop
    purchases). This tool enumerates all of them deterministically.

    Returns:
      - libraries: list of {full_path, name, is_public, duf_count, duf_count_capped}
      - count: number of libraries found

    Example:
        libs = daz_list_content_libraries()
        for lib in libs["libraries"]:
            print(lib["name"], lib["full_path"], lib["duf_count"])
    """
    return await _execute_by_id("vangard-list-libraries", None)


@mcp.tool()
async def daz_list_base_figures(generation: str = "") -> dict[str, Any]:
    """Find base figure .duf files across all content roots.

    Base figures are the starter figures DAZ Studio installs (e.g. "Genesis 8
    Basic Female.duf", "Genesis 9.duf"). Character presets such as skins or
    characters must be applied **onto** an existing base figure, so discovering
    the correct base for a given generation is the deterministic first step of
    any scene build.

    Args:
        generation: Optional filter against the People/ subfolder name
                    (case-insensitive substring), e.g. "Genesis 8 Female" or
                    "Genesis 9". Leave empty for every generation.

    Returns:
      - generation: resolved generation filter ("all" if empty)
      - bases: list of {"generation", "filename", "full_path"}
      - count: number of base figures found

    Example:
        bases = daz_list_base_figures("Genesis 8 Female")
        base_path = bases["bases"][0]["full_path"]
    """
    return await _execute_by_id("vangard-list-base-figures", {"generation": generation})


# ---------------------------------------------------------------------------
# Tool — deterministic DUF asset inspection (pure local file parse)
# ---------------------------------------------------------------------------

# Canonical content roots (typical DAZ installs). Used only for texture
# resolution during local inspection; exact roots are whatever DAZ reports via
# daz_list_content_libraries at runtime.
_DEFAULT_CONTENT_ROOTS: list[str] = [
    str(Path.home() / "Documents" / "DAZ 3D" / "Studio" / "My Library"),
    r"C:\Users\Public\Documents\My DAZ 3D Library",
    r"C:\Users\Public\Documents\DAZ 3D\Studio\My Library",
]


@mcp.tool()
async def daz_inspect_asset(file_path: str) -> dict[str, Any]:
    """Inspect a .duf asset file WITHOUT loading it into the scene.

    Deterministically classifies what the asset is, whether it needs a base
    figure, and whether its referenced textures actually exist on disk — so the
    AI can pick the correct loading strategy before touching the scene.

    Args:
        file_path: Absolute path to a .duf file on disk.

    Returns:
      - kind: One of:
          full_character   — self-contained character (builds a full figure)
          character_set    — must be applied onto an existing base figure
          figure           — a base/starter figure object with geometry
          material         — surface/shader preset
          hair / clothing  — fitted accessories
          environment      — environment / backdrop set
          prop             — prop / accessory
          pose             — pose preset
          scene            — a full scene file
          unknown
      - requires_base: true when this asset must be applied onto a loaded base figure
      - fits_base: the base generation it targets (e.g. "Genesis 8 Female"), if any
      - textures: {"referenced", "existing", "missing", "missing_paths"}
      - assets_stats: {"nodes", "figure_nodes", "geometries", "draw_to_selection"}
      - suggestion: one line of guidance on how to load it

    Example:
        info = daz_inspect_asset(r"C:__/Carmen.duf")
        # kind "character_set", requires_base True, fits_base "Genesis 8 Female"
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    if path.suffix.lower() != ".duf":
        return {
            "path": str(path),
            "kind": "not_a_duf",
            "suggestion": "Only .duf files are supported.",
        }

    try:
        with open(path, encoding="utf-8") as f:
            data = _json.load(f)
    except (OSError, _json.JSONDecodeError) as e:
        return {"path": str(path), "kind": "unparsable", "error": str(e)}

    result = _classify_duf(data, path)
    result["path"] = str(path)
    result["name"] = path.stem
    return result


# ---------------------------------------------------------------------------
# Deterministic classification (pure python — no DAZ requirement)
# ---------------------------------------------------------------------------

_RE_HAIR = re.compile(r"/Hair/", re.IGNORECASE)
_RE_CLOTHING = re.compile(r"/(?:Clothing|Outfit)/", re.IGNORECASE)
_RE_POSE = re.compile(r"/(?:Poses|Pose)/", re.IGNORECASE)
_RE_ENV = re.compile(r"/(?:Environments|Environment)/", re.IGNORECASE)
_RE_PEOPLE_GEN = re.compile(r"/People/([^/]+)/", re.IGNORECASE)


def _classify_duf(data: dict[str, Any], path: Path) -> dict[str, Any]:
    asset_info = data.get("asset_info", {}) or {}
    type_info = str(asset_info.get("type", "") or "")
    scene = data.get("scene", {}) or {}
    nodes = scene.get("nodes", []) or []
    rel = str(path).replace("\\", "/")

    # Deterministic per-node signals.
    parents_to_selection = 0
    geometries = 0
    figure_nodes = 0
    for node in nodes:
        if "@selection" in str(node.get("parent", "") or ""):
            parents_to_selection += 1
        geo = node.get("geometries")
        if isinstance(geo, list):
            geometries += len(geo)
        preview = node.get("preview", {}) or {}
        if preview.get("type") == "figure":
            figure_nodes += 1

    kind, requires_base = _resolve_kind(
        type_info=type_info,
        rel=rel,
        node_count=len(nodes),
        parents_to_selection=parents_to_selection,
        figure_nodes=figure_nodes,
        geometries=geometries,
    )
    fits_base = _hint_base_generation(rel)

    return {
        "kind": kind,
        "type": type_info or "none",
        "requires_base": requires_base,
        "fits_base": fits_base,
        "file_version": str(data.get("file_version", "")),
        "revision": str(asset_info.get("revision", "")),
        "asset_stats": {
            "nodes": len(nodes),
            "figure_nodes": figure_nodes,
            "draw_targets_selection": parents_to_selection,
            "geometries": geometries,
        },
        "textures": _validate_textures(data),
        "suggestion": _suggestion_for(kind, requires_base, fits_base),
    }


def _resolve_kind(
    type_info: str,
    rel: str,
    node_count: int,
    parents_to_selection: int,
    figure_nodes: int,
    geometries: int,
) -> tuple[str, bool]:
    t = type_info.lower()

    if t in ("material", "shader"):
        return "material", False
    if _RE_POSE.search(rel):
        return "pose", False
    if _RE_ENV.search(rel):
        return "environment", False
    if t == "environment":
        return "environment", False
    if t == "scene":
        return "scene", False
    if t == "item":
        return "prop", False

    if figure_nodes > 0 and parents_to_selection > 0:
        if _RE_HAIR.search(rel):
            return "hair", False
        if _RE_CLOTHING.search(rel):
            return "clothing", False
        return "character_set", True

    if figure_nodes > 0:
        return "full_character", False

    if node_count == 0:
        if _RE_HAIR.search(rel) or _RE_CLOTHING.search(rel):
            return file_kind_for(rel), False
        return "prop", False

    if geometries > 0:
        if _RE_HAIR.search(rel):
            return "hair", False
        if _RE_CLOTHING.search(rel):
            return "clothing", False
        return "prop", False

    return "unknown", False


def file_kind_for(rel: str) -> str:
    if _RE_HAIR.search(rel):
        return "hair"
    if _RE_CLOTHING.search(rel):
        return "clothing"
    if _RE_POSE.search(rel):
        return "pose"
    if _RE_ENV.search(rel):
        return "environment"
    return "unknown"


def _hint_base_generation(rel: str) -> str:
    m = _RE_PEOPLE_GEN.search(rel)
    return m.group(1).strip() if m else ""


def _suggestion_for(kind: str, requires_base: bool, fits_base: str) -> str:
    if requires_base:
        target = fits_base or "matching base"
        return f"Preset — apply onto a loaded {target} base figure (see daz_load_character)."
    if kind == "full_character":
        return "Full character — load directly into an empty scene."
    if kind == "figure":
        return "Base figure — load as the foundation, then apply a character preset."
    if kind == "environment":
        return "Environment set — load with a figure present."
    if kind in ("hair", "clothing"):
        return f"Accessory — fit onto the {fits_base or 'base'} figure after loading it."
    if kind == "prop":
        return "Prop — load and position in the scene."
    if kind == "material":
        return "Material preset — apply to an existing surface."
    if kind == "pose":
        return "Pose preset — apply to an existing figure."
    if kind == "scene":
        return "Full scene — loads its own figures, cameras, and lights."
    return "Unknown asset — inspect manually before loading."


# ---------------------------------------------------------------------------
# Texture reference validation (local disk check across content roots)
# ---------------------------------------------------------------------------


def _validate_textures(data: dict[str, Any]) -> dict[str, Any]:
    urls: list[str] = []
    _collect_urls(data.get("material_library", []) or [], urls)
    scene = data.get("scene", {}) or {}
    _collect_urls(scene.get("materials", {}) or {}, urls)

    missing: list[str] = []
    for url in urls:
        if not any(_texture_exists(url, root) for root in _DEFAULT_CONTENT_ROOTS):
            missing.append(url)
    return {
        "referenced": len(urls),
        "existing": len(urls) - len(missing),
        "missing": len(missing),
        "missing_paths": missing[:20],
    }


def _texture_exists(url: str, root: str) -> bool:
    candidate = root.replace("\\", "/") + "/" + url.lstrip("/")
    p = Path(candidate) if os.sep == "/" else Path(candidate.replace("/", "\\"))
    return p.exists()


def _collect_urls(obj: Any, acc: list[str]) -> None:
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key == "url" and isinstance(value, str) and value.startswith("/"):
                acc.append(value)
            else:
                _collect_urls(value, acc)
    elif isinstance(obj, list):
        for item in obj:
            _collect_urls(item, acc)


def classify_kind_sync(file_path: str) -> str:
    """Synchronous, disk-only kind classification used by non-async callers.

    Returns the same ``kind`` string as daz_inspect_asset, or "unknown" /
    "unparsable" on failure. Safe to call from anywhere (no DAZ or network).
    """
    path = Path(file_path)
    if not path.exists():
        return "unknown"
    try:
        with open(path, encoding="utf-8") as f:
            data = _json.load(f)
    except (OSError, _json.JSONDecodeError):
        return "unparsable"
    return _classify_duf(data, path).get("kind", "unknown")


# ---------------------------------------------------------------------------
# Local helper — resolve a base figure .duf for a generation (deterministic)
# ---------------------------------------------------------------------------

_BASE_CHARS = re.compile(r"[^A-Za-z0-9]+")


def _gen_matches(generation: str, folder: str) -> int:
    """Fitness (score) of a People/<folder> for a generation.

    Returns 0 when the folder cannot provide the generation, otherwise higher
    = better. An exact normalized folder name wins over a substring folder.
    """
    g = _BASE_CHARS.sub("", (generation or "")).lower()
    f = _BASE_CHARS.sub("", folder).lower()
    if not g:
        return 0
    if g == f:
        return 3
    if g in f:
        return 1
    return 0


def resolve_base_file(generation: str, roots: list[str] | None = None) -> str | None:
    """Deterministically locate a base figure .duf for a generation.

    Base figures sit at ``People/<generation>/*.duf`` (e.g. "Genesis 8 Basic
    Female.duf", "Genesis 9.duf") — the top-level files under the generation
    folder, not the nested Characters/ folders. Preference order:
       1) a folder that exactly matches the generation name,
       2) among them, a file whose stem contains the "Basic" figure marker
          (preferred for Genesis 8 — "Genesis 8 Basic Female"),
       3) the file whose stem equals the generation itself ("Genesis 9.duf").
    """
    roots = roots or _DEFAULT_CONTENT_ROOTS
    if not generation:
        return None

    best: list[tuple[int, int, str]] = []  # (folder_score, file_score, path)
    for root in roots:
        people = Path(root) / "People"
        if not people.is_dir():
            continue
        for folder in people.iterdir():
            if not folder.is_dir():
                continue
            folder_score = _gen_matches(generation, folder.name)
            if folder_score == 0:
                continue
            for f in folder.glob("*.duf"):
                stem = f.stem.lower()
                file_score = 0
                if "basic" in stem:
                    file_score = 3
                elif _gen_matches(generation, f.stem) >= 1:
                    file_score = 2
                best.append((folder_score, file_score, str(f)))

    # People/<generation>/<generation>.duf sits directly under People/ in
    # newer installs (e.g. People/Genesis 9.duf). Check that too.
    for root in roots:
        direct = Path(root) / "People" / f"{generation}.duf"
        if direct.is_file():
            best.append((3, 2, str(direct)))

    if not best:
        return None
    best.sort(key=lambda triple: (-triple[0], -triple[1], triple[2]))
    return best[0][2]