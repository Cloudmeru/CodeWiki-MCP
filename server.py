"""Backward-compatible entry point — delegates to the codewiki_mcp package."""

from codewiki_mcp.server import main

if __name__ == "__main__":
    main()
