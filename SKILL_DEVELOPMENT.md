# Skill: MCP Systems Architect
Technical documentation for server internals and the MCP bridge.

## Communication Flow
`MCP client → FastMCP → httpx.AsyncClient → DazScriptServer (18811) → DAZ Studio`

## Module Layout (v0.4.0)
- `server.py` — 15-line entry point; imports `_mcp` then `tools`
- `_mcp.py` — shared `FastMCP` instance, lifespan, `_execute*` helpers
- `_client.py` — httpx client singleton + env config (`DAZ_HOST`, `DAZ_PORT`, `DAZ_TIMEOUT`, `DAZ_API_TOKEN`, `DAZ_CONTENT_BROWSER_URL`)
- `_errors.py` — `handle_network_error()`, `check_response()`
- `_registry.py` — `_register_scripts()` with all pre-registered script payloads
- `tools/__init__.py` — imports all 13 tool modules (137 tools total)
- `tools/<module>.py` — each module imports `mcp` from `_mcp` and registers `@mcp.tool()` functions

## Adding a New Tool
1. Pick the appropriate module in `tools/` (or create a new one and add it to `tools/__init__.py`)
2. Import `mcp` from `.._mcp` and decorate with `@mcp.tool()`
3. Use `_execute()`, `_execute_by_id()`, or dazpy via `asyncio.to_thread`
4. If using a registered script, add its payload to `_registry.py`

## Script Registry System
- **Registration:** `_register_scripts()` runs at startup via lifespan.
- **Execution:** Uses `POST /scripts/:id/execute` for performance.
- **Auto-Retry:** On 404 (DAZ restart), the server re-registers and retries the call.

## Testing Standards
- Use `respx` for HTTP transport mocking.
- Tests call tool functions directly (e.g., `await daz_status()`).
- Import tool functions from their module (e.g., `from vangard_daz_mcp.tools.utility import daz_status`).

## Macros & Checkpoints
- `daz_start_recording` / `daz_stop_recording`: Session-based macro storage.
- `daz_save_scene_state` / `daz_restore_scene_state`: In-memory checkpoint of every skeleton's
  complete pose (bone rotations, morphs, node properties — via dazpy's `DazSceneState`/`DazPose`)
  plus camera/light transforms. Uses each property's raw (pre-formula) value throughout, so
  repeated save/restore cycles are idempotent even for properties driven by other linked dials
  (e.g. a custom character's Scale control fed by several morphs).
