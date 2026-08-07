"""MCP server wrapping the DazScriptServer HTTP API for DAZ Studio.

Entry point: ``vangard-daz-mcp`` (defined in pyproject.toml).

All tool registrations happen when ``vangard_daz_mcp.tools`` is imported;
each sub-module decorates its functions with ``@mcp.tool()`` on the shared
FastMCP instance from ``_mcp.py``.

For convenience (and backward compatibility with the test suite), every
``daz_*`` tool function is also importable directly from this module.
"""

from ._mcp import mcp  # noqa: F401 — creates the FastMCP instance + lifespan
from . import tools  # noqa: F401 — registers all @mcp.tool() functions

__all__ = ["mcp", "main"]


def _tool_module_names() -> list[str]:
    return [
        "spatial",
        "transform",
        "scene",
        "figure",
        "morph",
        "camera_light",
        "render",
        "animation",
        "material",
        "utility",
        "content",
        "library",
        "cinematic",
        "wardrobe",
    ]


def __getattr__(name: str):
    """Re-export ``daz_*`` tools so they can be imported from ``server``.

    PEP 562 module ``__getattr__``: called only when normal attribute lookup
    fails, so it is a pure fallback and cannot shadow existing names.
    """
    if name.startswith("daz_"):
        for mod_name in _tool_module_names():
            module = getattr(tools, mod_name, None)
            if module is not None and hasattr(module, name):
                return getattr(module, name)
    if name == "_register_scripts":
        from ._registry import _register_scripts

        return _register_scripts
    if name == "CONTENT_BROWSER_URL":
        from ._client import CONTENT_BROWSER_URL

        return CONTENT_BROWSER_URL
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
