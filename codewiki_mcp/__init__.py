"""CodeWiki MCP Server — AI-powered access to Google CodeWiki."""

from importlib.metadata import version, PackageNotFoundError

try:
    __version__: str = version("codewiki-mcp")
except PackageNotFoundError:
    __version__ = "0.0.0-dev"
