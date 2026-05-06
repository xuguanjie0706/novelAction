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


def test_split_strips_leading_chapter_title():
    """验证正文自动过滤开头的章节标题行，与章节标题区分。"""
    plain_with_title = "第1章 重剑无锋，焚尽韩家铁骑\n\n正文第一段内容。\n\n正文第二段。"
    body, idx = split_plain_manuscript_and_index_block(plain_with_title)
    assert "重剑无锋" not in body
    assert "正文第一段内容" in body
    assert body.startswith("正文第一段")

    plain_chapter_en = "Chapter 12: The Final Battle\nThe hero stood alone..."
    body2, _ = split_plain_manuscript_and_index_block(plain_chapter_en)
    assert "The hero stood alone" in body2
    assert "Chapter 12" not in body2

    plain_no_title = "直接开始的正文，没有标题。"
    body3, _ = split_plain_manuscript_and_index_block(plain_no_title)
    assert body3 == "直接开始的正文，没有标题。"
