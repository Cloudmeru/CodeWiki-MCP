"""Playwright-based wiki page fetcher and BeautifulSoup parser.

CodeWiki is a JavaScript SPA (Angular), so we must use Playwright to render
pages before parsing.  BeautifulSoup then extracts structured content from
the rendered HTML.
"""

from __future__ import annotations

import base64
import logging
import re
import warnings
from dataclasses import dataclass, field

from bs4 import BeautifulSoup, NavigableString, Tag

from . import config
from .browser import fetch_rendered_html
from .cache import get_cached_page, set_cached_page

logger = logging.getLogger("CodeWiki")


# ---------------------------------------------------------------------------
# Data classes for parsed content
# ---------------------------------------------------------------------------
@dataclass
class WikiSection:
    """A single section extracted from a CodeWiki page."""

    title: str
    level: int  # 1=h1, 2=h2, 3=h3, etc.
    content: str = ""
    children: list[WikiSection] = field(default_factory=list)


@dataclass
class WikiPage:
    """Parsed CodeWiki page with structured sections."""

    repo_name: str
    url: str
    title: str = ""
    sections: list[WikiSection] = field(default_factory=list)
    toc: list[dict[str, str]] = field(default_factory=list)  # [{title, level}]
    diagrams: list[dict] = field(default_factory=list)  # [{type, nodes, edges, content}]
    raw_text: str = ""


# ---------------------------------------------------------------------------
# Page fetcher with caching (Playwright-rendered)
# ---------------------------------------------------------------------------
def _fetch_html(url: str) -> str:
    """Fetch rendered HTML from *url*, with caching.

    Uses Playwright to render the JavaScript SPA, then caches
    the rendered output so subsequent calls are instant.
    """
    # Check cache first
    cached = get_cached_page(url)
    if cached is not None:
        return cached

    html = fetch_rendered_html(url)
    if html:
        set_cached_page(url, html)
    return html


# ---------------------------------------------------------------------------
# BeautifulSoup helpers
# ---------------------------------------------------------------------------
def _extract_text(tag: Tag) -> str:
    """Extract clean text from a BS4 tag, preserving code blocks."""
    parts: list[str] = []
    for child in tag.children:
        if isinstance(child, NavigableString):
            parts.append(str(child))
        elif isinstance(child, Tag):
            if child.name in ("pre", "code"):
                code_text = child.get_text()
                if child.name == "pre":
                    parts.append(f"\n```\n{code_text}\n```\n")
                else:
                    parts.append(f"`{code_text}`")
            elif child.name == "br":
                parts.append("\n")
            elif child.name in ("a",):
                href = child.get("href", "")
                text = child.get_text()
                if href and text:
                    parts.append(f"[{text}]({href})")
                else:
                    parts.append(text)
            elif child.name in ("strong", "b"):
                parts.append(f"**{child.get_text()}**")
            elif child.name in ("em", "i"):
                parts.append(f"*{child.get_text()}*")
            elif child.name in ("ul", "ol"):
                for li in child.find_all("li", recursive=False):
                    parts.append(f"\n- {li.get_text().strip()}")
                parts.append("\n")
            elif child.name in ("p", "div"):
                parts.append(f"\n{_extract_text(child)}\n")
            else:
                parts.append(child.get_text())
    return "".join(parts).strip()


def _tag_to_markdown(tag: Tag) -> str:
    """Convert a tag's content to simplified markdown."""
    return _extract_text(tag)


# ---------------------------------------------------------------------------
# Main parser
# ---------------------------------------------------------------------------
def _parse_sections(soup: BeautifulSoup) -> list[WikiSection]:
    """Extract sections from the wiki page.

    Handles two layouts:
    1. CodeWiki SPA — ``<body-content-section>`` custom elements with
       ``<documentation-markdown>`` children.
    2. Standard HTML — heading tags (h1-h6) as structural delimiters.
    """
    # --- Strategy 1: CodeWiki Angular SPA custom elements ----------------
    bcs_elements = soup.find_all("body-content-section")
    if bcs_elements:
        return _parse_codewiki_sections(bcs_elements)

    # --- Strategy 2: Standard HTML headings (fallback) -------------------
    return _parse_heading_sections(soup)


def _parse_codewiki_sections(bcs_elements: list[Tag]) -> list[WikiSection]:
    """Parse ``<body-content-section>`` elements from CodeWiki's SPA."""
    sections: list[WikiSection] = []
    for elem in bcs_elements:
        heading = elem.find(re.compile(r"h[1-6]"))
        if heading:
            level = int(heading.name[1])
            title = heading.get_text(strip=True)
        else:
            level = 2
            title = "Overview"

        # Gather markdown content, excluding the heading text itself
        md_parts: list[str] = []
        for md_elem in elem.find_all("documentation-markdown"):
            text = _extract_text(md_elem)
            if text:
                # Strip leading title duplication
                if title and text.startswith(title):
                    text = text[len(title):].strip()
                md_parts.append(text)

        # Fallback: extract text from the whole section
        if not md_parts:
            text = _extract_text(elem)
            if title and text.startswith(title):
                text = text[len(title):].strip()
            if text:
                md_parts.append(text)

        content = "\n\n".join(md_parts).strip()
        sections.append(WikiSection(title=title, level=level, content=content))

    return sections


def _parse_heading_sections(soup: BeautifulSoup) -> list[WikiSection]:
    """Parse sections from standard HTML using heading tags as delimiters."""
    sections: list[WikiSection] = []
    current_section: WikiSection | None = None
    content_parts: list[str] = []

    # Find the main content area
    main = soup.find("main") or soup.find("article") or soup.body
    if main is None:
        return sections

    # Search all headings recursively (not just direct children)
    all_headings = main.find_all(re.compile(r"h[1-6]"))
    if not all_headings:
        return sections

    for heading in all_headings:
        # Save previous section
        if current_section is not None:
            current_section.content = "\n".join(content_parts).strip()
            sections.append(current_section)
            content_parts = []

        level = int(heading.name[1])
        title = heading.get_text(strip=True)
        current_section = WikiSection(title=title, level=level)

        # Collect sibling content after this heading
        for sibling in heading.find_next_siblings():
            if isinstance(sibling, Tag):
                if re.match(r"h[1-6]", sibling.name or ""):
                    break  # Next heading — stop
                text = _tag_to_markdown(sibling)
                if text:
                    content_parts.append(text)

    # Don't forget last section
    if current_section is not None:
        current_section.content = "\n".join(content_parts).strip()
        sections.append(current_section)

    return sections


def _extract_toc(soup: BeautifulSoup) -> list[dict[str, str]]:
    """Extract the table of contents / navigation structure."""
    toc: list[dict[str, str]] = []

    # Strategy 1: Look for "On this page" nav or similar TOC elements
    for nav in soup.find_all(["nav", "div"], class_=re.compile(r"toc|table.of.contents|sidebar|nav", re.I)):
        for link in nav.find_all("a"):
            text = link.get_text(strip=True)
            if text and len(text) > 1:
                toc.append({"title": text, "href": link.get("href", "")})

    # Strategy 2: Extract from heading tags anywhere in the page
    if not toc:
        for heading in soup.find_all(re.compile(r"h[1-6]")):
            text = heading.get_text(strip=True)
            if text:
                level = heading.name[1]  # '2' from 'h2'
                toc.append({"title": text, "level": level})

    return toc

    return toc


def _extract_diagrams(soup: BeautifulSoup) -> list[dict]:
    """Extract diagrams from the rendered HTML.

    Handles three diagram sources:

    1. **CodeWiki SPA diagrams** — ``<code-documentation-diagram-inline>``
       elements containing ``<svg class="svg-diagram">`` with embedded
       base64 SVG ``<image>`` data URIs.  Graphviz node/edge groups are
       parsed to extract structured graph data (entities and relationships).
    2. **Mermaid code blocks / divs** — standard ``<pre><code class="mermaid">``
       or ``<div class="mermaid">``.
    3. **Fallback** — bare ``<svg>`` elements with ``<title>`` children, and
       ``<img>`` tags whose ``alt`` text mentions diagrams.
    """
    diagrams: list[dict] = []
    _seen_hrefs: set[str] = set()  # deduplicate identical embedded SVGs

    # ----- Strategy 1: CodeWiki SPA custom diagram elements -----------------
    for inline in soup.find_all("code-documentation-diagram-inline"):
        info: dict = {"type": "svg-diagram"}

        # Determine which section this diagram belongs to
        parent_section = inline.find_parent("body-content-section")
        if parent_section:
            heading = parent_section.find(["h1", "h2", "h3", "h4", "h5", "h6"])
            if heading:
                info["section"] = heading.get_text(strip=True)

        # Look for the base64-encoded SVG inside <image class="image-diagram">
        image_el = inline.find("image", class_="image-diagram")
        href = (image_el.get("href") or image_el.get("xlink:href") or "") if image_el else ""

        if href and href not in _seen_hrefs:
            _seen_hrefs.add(href)
            graph = _extract_svg_graph(href)
            if graph:
                info.update(graph)
            diagrams.append(info)
        elif not href:
            # SVG without data URI — still record it
            diagrams.append(info)

    # ----- Strategy 2: Mermaid code blocks ----------------------------------
    for pre in soup.find_all("pre"):
        code = pre.find("code")
        if code:
            classes = code.get("class", [])
            class_str = " ".join(classes) if isinstance(classes, list) else str(classes)
            if "mermaid" in class_str.lower():
                diagrams.append({
                    "type": "mermaid",
                    "content": code.get_text(strip=True),
                })

    for div in soup.find_all("div", class_=re.compile(r"mermaid", re.I)):
        text = div.get_text(strip=True)
        if text:
            diagrams.append({"type": "mermaid", "content": text})

    # ----- Strategy 3: Fallback — bare SVGs and diagram images --------------
    # Only pick up SVGs that were NOT already captured by Strategy 1
    for svg in soup.find_all("svg"):
        if svg.find_parent("code-documentation-diagram-inline"):
            continue  # already handled
        title_elem = svg.find("title")
        if title_elem:
            diagrams.append({
                "type": "svg",
                "title": title_elem.get_text(strip=True),
            })

    for img in soup.find_all("img", alt=re.compile(r"diagram|architecture|flow|image", re.I)):
        diagrams.append({
            "type": "image",
            "alt": img.get("alt", ""),
            "src": img.get("src", ""),
        })

    return diagrams


def _extract_svg_graph(href: str) -> dict | None:
    """Decode a ``data:image/svg+xml;base64,...`` URI and extract graph data.

    Parses Graphviz-generated SVGs for structured ``<g class="node">`` and
    ``<g class="edge">`` groups.  Returns a dict with:

    - ``nodes``: list of ``{"id": ..., "label": ...}``
    - ``edges``: list of ``{"from": ..., "to": ..., "label": ...}``
    - ``content``: flat text summary (for backward compatibility)

    Falls back to flat ``<text>`` extraction when no Graphviz groups exist.
    """
    if not href.startswith("data:image/svg+xml;base64,"):
        return None
    try:
        b64 = href.split(",", 1)[1]
        svg_xml = base64.b64decode(b64).decode("utf-8", errors="replace")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            inner = BeautifulSoup(svg_xml, "xml")

        node_groups = inner.find_all("g", class_="node")
        edge_groups = inner.find_all("g", class_="edge")

        if node_groups or edge_groups:
            # Graphviz structured SVG
            nodes = []
            for g in node_groups:
                title_el = g.find("title")
                node_id = title_el.get_text(strip=True) if title_el else ""
                texts = [t.get_text(strip=True) for t in g.find_all("text") if t.get_text(strip=True)]
                label = " ".join(texts)
                if node_id or label:
                    nodes.append({"id": node_id, "label": label})

            edges = []
            for g in edge_groups:
                title_el = g.find("title")
                edge_id = title_el.get_text(strip=True) if title_el else ""
                texts = [t.get_text(strip=True) for t in g.find_all("text") if t.get_text(strip=True)]
                edge_label = " ".join(texts)

                # Parse "A->B" from the <title>
                src, dst = "", ""
                if "->" in edge_id:
                    parts = edge_id.split("->", 1)
                    src, dst = parts[0].strip(), parts[1].strip()

                edge_entry: dict[str, str] = {}
                if src:
                    edge_entry["from"] = src
                if dst:
                    edge_entry["to"] = dst
                if edge_label:
                    edge_entry["label"] = edge_label
                if edge_entry:
                    edges.append(edge_entry)

            # Build flat content summary for backward compat
            node_labels = [n["label"] for n in nodes if n.get("label")]
            edge_descs = []
            for e in edges:
                desc = f"{e.get('from', '?')} -> {e.get('to', '?')}"
                if e.get("label"):
                    desc += f" [{e['label']}]"
                edge_descs.append(desc)

            content = ", ".join(node_labels)
            return {
                "nodes": nodes,
                "edges": edges,
                "content": content,
            }
        else:
            # No Graphviz groups — fall back to flat text extraction
            texts = [t.get_text(strip=True) for t in inner.find_all("text") if t.get_text(strip=True)]
            if texts:
                return {"content": ", ".join(texts)}
            return None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def fetch_wiki_page(repo_url: str) -> WikiPage:
    """Fetch and parse a CodeWiki page for *repo_url*.

    Args:
        repo_url: Full GitHub URL (e.g. https://github.com/owner/repo).

    Returns:
        WikiPage with structured sections, TOC, and diagrams.

    Raises:
        Exception: If the page cannot be fetched or rendered.
    """
    clean_repo = repo_url.replace("https://", "").replace("http://", "")
    target_url = f"{config.CODEWIKI_BASE_URL}/{clean_repo}"

    html = _fetch_html(target_url)
    soup = BeautifulSoup(html, "lxml")

    # Extract repo name from heading or URL
    title_tag = soup.find("h1") or soup.find("h2")
    title = title_tag.get_text(strip=True) if title_tag else clean_repo
    # Clean up SPA UI artifacts in title (e.g. "sparkPowered by Gemini")
    title = re.sub(r"spark\s*Powered by Gemini\s*$", "", title).strip()

    sections = _parse_sections(soup)
    toc = _extract_toc(soup)
    diagrams = _extract_diagrams(soup)

    # Build raw text from body
    body = soup.find("body")
    raw_text = body.get_text(separator="\n", strip=True) if body else ""

    # Clean up UI artifacts
    for artifact in config.UI_ARTIFACTS:
        raw_text = raw_text.replace(artifact, "")

    page = WikiPage(
        repo_name=clean_repo,
        url=target_url,
        title=title,
        sections=sections,
        toc=toc,
        diagrams=diagrams,
        raw_text=raw_text,
    )

    logger.info(
        "Parsed %s: %d sections, %d TOC items, %d diagrams, %d chars",
        clean_repo, len(sections), len(toc), len(diagrams), len(raw_text),
    )
    return page


def get_section_by_title(page: WikiPage, section_title: str) -> WikiSection | None:
    """Find a section by (case-insensitive partial) title match."""
    needle = section_title.lower().strip()
    for section in page.sections:
        if needle in section.title.lower():
            return section
    return None


def page_to_markdown(page: WikiPage, *, max_chars: int = 0) -> str:
    """Convert a WikiPage to a markdown-formatted string."""
    parts = [f"# {page.title}\n"]

    # Place diagram summary early so it's visible even when truncated
    if page.diagrams:
        lines = [f"\n**Diagrams ({len(page.diagrams)}):**\n"]
        for i, d in enumerate(page.diagrams):
            section = d.get("section", "")
            title = d.get("title", "")
            label = section or title or f"Diagram {i}"
            lines.append(f"**{i}. {label}**")

            nodes = d.get("nodes", [])
            edges = d.get("edges", [])

            if nodes or edges:
                # Structured graph — show entities and relationships
                if nodes:
                    node_labels = [n.get("label", n.get("id", "?")) for n in nodes]
                    lines.append(f"  Entities: {', '.join(node_labels)}")
                if edges:
                    rel_parts = []
                    for e in edges:
                        rel = f"{e.get('from', '?')} -> {e.get('to', '?')}"
                        if e.get("label"):
                            rel += f" [{e['label']}]"
                        rel_parts.append(rel)
                    lines.append("  Relationships:")
                    for rel in rel_parts:
                        lines.append(f"    - {rel}")
            else:
                # Flat content fallback
                content = d.get("content", "")
                if content:
                    preview = content[:200] + ("..." if len(content) > 200 else "")
                    lines.append(f"  Labels: {preview}")
            lines.append("")  # blank line between diagrams

        parts.append("\n".join(lines))

    for section in page.sections:
        prefix = "#" * min(section.level + 1, 6)
        parts.append(f"\n{prefix} {section.title}\n")
        if section.content:
            parts.append(section.content)

    text = "\n".join(parts).strip()

    if max_chars and len(text) > max_chars:
        text = text[:max_chars] + "\n\n... [truncated]"

    return text
