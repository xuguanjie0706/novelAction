from app.utils.chapter_manuscript import (
    html_to_plain_for_revision,
    plain_text_blocks_to_html,
    split_plain_manuscript_and_index_block,
)


def test_html_to_plain_for_revision_preserves_paragraph_breaks():
    html = "<p>第一段</p><p>第二段</p>"
    plain = html_to_plain_for_revision(html)
    assert "第一段" in plain
    assert "第二段" in plain
    assert "\n\n" in plain


def test_micro_replace_pipeline():
    html = "<p>他在青云城。</p><p>次日动身。</p>"
    plain = html_to_plain_for_revision(html)
    body, idx = split_plain_manuscript_and_index_block(plain)
    assert "青云城" in body
    new_body = body.replace("青云城", "远水城", 1)
    new_plain = new_body + (f"\n\n{idx}" if idx else "")
    out = plain_text_blocks_to_html(new_plain)
    assert "远水城" in out
    assert "<p>" in out
