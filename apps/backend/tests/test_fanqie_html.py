"""番茄 HTML 转换单测。"""
from app.services.fanqie.html import (
    chapter_html_to_fanqie_html,
    fanqie_html_plain_length,
    plain_to_fanqie_html,
)


def test_plain_to_fanqie_html():
    assert plain_to_fanqie_html("第一行\n\n第二行") == "<p>第一行</p><p></p><p>第二行</p>"


def test_chapter_html_preserves_tipTap_paragraphs():
    raw = '<p></p><p>“吞了这缕圣火灵根”</p><p>第二段</p>'
    out = chapter_html_to_fanqie_html(raw)
    assert out == raw
    assert fanqie_html_plain_length(out) >= 10


def test_chapter_html_from_plain_text():
    out = chapter_html_to_fanqie_html("只有纯文本一行")
    assert out == "<p>只有纯文本一行</p>"
