"""Integration tests — scene state, checkpoints, macros, and validation.

Tools covered
-------------
- daz_validate_scene           (scene health check)
- daz_save_scene_state         (in-memory checkpoint)
- daz_restore_scene_state      (restore checkpoint)
- daz_list_checkpoints         (list saved checkpoints)
- daz_start_recording          (begin macro capture)
- daz_stop_recording           (end macro capture)
- daz_list_macros              (list recorded macros)
- daz_replay_macro             (replay a macro)
"""

from __future__ import annotations

import json

import pytest
import pytest_asyncio
from fastmcp.exceptions import ToolError

from vangard_daz_mcp._client import get_daz_client, run_dazpy
from vangard_daz_mcp.tools.scene import (
    daz_list_checkpoints,
    daz_restore_scene_state,
    daz_save_scene_state,
)
from vangard_daz_mcp.tools.transform import daz_set_property
from vangard_daz_mcp.tools.utility import (
    daz_list_macros,
    daz_replay_macro,
    daz_start_recording,
    daz_stop_recording,
    daz_validate_scene,
)


# ---------------------------------------------------------------------------
# daz_validate_scene
# ---------------------------------------------------------------------------

class TestValidateScene:
    async def test_returns_dict(self, live_client):
        result = await daz_validate_scene()
        assert isinstance(result, dict)

    async def test_has_health_indicator(self, live_client):
        result = await daz_validate_scene()
        text = str(result).lower()
        assert any(k in text for k in ["valid", "issue", "warning", "ok", "pass", "error"])


# ---------------------------------------------------------------------------
# daz_save_scene_state / daz_restore_scene_state / daz_list_checkpoints
# ---------------------------------------------------------------------------

class TestSceneCheckpoints:
    CHECKPOINT = "test_checkpoint_integration"

    async def test_save_checkpoint(self, live_client, figure_label):
        result = await daz_save_scene_state(self.CHECKPOINT)
        assert isinstance(result, dict)

    async def test_saved_checkpoint_appears_in_list(self, live_client, figure_label):
        await daz_save_scene_state(self.CHECKPOINT)
        result = await daz_list_checkpoints()
        assert isinstance(result, dict)
        checkpoints = result.get("checkpoints", result.get("names", []))
        assert isinstance(checkpoints, list)
        # The checkpoint name should appear in the list
        names = [
            (c if isinstance(c, str) else c.get("name", ""))
            for c in checkpoints
        ]
        assert self.CHECKPOINT in names

    async def test_restore_checkpoint(self, live_client, figure_label):
        # Save current state
        await daz_save_scene_state(self.CHECKPOINT)
        # Modify something
        await daz_set_property(figure_label, "XTranslate", 10.0)
        # Restore
        result = await daz_restore_scene_state(self.CHECKPOINT)
        assert isinstance(result, dict)
        # Clean up translation
        await daz_set_property(figure_label, "XTranslate", 0.0)

    async def test_list_checkpoints_without_figure(self, live_client):
        result = await daz_list_checkpoints()
        assert isinstance(result, dict)

    async def test_restore_missing_checkpoint_raises(self, live_client):
        with pytest.raises((ToolError, KeyError, Exception)):
            await daz_restore_scene_state("checkpoint_that_does_not_exist_xyz_999")

    async def test_repeated_save_restore_does_not_inflate_erc_driven_property(
        self, live_client, figure_label
    ):
        """Regression test for a checkpoint-fidelity bug.

        A property driven by DzERCLink controllers (e.g. a "Scale" dial fed
        by other morphs) returns a computed total from getValue() that
        already includes every controller's contribution. The old
        implementation captured that computed total and wrote it straight
        back via setValue() on restore, which re-applies the same ERC
        contributions on top -- inflating the property a little more on
        every save/restore cycle even though nothing in the scene actually
        changed. This asserts the fix (getRawValue()/setRawValue()) makes
        repeated cycles idempotent.
        """
        def _read_scale_raw() -> float | None:
            label_json = json.dumps(figure_label)
            script = f"""(function(){{
                var _skels = Scene.getSkeletonList();
                var _s = null;
                for (var _i = 0; _i < _skels.length; _i++) {{
                    if (_skels[_i].getLabel() === {label_json}) {{ _s = _skels[_i]; break; }}
                }}
                if (!_s) return null;
                return _s.getScaleControl().getRawValue();
            }})();"""
            return get_daz_client().execute(script).value

        baseline = await run_dazpy(_read_scale_raw)
        if baseline is None:
            pytest.skip(f"Could not resolve scale control for {figure_label!r}")

        for _ in range(3):
            await daz_save_scene_state(self.CHECKPOINT)
            await daz_restore_scene_state(self.CHECKPOINT)

        after = await run_dazpy(_read_scale_raw)
        assert after == pytest.approx(baseline, abs=1e-6), (
            f"Scale raw value drifted from {baseline} to {after} across "
            "repeated save/restore cycles -- checkpoint restore is not idempotent"
        )


# ---------------------------------------------------------------------------
# daz_start_recording / daz_stop_recording / daz_list_macros / daz_replay_macro
# ---------------------------------------------------------------------------

class TestMacroSystem:
    MACRO_NAME = "test_macro_integration"

    async def test_start_recording(self, live_client):
        result = await daz_start_recording(self.MACRO_NAME, description="Integration test macro")
        assert isinstance(result, dict)
        # Clean up: stop recording immediately
        await daz_stop_recording()

    async def test_stop_recording(self, live_client):
        await daz_start_recording(self.MACRO_NAME)
        result = await daz_stop_recording()
        assert isinstance(result, dict)

    async def test_recorded_macro_in_list(self, live_client):
        await daz_start_recording(self.MACRO_NAME)
        await daz_stop_recording()
        result = await daz_list_macros()
        assert isinstance(result, dict)
        macros = result.get("macros", result.get("names", []))
        assert isinstance(macros, list)
        names = [
            (m if isinstance(m, str) else m.get("name", ""))
            for m in macros
        ]
        assert self.MACRO_NAME in names

    async def test_list_macros_returns_dict(self, live_client):
        result = await daz_list_macros()
        assert isinstance(result, dict)

    async def test_replay_empty_macro(self, live_client):
        """Record an empty macro (no operations) and replay it — should not error."""
        await daz_start_recording(self.MACRO_NAME + "_empty")
        await daz_stop_recording()
        result = await daz_replay_macro(self.MACRO_NAME + "_empty")
        assert isinstance(result, dict)

    async def test_replay_missing_macro_raises(self, live_client):
        with pytest.raises((ToolError, KeyError, Exception)):
            await daz_replay_macro("macro_that_does_not_exist_xyz_999")
