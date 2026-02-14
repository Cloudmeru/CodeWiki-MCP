"""CodeWiki MCP Server — modular server setup with CLI arguments.

Inspired by DeepWiki MCP's multi-transport and CLI-argument patterns.
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys

from mcp.server.fastmcp import FastMCP

from . import config
from .tools import register_all_tools

# ---------------------------------------------------------------------------
# Logging (configurable via CODEWIKI_VERBOSE)
# ---------------------------------------------------------------------------
logger = logging.getLogger("CodeWiki")
logger.setLevel(logging.DEBUG if config.VERBOSE else logging.INFO)
_handler = logging.StreamHandler(sys.stderr)
_handler.setFormatter(logging.Formatter("[%(name)s %(levelname)s] %(message)s"))
logger.addHandler(_handler)


# ---------------------------------------------------------------------------
# Graceful shutdown
# ---------------------------------------------------------------------------
def _shutdown(signum: int, _frame) -> None:
    """Handle SIGINT/SIGTERM — clean up Playwright and exit quietly."""
    sig_name = signal.Signals(signum).name
    logger.info("Received %s — shutting down…", sig_name)

    # Clean up the shared Playwright browser (best-effort)
    try:
        from .browser import (  # pylint: disable=import-outside-toplevel
            cleanup_browser,
            run_in_browser_loop,
        )

        run_in_browser_loop(cleanup_browser())
    except Exception:  # pylint: disable=broad-except
        pass

    logger.info("CodeWiki MCP server stopped.")
    sys.exit(0)


# ---------------------------------------------------------------------------
# Server factory
# ---------------------------------------------------------------------------
def create_server(name: str = "CodeWiki", *, transport: str = "stdio") -> FastMCP:
    """Create and configure the MCP server with all tools registered."""
    mcp = FastMCP(name)
    register_all_tools(mcp)
    logger.info("CodeWiki MCP server created (transport=%s)", transport)
    return mcp


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments (mirrors DeepWiki MCP's --http/--sse/--port flags)."""
    parser = argparse.ArgumentParser(
        prog="codewiki-mcp",
        description="CodeWiki MCP Server — AI-powered access to Google CodeWiki",
    )
    transport = parser.add_mutually_exclusive_group()
    transport.add_argument(
        "--stdio",
        action="store_const",
        const="stdio",
        dest="transport",
        help="Run with stdio transport (default)",
    )
    transport.add_argument(
        "--sse",
        action="store_const",
        const="sse",
        dest="transport",
        help="Run with SSE transport",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=3000,
        help="Port for SSE transport (default: 3000)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        default=config.VERBOSE,
        help="Enable verbose/debug logging",
    )
    parser.set_defaults(transport="stdio")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """CLI entry point — starts the MCP server with chosen transport."""
    args = parse_args(argv)

    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    # Update log level based on --verbose flag
    if args.verbose:
        logger.setLevel(logging.DEBUG)

    mcp = create_server(transport=args.transport)

    try:
        if args.transport == "sse":
            logger.info("Starting SSE server on port %d...", args.port)
            mcp.run(transport="sse")
        else:
            mcp.run()
    except KeyboardInterrupt:
        pass
    except SystemExit:
        pass
    finally:
        # Ensure Playwright cleanup even if signal handler didn't fire
        try:
            from .browser import (  # pylint: disable=import-outside-toplevel
                cleanup_browser,
                run_in_browser_loop,
            )

            run_in_browser_loop(cleanup_browser())
        except Exception:  # pylint: disable=broad-except
            pass
        logger.info("CodeWiki MCP server stopped.")


if __name__ == "__main__":
    main()
