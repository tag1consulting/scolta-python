"""Lightweight markdown-to-HTML renderer for AI responses.

Direct port of ``Tag1\\Scolta\\Util\\MarkdownRenderer``. Handles bold,
italic, links, bullet lists and paragraphs. All output is HTML-escaped for
XSS safety — text is escaped first, then safe structural tags are applied via
regex. A general markdown library is intentionally NOT used: the ported tests
assert this exact output (subset of tags, broken-link salvage, escaping order).
"""

from __future__ import annotations

import re

_BOLD_ITALIC = re.compile(r"\*\*\*(.+?)\*\*\*")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_ITALIC = re.compile(r"\*(.+?)\*")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_TRUNCATED_LINK = re.compile(r"\[([^\]]+)\]\([^)]*$")
_ORPHAN_BRACKET = re.compile(r"\[([^\]]+)\](?!\()")


def _escape(text: str) -> str:
    """Equivalent of PHP htmlspecialchars(..., ENT_QUOTES, 'UTF-8')."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#039;")
    )


def _clean_broken_links(text: str) -> str:
    # [text]( with no closing ) — truncated URL, keep the label as bold.
    text = _TRUNCATED_LINK.sub(r"**\1**", text)
    # [text] with no following (url) — orphaned bracket, keep label as bold.
    text = _ORPHAN_BRACKET.sub(r"**\1**", text)
    return text


def _render_inline(text: str) -> str:
    text = _clean_broken_links(text)
    text = _escape(text)
    text = _BOLD_ITALIC.sub(r"<strong><em>\1</em></strong>", text)
    text = _BOLD.sub(r"<strong>\1</strong>", text)
    text = _ITALIC.sub(r"<em>\1</em>", text)
    text = _LINK.sub(r'<a href="\2" target="_blank" rel="noopener">\1</a>', text)
    return text


def render(markdown: str) -> str:
    """Render markdown text to sanitized HTML."""
    if markdown == "":
        return ""

    html = ""
    in_list = False

    for line in markdown.split("\n"):
        trimmed = line.strip()

        if trimmed == "":
            if in_list:
                html += "</ul>"
                in_list = False
            continue

        if trimmed.startswith("- "):
            if not in_list:
                html += "<ul>"
                in_list = True
            html += "<li>" + _render_inline(trimmed[2:]) + "</li>"
        else:
            if in_list:
                html += "</ul>"
                in_list = False
            html += "<p>" + _render_inline(trimmed) + "</p>"

    if in_list:
        html += "</ul>"

    return html
