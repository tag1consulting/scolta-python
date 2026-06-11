"""Ported from tests/Html/HtmlCleanerTest.php and PagefindHtmlBuilderTest.php (1:1)."""

from scolta.html import build, clean

# -- HtmlCleaner --------------------------------------------------------------


def test_clean_basic_html():
    assert clean("<p>Hello <strong>world</strong></p>") == "Hello world"


def test_removes_script():
    r = clean('<p>Content</p><script>alert("xss")</script><p>More</p>')
    assert "Content" in r
    assert "More" in r
    assert "alert" not in r
    assert "script" not in r


def test_removes_multiline_script():
    html = '<p>Before</p>\n<script type="text/javascript">\n  var x = 1;\n  console.log(x);\n</script>\n<p>After</p>'
    r = clean(html)
    assert "Before" in r
    assert "After" in r
    assert "console" not in r
    assert "var x" not in r


def test_removes_multiline_style():
    html = "<p>Before</p>\n<style>\n  body { color: red; }\n  h1 { font-size: 2em; }\n</style>\n<p>After</p>"
    r = clean(html)
    assert "Before" in r
    assert "After" in r
    assert "color" not in r
    assert "font-size" not in r


def test_removes_html_comments():
    r = clean("<p>Visible</p><!-- This is a comment --><p>Also visible</p>")
    assert "Visible" in r
    assert "Also visible" in r
    assert "comment" not in r
    assert "<!--" not in r


def test_extract_main_content():
    html = (
        "<nav>Navigation</nav>"
        '<div id="main-content"><p>Important content here</p></div>'
        "<footer>Footer stuff</footer>"
    )
    r = clean(html)
    assert "Important content" in r
    assert "Navigation" not in r
    assert "Footer stuff" not in r


def test_main_content_case_insensitive():
    html = (
        '<div>Outside</div><DIV ID="main-content"><p>Inside main</p></DIV><div>Also outside</div>'
    )
    r = clean(html)
    assert "Inside main" in r
    assert "Outside" not in r


def test_removes_footer_by_class():
    r = clean('<p>Content</p><div class="site-footer"><p>Footer content</p></div>')
    assert "Content" in r
    assert "Footer content" not in r


def test_removes_footer_by_id():
    r = clean('<p>Content</p><div id="page-footer"><p>Footer content</p></div>')
    assert "Content" in r
    assert "Footer content" not in r


def test_handles_malformed_html():
    r = clean("<p>Unclosed paragraph<div>Mixed <b>nesting</div></b>")
    assert isinstance(r, str)
    assert "Unclosed paragraph" in r


def test_empty_input():
    assert clean("") == ""


def test_removes_nav():
    html = "<nav><ul><li>Home</li><li>About</li></ul></nav><main><p>Page content here</p></main>"
    r = clean(html)
    assert "Page content" in r
    assert "Home" not in r
    assert "About" not in r


# -- PagefindHtmlBuilder ------------------------------------------------------


def test_build_basic():
    html = build(
        id="doc-1",
        title="Test Title",
        body="Body text here",
        url="https://example.com/page",
        date="2024-06-15",
        site_name="My Site",
    )
    assert "data-pagefind-body" in html
    assert 'id="doc-1"' in html
    assert "<title>Test Title</title>" in html
    assert "<h1>Test Title</h1>" in html
    assert 'data-pagefind-filter="site:My Site"' in html
    assert 'data-pagefind-meta="date:2024-06-15"' in html
    assert 'data-pagefind-meta="url:https://example.com/page"' in html
    assert "Body text here" in html


def test_escapes_content():
    html = build(
        id="doc-2",
        title="Tom & Jerry's <Adventure>",
        body='Content with "quotes" & <tags>',
        url="https://example.com/page?a=1&b=2",
        date="2024-01-01",
        site_name='Site "One"',
    )
    assert "Tom &amp; Jerry&apos;s &lt;Adventure&gt;" in html
    assert "Content with &quot;quotes&quot; &amp; &lt;tags&gt;" in html
    assert "url:https://example.com/page?a=1&amp;b=2" in html
    assert "site:Site &quot;One&quot;" in html


def test_omits_empty_site():
    html = build(
        id="doc-3",
        title="No Site",
        body="Body content",
        url="https://example.com",
        date="2024-01-01",
        site_name="",
    )
    assert 'data-pagefind-filter="site:' not in html
    assert 'data-pagefind-filter="language:en"' in html
    assert "data-pagefind-body" in html


def test_default_language_is_english():
    html = build(id="doc-4", title="English", body="Body", url="https://example.com")
    assert '<html lang="en">' in html
    assert 'data-pagefind-filter="language:en"' in html


def test_language_attribute():
    html = build(
        id="doc-5",
        title="Español",
        body="Contenido en español",
        url="https://example.com/es",
        date="2024-06-15",
        site_name="Mi Sitio",
        language="es",
    )
    assert '<html lang="es">' in html
    assert 'data-pagefind-filter="language:es"' in html


def test_language_value_is_escaped():
    html = build(
        id="doc-6", title="Test", body="Body", url="https://example.com", language="zh-Hant"
    )
    assert '<html lang="zh-Hant">' in html
    assert 'data-pagefind-filter="language:zh-Hant"' in html


def test_extra_filters_emitted():
    html = build(
        id="doc-7",
        title="Test",
        body="Body",
        url="https://example.com",
        filters={"base_topic": "Cardiology", "region": "Europe"},
    )
    assert 'data-pagefind-filter="base_topic:Cardiology"' in html
    assert 'data-pagefind-filter="region:Europe"' in html


def test_extra_filter_values_are_escaped():
    html = build(
        id="doc-8",
        title="Test",
        body="Body",
        url="https://example.com",
        filters={"category": "Rock & Roll <genre>"},
    )
    assert 'data-pagefind-filter="category:Rock &amp; Roll &lt;genre&gt;"' in html
    assert "Rock & Roll" not in html


def test_multi_value_filter_emits_one_span_per_value():
    html = build(
        id="doc-m",
        title="Test",
        body="Body",
        url="https://example.com",
        filters={"topics": ["Science", "History"]},
    )
    assert 'data-pagefind-filter="topics:Science"' in html
    assert 'data-pagefind-filter="topics:History"' in html


def test_empty_filters_produces_no_extra_spans():
    html = build(id="doc-9", title="Test", body="Body", url="https://example.com")
    assert html.count("data-pagefind-filter=") == 1


def test_metadata_emitted():
    html = build(
        id="doc-10",
        title="Test",
        body="Body",
        url="https://example.com",
        metadata={"price": "29.99", "rating": "4.5"},
    )
    assert 'data-pagefind-meta="price:29.99"' in html
    assert 'data-pagefind-meta="rating:4.5"' in html


def test_metadata_values_are_escaped():
    html = build(
        id="doc-11",
        title="Test",
        body="Body",
        url="https://example.com",
        metadata={"note": "Tom & Jerry <b>"},
    )
    assert 'data-pagefind-meta="note:Tom &amp; Jerry &lt;b&gt;"' in html


def test_empty_metadata_produces_no_extra_elements():
    html = build(
        id="doc-12", title="Test", body="Body", url="https://example.com", date="2024-01-01"
    )
    assert html.count("data-pagefind-meta=") == 2


def test_sortable_emitted():
    html = build(
        id="doc-13",
        title="Test",
        body="Body",
        url="https://example.com",
        sortable={"price": "29.99", "rating": "4.5"},
    )
    assert 'data-pagefind-sort="price:29.99"' in html
    assert 'data-pagefind-sort="rating:4.5"' in html


def test_sortable_values_are_escaped():
    html = build(
        id="doc-14",
        title="Test",
        body="Body",
        url="https://example.com",
        sortable={"field": "a & b"},
    )
    assert 'data-pagefind-sort="field:a &amp; b"' in html


def test_empty_sortable_produces_no_sort_attributes():
    html = build(id="doc-15", title="Test", body="Body", url="https://example.com")
    assert "data-pagefind-sort=" not in html


def test_metadata_and_sortable_can_coexist():
    html = build(
        id="doc-16",
        title="Test",
        body="Body",
        url="https://example.com",
        metadata={"published": "2024-06-15"},
        sortable={"price": "9.99"},
    )
    assert 'data-pagefind-meta="published:2024-06-15"' in html
    assert 'data-pagefind-sort="price:9.99"' in html


def test_auto_includes_date_as_sortable():
    html = build(
        id="doc-17", title="Test", body="Body", url="https://example.com", date="2026-05-15"
    )
    assert 'data-pagefind-sort="date:2026-05-15"' in html


def test_explicit_sortable_date_takes_precedence():
    html = build(
        id="doc-18",
        title="Test",
        body="Body",
        url="https://example.com",
        date="2026-05-15",
        sortable={"date": "2026-01-01"},
    )
    assert 'data-pagefind-sort="date:2026-01-01"' in html
    assert 'data-pagefind-sort="date:2026-05-15"' not in html


def test_empty_date_not_auto_included_as_sortable():
    html = build(id="doc-19", title="Test", body="Body", url="https://example.com", date="")
    assert 'data-pagefind-sort="date:"' not in html
