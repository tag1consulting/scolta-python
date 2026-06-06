"""Ported from tests/Util/MarkdownRendererTest.php (1:1)."""

from scolta.markdown import render


def test_empty_string_returns_empty():
    assert render("") == ""


def test_plain_text_wrapped_in_paragraph():
    assert render("Hello world") == "<p>Hello world</p>"


def test_bold_renders_as_strong():
    assert render("This is **bold** text") == "<p>This is <strong>bold</strong> text</p>"


def test_multiple_bold_in_same_line():
    assert (
        render("**first** and **second**")
        == "<p><strong>first</strong> and <strong>second</strong></p>"
    )


def test_link_renders_as_anchor():
    assert render("Visit [Example](https://example.com) now") == (
        '<p>Visit <a href="https://example.com" target="_blank" rel="noopener">Example</a> now</p>'
    )


def test_bullet_list_renders_as_ul():
    out = render("- First item\n- Second item\n- Third item")
    assert out == "<ul><li>First item</li><li>Second item</li><li>Third item</li></ul>"


def test_mixed_paragraphs_and_list():
    out = render("Introduction paragraph\n\n- Item one\n- Item two\n\nConclusion paragraph")
    assert out == (
        "<p>Introduction paragraph</p><ul><li>Item one</li><li>Item two</li></ul>"
        "<p>Conclusion paragraph</p>"
    )


def test_bold_inside_list_item():
    out = render("- A **bold** item\n- A normal item")
    assert out == "<ul><li>A <strong>bold</strong> item</li><li>A normal item</li></ul>"


def test_link_inside_list_item():
    out = render("- See [docs](https://docs.example.com) for details")
    assert out == (
        '<ul><li>See <a href="https://docs.example.com" target="_blank" rel="noopener">docs</a>'
        " for details</li></ul>"
    )


def test_xss_script_tag_is_escaped():
    out = render('<script>alert("xss")</script>')
    assert "<script>" not in out
    assert "&lt;script&gt;" in out


def test_xss_in_bold_is_escaped():
    out = render("**<img src=x onerror=alert(1)>**")
    assert "<img" not in out
    assert "<strong>" in out


def test_xss_in_link_text_is_escaped():
    out = render("[<script>evil</script>](https://example.com)")
    assert "<script>" not in out
    assert "&lt;script&gt;" in out


def test_html_entities_in_plain_text_are_escaped():
    out = render('Use the <div> element & "quotes"')
    assert "&lt;div&gt;" in out
    assert "&amp;" in out
    assert "&quot;quotes&quot;" in out


def test_multiple_paragraphs_separated_by_blank_lines():
    out = render("First paragraph\n\nSecond paragraph\n\nThird paragraph")
    assert out == "<p>First paragraph</p><p>Second paragraph</p><p>Third paragraph</p>"


def test_list_closed_at_end_of_input():
    out = render("- Item one\n- Item two")
    assert out == "<ul><li>Item one</li><li>Item two</li></ul>"


def test_whitespace_only_lines_act_as_blank_lines():
    out = render("Paragraph one\n   \nParagraph two")
    assert out == "<p>Paragraph one</p><p>Paragraph two</p>"


def test_italic_renders_as_em():
    assert render("This is *italic* text") == "<p>This is <em>italic</em> text</p>"


def test_multiple_italic_in_same_line():
    assert render("*first* and *second*") == "<p><em>first</em> and <em>second</em></p>"


def test_italic_inside_list_item():
    out = render("- An *italic* item\n- A normal item")
    assert out == "<ul><li>An <em>italic</em> item</li><li>A normal item</li></ul>"


def test_mixed_bold_and_italic():
    assert (
        render("**bold** and *italic* text")
        == "<p><strong>bold</strong> and <em>italic</em> text</p>"
    )


def test_bold_italic_renders_as_both():
    assert (
        render("This is ***bold italic*** text")
        == "<p>This is <strong><em>bold italic</em></strong> text</p>"
    )


def test_plain_text_without_markdown_unchanged():
    assert render("No formatting here") == "<p>No formatting here</p>"


def test_xss_in_italic_is_escaped():
    out = render("*<img src=x onerror=alert(1)>*")
    assert "<img" not in out
    assert "<em>" in out


def test_truncated_link_no_closing_paren_becomes_bold():
    out = render("Try [Chocolate Cake](https://example.com/recipe")
    assert "<strong>Chocolate Cake</strong>" in out
    assert "<a " not in out


def test_orphan_bracket_no_becomes_bold():
    out = render("See the [recipe guide] for details")
    assert "<strong>recipe guide</strong>" in out
    assert "<a " not in out


def test_valid_link_still_renders_as_anchor_after_cleanup():
    out = render("[Example](https://example.com)")
    assert '<a href="https://example.com"' in out
    assert "<strong>Example</strong>" not in out


def test_mixed_valid_and_broken_links_on_same_line():
    out = render("See [Good Link](https://example.com) and also [Broken](https://cut")
    assert '<a href="https://example.com"' in out
    assert "<strong>Broken</strong>" in out


def test_orphan_bracket_in_list_item():
    out = render("- Try [the recipe] today")
    assert "<li>" in out
    assert "<strong>the recipe</strong>" in out
