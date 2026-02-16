#!/usr/bin/env python3
"""Bump the project version in pyproject.toml and propagate to all docs.

Usage
-----
    python scripts/bump_version.py <new_version>

Example
-------
    python scripts/bump_version.py 1.1.0

This script:
  1. Updates ``version`` in *pyproject.toml* (the single source of truth).
  2. Rewrites every ``<span class="version">vX.Y.Z</span>`` badge in ``docs/*.html``.

``codewiki_mcp/__init__.py`` no longer contains a hard-coded version — it reads
from ``importlib.metadata`` at runtime, so no update is needed there.

The README badge is dynamic (shields.io → PyPI) and is updated automatically
once the new version is published.
"""

from __future__ import annotations

import datetime
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"
DOCS_DIR = ROOT / "docs"
SERVER_PY = ROOT / "codewiki_mcp" / "server.py"

# --- regex patterns --------------------------------------------------------
# pyproject.toml:  version = "1.0.4"
_PYPROJECT_RE = re.compile(r'^(version\s*=\s*")([^"]+)(")', re.MULTILINE)

# docs HTML:  <span class="version">v1.0.4</span>
_DOCS_BADGE_RE = re.compile(
    r'(<span\s+class="version">v)([^<]+)(</span>)',
)


def _update_pyproject(new_ver: str) -> str:
    """Update pyproject.toml and return the old version string."""
    text = PYPROJECT.read_text(encoding="utf-8")
    m = _PYPROJECT_RE.search(text)
    if not m:
        sys.exit("ERROR: could not find 'version = \"...\"' in pyproject.toml")

    old_ver = m.group(2)
    updated = _PYPROJECT_RE.sub(rf"\g<1>{new_ver}\3", text, count=1)
    PYPROJECT.write_text(updated, encoding="utf-8")
    return old_ver


# server.py banner:  "  CodeWiki MCP Server 2026 - by CloudMeru\n"
_BANNER_YEAR_RE = re.compile(
    r'(CodeWiki MCP Server )\d{4}( - by CloudMeru)',
)


def _update_banner_year(year: int) -> bool:
    """Update the copyright year in the ASCII banner in server.py."""
    text = SERVER_PY.read_text(encoding="utf-8")
    updated, n = _BANNER_YEAR_RE.subn(rf"\g<1>{year}\2", text)
    if n:
        SERVER_PY.write_text(updated, encoding="utf-8")
        return True
    return False


def _update_docs(new_ver: str) -> list[str]:
    """Rewrite <span class="version">vX.Y.Z</span> in every docs HTML file."""
    changed: list[str] = []
    for html in sorted(DOCS_DIR.glob("*.html")):
        text = html.read_text(encoding="utf-8")
        updated, n = _DOCS_BADGE_RE.subn(rf"\g<1>{new_ver}\3", text)
        if n:
            html.write_text(updated, encoding="utf-8")
            changed.append(html.name)
    return changed


def main(argv: list[str] | None = None) -> None:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 1:
        print(__doc__)
        sys.exit(1)

    new_ver = args[0].lstrip("v")  # accept "v1.1.0" or "1.1.0"

    # simple semver sanity check
    if not re.fullmatch(r"\d+\.\d+\.\d+([a-zA-Z0-9._-]+)?", new_ver):
        sys.exit(f"ERROR: '{new_ver}' does not look like a valid version")

    old_ver = _update_pyproject(new_ver)
    print(f"pyproject.toml  : {old_ver} -> {new_ver}")

    year = datetime.datetime.now().year
    if _update_banner_year(year):
        print(f"server.py banner: year -> {year}")
    else:
        print("server.py banner: no match found (skipped)")

    changed = _update_docs(new_ver)
    if changed:
        print(f"docs (v{new_ver}) : {', '.join(changed)}")
    else:
        print("docs            : no files matched")

    print("\nDone! Remember to:")
    print("  • Commit the changes")
    print("  • Tag the release:  git tag v" + new_ver)
    print("  • Publish to PyPI so the README badge updates automatically")


if __name__ == "__main__":
    main()
