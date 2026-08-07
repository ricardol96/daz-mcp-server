"""Integration + unit tests for the asset-intelligence layer.

Covers the deterministic (no-DAZ) and live tools:
- daz_inspect_asset       (pure local DUF parse)
- daz_list_content_libraries
- daz_list_base_figures
- daz_load_character      (live: base resolution + preset apply)
- daz_scene_health
- daz_render_shot
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from fastmcp.exceptions import ToolError

from vangard_daz_mcp.server import (
    daz_inspect_asset,
    daz_list_base_figures,
    daz_list_content_libraries,
    daz_load_character,
    daz_render_shot,
    daz_scene_health,
)
from vangard_daz_mcp.tools.library import classify_kind_sync, resolve_base_file


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _duf(kind: str = "character_set") -> dict:
    """A minimal structurally-valid DUF for the deterministic classifier."""
    scene_nodes = []
    asset_type = None
    if kind == "figure":
        asset_type = "figure"
        scene_nodes = [
            {"name": "Genesis8", "preview": {"type": "figure"}, "geometries": ["geo1"]}
        ]
    elif kind == "character_set":
        asset_type = "character"
        scene_nodes = [
            {
                "name": "Skin",
                "preview": {"type": "figure"},
                "parent": "@selection",
                "geometries": ["geo1"],
            }
        ]
    elif kind == "material":
        asset_type = "material"
    elif kind == "environment":
        asset_type = "environment"
    return {
        "file_version": "0.6.0.0",
        "asset_info": {"id": "/test/asset-" + kind, "type": asset_type},
        "scene": {"nodes": scene_nodes},
    }


def _write_duf(tmp_path: Path, name: str, data: dict) -> Path:
    p = tmp_path / name
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Unit: deterministic classifier (no DAZ needed)
# ---------------------------------------------------------------------------


class TestClassifyDuf:
    @pytest.mark.parametrize(
        "kind,expected",
        [
            ("character_set", "character_set"),
            ("material", "material"),
            ("environment", "environment"),
            ("figure", "full_character"),
        ],
    )
    async def test_kinds(self, tmp_path, kind, expected):
        p = _write_duf(tmp_path, f"test_{kind}.duf", _duf(kind))
        info = await daz_inspect_asset(str(p))
        assert info["kind"] == expected

    async def test_character_set_requires_base(self, tmp_path):
        p = _write_duf(tmp_path, "preset.duf", _duf("character_set"))
        info = await daz_inspect_asset(str(p))
        assert info["requires_base"] is True
        assert info["suggestion"].startswith("Preset")

    async def test_full_figure_no_base(self, tmp_path):
        data = _duf("figure")
        data["asset_info"]["type"] = "character"
        p = _write_duf(tmp_path, "figure.duf", data)
        info = await daz_inspect_asset(str(p))
        assert info["requires_base"] is False
        assert info["kind"] == "full_character"

    async def test_duf_missing_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            await daz_inspect_asset(str(tmp_path / "nope.duf"))

    async def test_not_a_duf(self, tmp_path):
        p = tmp_path / "notes.txt"
        p.write_text("hello", encoding="utf-8")
        info = await daz_inspect_asset(str(p))
        assert info["kind"] == "not_a_duf"


class TestClassifySync:
    def test_sync_kind_parse(self, tmp_path):
        p = _write_duf(tmp_path, "preset.duf", _duf("character_set"))
        assert classify_kind_sync(str(p)) == "character_set"

    def test_sync_missing_file(self, tmp_path):
        assert classify_kind_sync(str(tmp_path / "missing.duf")) == "unknown"


# ---------------------------------------------------------------------------
# Unit: resolve_base_file (deterministic local scan)
# ---------------------------------------------------------------------------


class TestResolveBase:
    def test_resolves_exact_folder_prefers_basic(self, tmp_path):
        gen = tmp_path / "People" / "Genesis 8 Female"
        gen.mkdir(parents=True)
        (gen / "Genesis 8 Basic Female.duf").write_text("{}")
        (gen / "Helen.duf").write_text("{}")
        found = resolve_base_file("Genesis 8 Female", roots=[str(tmp_path)])
        assert found is not None
        assert found.endswith("Genesis 8 Basic Female.duf")

    def test_substring_folder_ignored_when_exact_exists(self, tmp_path):
        # "Genesis 9 Toon" contains "Genesis 9" but the exact folder must win.
        people = tmp_path / "People"
        (people / "Genesis 9").mkdir(parents=True)
        (people / "Genesis 9" / "Genesis 9.duf").write_text("{}")
        (people / "Genesis 9 Toon").mkdir()
        (people / "Genesis 9 Toon" / "Basic FilaToon Environment.duf").write_text("{}")
        found = resolve_base_file("Genesis 9", roots=[str(tmp_path)])
        assert found is not None
        assert found.endswith("Genesis 9.duf")

    def test_no_match_returns_none(self, tmp_path):
        assert resolve_base_file("Genesis 99", roots=[str(tmp_path)]) is None

    def test_empty_generation(self, tmp_path):
        assert resolve_base_file("", roots=[str(tmp_path)]) is None


# ---------------------------------------------------------------------------
# Live tools (require DAZ Studio + DAZ_LIVE_TESTS=1)
# ---------------------------------------------------------------------------


class TestLibraryLive:
    async def test_list_content_libraries(self, live_client):
        result = await daz_list_content_libraries()
        libs = result.get("libraries", [])
        assert isinstance(libs, list)
        assert len(libs) >= 1
        assert all("full_path" in lib for lib in libs)

    async def test_list_base_figures(self, live_client):
        result = await daz_list_base_figures("Genesis 8 Female")
        assert isinstance(result.get("bases", []), list)

        result_all = await daz_list_base_figures("")
        assert isinstance(result_all.get("bases", []), list)

    async def test_scene_health(self, live_client):
        health = await daz_scene_health()
        assert isinstance(health, dict)
        assert "render_ready" in health
        assert "figures" in health
        assert "totalNodes" in health

    async def test_load_character_auto_base(self, tmp_path, live_client):
        """End-to-end: resolve base + apply a real character preset.

        Uses Carmen.duf (ships with the user content library here); skips
        cleanly if that exact preset or its generation is unavailable.
        """
        from vangard_daz_mcp.tools.library import resolve_base_file

        preset_candidates = [
            Path(os.environ["USERPROFILE"])
            / "Documents"
            / "DAZ 3D"
            / "Studio"
            / "My Library"
            / "People"
            / "Genesis 8 Female"
            / "Characters"
            / "Carmen.duf",
        ]
        preset = next((p for p in preset_candidates if p.exists()), None)
        if preset is None:
            pytest.skip("no known character preset on this machine")
        base = resolve_base_file("Genesis 8 Female")
        if not base:
            pytest.skip("no Genesis 8 base figure on this machine")

        result = await daz_load_character(str(preset), base_figure=base)
        assert isinstance(result, dict)
        assert result.get("loaded") == "preset"
        assert "inspected" in result
        assert result["inspected"]["kind"] == "character_set"
        assert "scene" in result


# NOTE: daz_render_shot is expensive and mutates render output settings; it is
# not part of every DAZ_LIVE_TESTS=1 run. It is exercised by the manual render
# workflow documented in AGENTS.md instead.