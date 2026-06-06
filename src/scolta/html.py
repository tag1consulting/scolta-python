"""HTML cleaning and Pagefind-document building.

Faithful port of ``Tag1\\Scolta\\Html\\HtmlCleaner`` and
``PagefindHtmlBuilder``. Both are intentionally regex/string-based (the PHP is
itself ported from the Rust ``html.rs``), NOT DOM-parser based — a real HTML
parser (lxml/selectolax) would diverge on the malformed-input and
comment/attribute edge cases the parity gate checks. So this reproduces PHP's
``strip_tags`` / ``html_entity_decode`` / non-``/u`` ``\\s`` semantics exactly.
"""

from __future__ import annotations

import html as _htmllib
import re

# Whitespace set matching PCRE2 \s without the /u modifier: HT LF FF CR SP VT.
# Notably this does NOT include U+00A0 (&nbsp;), so decoded nbsp survives, as
# in the PHP cleaner.
_ASCII_WS = "\t\n\f\r \x0b"
_PHP_TRIM = " \t\n\r\x00\x0b"  # PHP trim()/ltrim() default character mask.

_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_FOOTER_TAG = re.compile(r"<footer\b[^>]*>.*?</footer\s*>", re.DOTALL | re.IGNORECASE)
_FOOTER_ID = re.compile(
    r"""<[^>]*\sid\s*=\s*["'][^"']*footer[^"']*["'][^>]*>.*?</[^>]*>""",
    re.DOTALL | re.IGNORECASE,
)
_FOOTER_CLASS = re.compile(
    r"""<[^>]*\sclass\s*=\s*["'][^"']*footer[^"']*["'][^>]*>.*?</[^>]*>""",
    re.DOTALL | re.IGNORECASE,
)
_FOOTER_REGION = re.compile(
    r"""<[^>]*\sclass\s*=\s*["'][^"']*region-footer[^"']*["'][^>]*>.*?</[^>]*>""",
    re.DOTALL | re.IGNORECASE,
)
_SCRIPT = re.compile(r"<script\b[^>]*>.*?</script\s*>", re.DOTALL | re.IGNORECASE)
_STYLE = re.compile(r"<style\b[^>]*>.*?</style\s*>", re.DOTALL | re.IGNORECASE)
_NAV = re.compile(r"<nav\b[^>]*>.*?</nav\s*>", re.DOTALL | re.IGNORECASE)
_WS = re.compile(r"[\t\n\f\r \x0b]+")
_MAIN = re.compile(
    r"""<(div|main|article|section)\b[^>]*\sid\s*=\s*["']main-content["'][^>]*>""",
    re.IGNORECASE,
)

_TAG_TRIGGER_STOP = set(_ASCII_WS)  # '<' + whitespace is literal, not a tag.
_CLOSE_OK_AFTER_OPEN = {" ", ">", "/", "\t", "\n"}


def clean(html: str, title: str = "") -> str:
    """Clean raw HTML into plain text suitable for search indexing."""
    content = _COMMENT.sub("", html)
    content = _extract_main_content(content)
    content = _FOOTER_TAG.sub("", content)
    content = _FOOTER_ID.sub("", content)
    content = _FOOTER_CLASS.sub("", content)
    content = _FOOTER_REGION.sub("", content)
    content = _SCRIPT.sub("", content)
    content = _STYLE.sub("", content)
    content = _NAV.sub("", content)
    content = _strip_tags(content)
    content = _htmllib.unescape(content)
    content = _WS.sub(" ", content).strip(_PHP_TRIM)

    if title != "":
        pos = content.find(title)
        if pos != -1 and pos < 50:
            content = content[pos + len(title):].lstrip(_PHP_TRIM)

    return content


def _strip_tags(s: str) -> str:
    """Replicate PHP strip_tags for the (comment/script/style-free) inputs the
    cleaner produces: ``<`` starts a tag unless it is followed by whitespace or
    end-of-string; a tag with no closing ``>`` swallows to end of string."""
    out: list[str] = []
    i = 0
    n = len(s)
    in_tag = False
    while i < n:
        c = s[i]
        if in_tag:
            if c == ">":
                in_tag = False
            i += 1
            continue
        if c == "<":
            nxt = s[i + 1] if i + 1 < n else ""
            if nxt != "" and nxt not in _TAG_TRIGGER_STOP:
                in_tag = True
                i += 1
                continue
            out.append(c)
            i += 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


def strip_tags(s: str) -> str:
    """Public alias for PHP strip_tags semantics (used by the index builder)."""
    return _strip_tags(s)


def decode_entities(s: str) -> str:
    """PHP html_entity_decode(ENT_QUOTES | ENT_HTML5) equivalent."""
    return _htmllib.unescape(s)


def _extract_main_content(html: str) -> str:
    """Extract id="main-content", falling back to <body>, then full input."""
    m = _MAIN.search(html)
    if m:
        tag_name = m.group(1)
        tag_end = m.end()
        close_pos = _find_matching_close(html, tag_end, tag_name)
        if close_pos is not None:
            return html[tag_end:close_pos]

    lower = html.lower()
    body_start = lower.find("<body")
    if body_start != -1:
        body_tag_end = html.find(">", body_start)
        if body_tag_end != -1:
            body_tag_end += 1
            body_close = lower.find("</body>", body_tag_end)
            if body_close != -1:
                return html[body_tag_end:body_close]

    return html


def _find_matching_close(html: str, start_pos: int, tag_name: str) -> int | None:
    """Find the matching closing tag, handling nesting (port of the PHP scan)."""
    search = html[start_pos:]
    search_low = search.lower()
    open_pat = ("<" + tag_name).lower()
    close_pat = ("</" + tag_name).lower()
    depth = 1
    pos = 0
    length = len(search)

    while pos < length:
        rem_low = search_low[pos:]
        next_open = rem_low.find(open_pat)
        next_close = rem_low.find(close_pat)

        if next_open != -1:
            after_idx = pos + next_open + len(open_pat)
            after = search[after_idx] if after_idx < length else None
            if after not in _CLOSE_OK_AFTER_OPEN:
                next_open = -1

        if next_open != -1 and next_close != -1 and next_open < next_close:
            depth += 1
            pos += next_open + len(open_pat)
        elif next_close != -1:
            depth -= 1
            if depth == 0:
                return start_pos + pos + next_close
            pos += next_close + len(close_pat)
        elif next_open != -1:
            depth += 1
            pos += next_open + len(open_pat)
        else:
            break

    return None


# -- Pagefind HTML builder ----------------------------------------------------


def _hs(s: str) -> str:
    """Equivalent of PHP htmlspecialchars(s, ENT_QUOTES | ENT_HTML5, 'UTF-8').

    Note ENT_HTML5 encodes the single quote as &apos; (not &#039;)."""
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def build(
    id: str,
    title: str,
    body: str,
    url: str,
    date: str = "",
    site_name: str = "",
    language: str = "en",
    filters: dict | None = None,
    metadata: dict | None = None,
    sortable: dict | None = None,
) -> str:
    """Build a Pagefind-compatible HTML document (port of PagefindHtmlBuilder)."""
    filters = filters or {}
    metadata = metadata or {}
    sortable = sortable or {}

    escaped_title = _hs(title)
    escaped_body = _hs(body)
    escaped_url = _hs(url)
    escaped_lang = _hs(language)

    site_filter = ""
    if site_name != "":
        site_filter = f' data-pagefind-filter="site:{_hs(site_name)}"'

    date_meta = ""
    if date != "":
        date_meta = f'<p data-pagefind-meta="date:{_hs(date)}" hidden></p>\n'

    lang_filter = f'<span data-pagefind-filter="language:{escaped_lang}" hidden></span>\n'

    extra_filters = ""
    for key, value in filters.items():
        ekey = _hs(str(key))
        values = value if isinstance(value, list) else [value]
        for v in values:
            extra_filters += f'<span data-pagefind-filter="{ekey}:{_hs(str(v))}" hidden></span>\n'

    extra_meta = ""
    for key, value in metadata.items():
        extra_meta += f'<p data-pagefind-meta="{_hs(str(key))}:{_hs(str(value))}" hidden></p>\n'

    sort_attrs = ""
    for key, value in sortable.items():
        sort_attrs += f'<p data-pagefind-sort="{_hs(str(key))}:{_hs(str(value))}" hidden></p>\n'
    if date != "" and "date" not in sortable:
        sort_attrs += f'<p data-pagefind-sort="date:{_hs(date)}" hidden></p>\n'

    return (
        "<!DOCTYPE html>\n"
        f'<html lang="{escaped_lang}">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        f"<title>{escaped_title}</title>\n"
        "</head>\n"
        f'<body data-pagefind-body id="{id}"{site_filter}>\n'
        f"<h1>{escaped_title}</h1>\n"
        f'<p data-pagefind-meta="url:{escaped_url}" hidden></p>\n'
        f"{date_meta}{lang_filter}{extra_filters}{extra_meta}{sort_attrs}{escaped_body}\n"
        "</body>\n"
        "</html>"
    )
