"""Content browser tools: category listing, browsing, metadata, search, and product loading."""
from __future__ import annotations

import json as _json
import os
from pathlib import Path
from typing import Any

import httpx
from fastmcp.exceptions import ToolError

from .._mcp import mcp, _execute_by_id
from .._client import get_content_browser_client, CONTENT_BROWSER_URL


# ---------------------------------------------------------------------------
# Tools — content library (DAZ Studio Script Server registered scripts)
# ---------------------------------------------------------------------------


@mcp.tool()
async def daz_list_categories(parent_path: str = "") -> dict[str, Any]:
    """List content library category subdirectories under a parent path.

    Searches across all configured DAZ content directories and deduplicates by name.

    Args:
        parent_path: Relative path within content directories to list (e.g. "People/Genesis 9").
                     Leave empty to list top-level categories.

    Returns:
        Dict with parent, categories (list of {name, path, duf_count}), and count.

    Example:
        daz_list_categories()                      # top-level: People, Props, Environments...
        daz_list_categories("People/Genesis 9")    # sub-folders: Characters, Clothing, Hair...
    """
    return await _execute_by_id("vangard-list-categories", {"parentPath": parent_path})


@mcp.tool()
async def daz_browse_category(
    category_path: str,
    sort_by: str = "name",  # pylint: disable=unused-argument
    # Only "name" is currently supported; see docstring below.
) -> dict[str, Any]:
    """List .duf content files in a content library category path.

    Searches all configured DAZ content directories and deduplicates by filename.

    Args:
        category_path: Relative path within content directories (e.g. "People/Genesis 9/Hair").
        sort_by: Sort order — only "name" is currently supported (alphabetical).

    Returns:
        Dict with category, items (list of {name, filename, full_path}), and count.

    Example:
        daz_browse_category("People/Genesis 9/Hair")
        daz_browse_category("Props/Furniture")
    """
    return await _execute_by_id("vangard-browse-category", {"categoryPath": category_path})


@mcp.tool()
async def daz_get_content_info(file_path: str) -> dict[str, Any]:
    """Read metadata from a .duf content file without loading it into the scene.

    Parses the JSON structure of a .duf file to extract name, type, contributor,
    and other available metadata fields.

    Args:
        file_path: Absolute path to a .duf file on disk.

    Returns:
        Dict with name, type, file_version, contributor, revision, modified, and
        any scene-level asset info found in the file.

    Raises:
        ToolError: If the file does not exist, is not readable, or is not valid JSON.
    """
    path = Path(file_path)
    if not path.exists():
        raise ToolError(f"File not found: {file_path}")
    if not path.suffix.lower() == ".duf":
        raise ToolError(f"Not a .duf file: {file_path}")

    try:
        with open(path, encoding="utf-8") as f:
            data = _json.load(f)
    except (OSError, _json.JSONDecodeError) as e:
        raise ToolError(f"Failed to read {file_path}: {e}") from e

    asset_info = data.get("asset_info", {})
    contributor = asset_info.get("contributor", {})

    result: dict[str, Any] = {
        "path": str(path),
        "name": path.stem,
        "file_version": data.get("file_version", "unknown"),
        "asset_id": asset_info.get("id", ""),
        "type": asset_info.get("type", "unknown"),
        "revision": asset_info.get("revision", ""),
        "modified": asset_info.get("modified", ""),
        "contributor": {
            "author": contributor.get("author", ""),
            "studio": contributor.get("studio", ""),
            "website": contributor.get("website", ""),
        },
    }

    # Try to extract a human-readable description from common locations
    if "scene" in data:
        scene = data["scene"]
        nodes = scene.get("nodes", [])
        if nodes:
            first = nodes[0]
            result["label"] = first.get("label", path.stem)
            if "description" in first:
                result["description"] = first["description"]

    return result


# ---------------------------------------------------------------------------
# Tools — content browser FastAPI server
# ---------------------------------------------------------------------------


@mcp.tool()
async def daz_search_content(query: str, max_results: int = 10) -> dict[str, Any]:
    """Search the DAZ product catalog using semantic vector search.

    Calls the daz-content-browser FastAPI server (POST /api/v1/search).
    Returns a list of matching products with sku, name, description,
    compatible_figures, tags, and store_url fields.

    Returns {"available": false, "reason": "..."} gracefully if the content
    browser is not running.

    Args:
        query: Natural-language search query, e.g. "sci-fi armor for Genesis 9".
        max_results: Maximum number of results to return (default 10).
    """
    client = get_content_browser_client()
    try:
        response = await client.post(
            "/api/v1/search",
            json={"query": query, "max_results": max_results},
        )
    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.TimeoutException):
        return {
            "available": False,
            "reason": "Content browser not reachable at " + CONTENT_BROWSER_URL,
        }
    if response.status_code != 200:
        return {
            "available": False,
            "reason": f"Content browser returned HTTP {response.status_code}",
        }
    return response.json()


@mcp.tool()
async def daz_load_product(product_name: str) -> dict[str, Any]:
    """Find a DAZ product by name and load it into the current scene.

    Queries the daz-content-browser product index (GET /api/v1/products?q=<name>)
    to resolve the absolute .duf path, then calls POST /api/v1/scene/load which
    delegates to the DazScriptServer to merge the asset into the scene.

    Returns {"available": false, "reason": "..."} gracefully if the content
    browser is not running or no matching product is found.

    Args:
        product_name: Partial or full product name to search for.
    """
    client = get_content_browser_client()
    try:
        search_response = await client.get("/api/v1/products", params={"q": product_name})
    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.TimeoutException):
        return {
            "available": False,
            "reason": "Content browser not reachable at " + CONTENT_BROWSER_URL,
        }
    if search_response.status_code != 200:
        return {
            "available": False,
            "reason": f"Content browser returned HTTP {search_response.status_code}",
        }

    products = search_response.json()
    if isinstance(products, dict):
        products = products.get("products", products.get("results", []))
    if not products:
        return {
            "available": True,
            "found": False,
            "reason": f"No product found matching '{product_name}'",
        }

    product = products[0]
    duf_path = product.get("path") or product.get("file_path") or product.get("duf_path")
    if not duf_path:
        return {
            "available": True,
            "found": True,
            "error": "Product record has no file path",
            "product": product,
        }

    try:
        load_response = await client.post("/api/v1/scene/load", json={"path": duf_path})
    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.TimeoutException):
        return {"available": False, "reason": "Content browser not reachable during load"}
    if load_response.status_code != 200:
        return {
            "available": False,
            "reason": f"Scene load returned HTTP {load_response.status_code}",
        }

    result = load_response.json()
    result["product"] = product
    return result


# ---------------------------------------------------------------------------
# Tools — asset compatibility
# ---------------------------------------------------------------------------


@mcp.tool()
async def daz_check_compatibility(asset_path: str, figure_label: str) -> dict[str, Any]:
    """Check if an asset is compatible with the specified figure generation.

    Reads the asset's .duf file to inspect compatible_figures metadata.
    """
    try:
        if not os.path.exists(asset_path):
            return {"compatible": False, "reason": "Asset file not found"}
        with open(asset_path, encoding="utf-8") as f:
            data = _json.load(f)
        asset_info = data.get("asset_info", {})
        compatible = asset_info.get("compatible_figures", [])
        return {
            "asset_path": asset_path,
            "figure_label": figure_label,
            "compatible_figures": compatible,
            "likely_compatible": any(
                figure_label.lower() in str(c).lower() or str(c).lower() in figure_label.lower()
                for c in compatible
            ) if compatible else None,
        }
    except Exception as e:
        return {"compatible": None, "error": str(e)}
