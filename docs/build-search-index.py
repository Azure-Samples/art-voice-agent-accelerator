#!/usr/bin/env python3
"""
Build a static client-side search index from the docs/ HTML pages.

Walks every *.html file in docs/, splits content into sections by
<h2>/<h3> headings (id-anchored), strips markup, and writes
docs/search-index.json — consumed at runtime by js/search.js.

Dependency-free (stdlib only). Run:

    python docs/build-search-index.py

or:

    make docs-search-index
"""

from __future__ import annotations

import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

DOCS_DIR = Path(__file__).resolve().parent
OUTPUT = DOCS_DIR / "search-index.json"

# Tags whose contents we do NOT want in the index (chrome / scripts / diagrams)
SKIP_TAGS = {"head", "script", "style", "header", "aside", "nav", "svg"}
# Block-level tags whose text we treat as a hard break (insert space)
BLOCK_TAGS = {
    "p", "li", "tr", "td", "th", "pre", "div", "section", "article",
    "summary", "figcaption", "blockquote", "h1", "h2", "h3", "h4", "h5", "h6",
    "br",
}


class SectionExtractor(HTMLParser):
    """
    Streams an HTML file and emits a flat list of sections.

    A section is anchored on an <h2 id="..."> or <h3 id="..."> heading and
    contains all body text up to the next heading of the same level or higher.
    The page intro (before any <h2>) is captured as the h1 section.
    """

    def __init__(self, page_title: str, page_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.page_title = page_title
        self.page_url = page_url

        self.sections: list[dict] = []
        self._skip_depth = 0           # > 0 while inside SKIP_TAGS
        self._current_heading = None   # ('h2'|'h3', id, title_text) or None
        self._current_text: list[str] = []
        self._heading_collect: list[str] | None = None
        self._inline_heading: bool = False  # True when current heading lacks an id
        self._h1_title: str | None = None
        self._h1_id: str | None = None

        # Seed an implicit "intro" section keyed off h1 (filled when we see h1)
        self._intro_text: list[str] = []
        self._mode = "intro"           # 'intro' until first h2/h3

    # --- HTMLParser hooks -------------------------------------------------

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in SKIP_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return

        attrs_d = {k: (v or "") for k, v in attrs}

        if tag == "h1":
            self._h1_id = attrs_d.get("id") or "top"
            self._heading_collect = []
            return

        if tag in ("h2", "h3"):
            anchor = attrs_d.get("id")
            if not anchor:
                # Anchorless heading — not navigable on its own. Keep the
                # current section open and fold the heading text into the body
                # so it remains searchable but does not create an orphan entry.
                self._heading_collect = []
                self._inline_heading = True
                return
            # Close previous section, open a new one anchored on the heading id
            self._flush_current()
            self._current_heading = (tag, anchor, "")
            self._heading_collect = []
            self._inline_heading = False
            self._mode = "section"
            return

        if tag in BLOCK_TAGS:
            self._append_text(" ")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if self._skip_depth:
            return

        if tag == "h1":
            if self._heading_collect is not None:
                self._h1_title = " ".join(self._heading_collect).strip() or self.page_title
            self._heading_collect = None
            return

        if tag in ("h2", "h3"):
            if self._heading_collect is not None:
                heading_text = " ".join(self._heading_collect).strip()
                if getattr(self, "_inline_heading", False):
                    # Fold anchorless heading text into the body of the active section
                    if heading_text:
                        self._append_text(" " + heading_text + " ")
                    self._inline_heading = False
                elif self._current_heading:
                    lvl, aid, _ = self._current_heading
                    self._current_heading = (lvl, aid, heading_text)
            self._heading_collect = None
            return

        if tag in BLOCK_TAGS:
            self._append_text(" ")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        # Capture heading text separately so it doesn't pollute body text
        if self._heading_collect is not None:
            self._heading_collect.append(data)
            return
        self._append_text(data)

    # --- internals --------------------------------------------------------

    def _append_text(self, chunk: str) -> None:
        if self._mode == "intro":
            self._intro_text.append(chunk)
        else:
            self._current_text.append(chunk)

    def _flush_current(self) -> None:
        if not self._current_heading:
            return
        lvl, aid, title = self._current_heading
        if not title:
            self._current_heading = None
            self._current_text = []
            return
        body = _clean(" ".join(self._current_text))
        if body or title:
            self.sections.append(
                {
                    "url": f"{self.page_url}#{aid}",
                    "anchor": aid,
                    "level": int(lvl[1]),  # 2 or 3
                    "page": self.page_title,
                    "title": title,
                    "text": body,
                }
            )
        self._current_heading = None
        self._current_text = []

    def finalize(self) -> list[dict]:
        # Flush trailing section
        self._flush_current()

        # Prepend the h1 / intro section (text before the first h2)
        intro = _clean(" ".join(self._intro_text))
        h1_title = self._h1_title or self.page_title
        anchor = self._h1_id or "top"
        intro_section = {
            "url": f"{self.page_url}#{anchor}",
            "anchor": anchor,
            "level": 1,
            "page": self.page_title,
            "title": h1_title,
            "text": intro,
        }
        return [intro_section] + self.sections


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_WS_RE = re.compile(r"\s+")


def _clean(text: str) -> str:
    """Collapse whitespace and trim."""
    return _WS_RE.sub(" ", text).strip()


def _extract_title(html: str, fallback: str) -> str:
    """Pull the <title> tag, stripping the ' — ART Agent Docs' suffix."""
    m = re.search(r"<title>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
    if not m:
        return fallback
    title = _clean(m.group(1))
    for sep in (" — ", " - ", " | "):
        if sep in title:
            title = title.split(sep, 1)[0].strip()
            break
    return title or fallback


def build_index(docs_dir: Path = DOCS_DIR) -> dict:
    pages = sorted(p for p in docs_dir.glob("*.html"))
    if not pages:
        raise SystemExit(f"No HTML files found in {docs_dir}")

    all_sections: list[dict] = []
    page_meta: list[dict] = []

    for path in pages:
        rel = path.name
        html = path.read_text(encoding="utf-8")
        title = _extract_title(html, fallback=rel)

        parser = SectionExtractor(page_title=title, page_url=rel)
        parser.feed(html)
        sections = parser.finalize()

        all_sections.extend(sections)
        page_meta.append({"url": rel, "title": title, "sections": len(sections)})

    # Drop sections that ended up totally empty (no title, no body)
    all_sections = [s for s in all_sections if s["title"] or s["text"]]

    return {
        "generated_by": "docs/build-search-index.py",
        "version": 1,
        "pages": page_meta,
        "sections": all_sections,
    }


def main() -> int:
    index = build_index()
    OUTPUT.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    total_sections = len(index["sections"])
    total_chars = sum(len(s["text"]) for s in index["sections"])
    print(
        f"Wrote {OUTPUT.relative_to(DOCS_DIR.parent)} — "
        f"{len(index['pages'])} pages, {total_sections} sections, "
        f"{total_chars:,} body chars"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
