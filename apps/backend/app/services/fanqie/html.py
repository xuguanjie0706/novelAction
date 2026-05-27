"""番茄编辑器 HTML：TipTap / 纯文本 → cover_article 的 content 字段。"""
from __future__ import annotations

import re

from app.utils.chapter_manuscript import html_to_plain_for_revision

_RE_SCRIPT = re.compile(r"<script[\s\S]*?</script>", re.I)
_RE_HAS_P = re.compile(r"<p[\s>]", re.I)


def plain_to_fanqie_html(text: str) -> str:
    """
    将纯文本转换为番茄编辑器 HTML 格式。

    每非空行转为 ``<p>...</p>``，空行转为 ``<p></p>``。
    """
    lines = (text or "").splitlines()
    parts: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped:
            escaped = (
                stripped.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;")
            )
            parts.append(f"<p>{escaped}</p>")
        else:
            parts.append("<p></p>")
    while parts and parts[-1] == "<p></p>":
        parts.pop()
    return "".join(parts) if parts else "<p></p>"


def chapter_html_to_fanqie_html(raw_html: str) -> str:
    """
    将章节 HTML（TipTap 或已含 <p> 的片段）转为番茄 cover_article 的 content。

    已有 <p> 段落时直接复用（仅去 script），避免 HTML→纯文本→HTML 二次转换丢字。
    """
    html = _RE_SCRIPT.sub("", (raw_html or "").strip())
    if not html:
        return ""
    if _RE_HAS_P.search(html):
        return html
    plain = html_to_plain_for_revision(html)
    return plain_to_fanqie_html(plain)


def fanqie_html_plain_length(html: str) -> int:
    """估算上传正文的纯文本字数（用于校验与前端提示）。"""
    text = re.sub(r"<[^>]+>", "", html or "")
    return len(text.strip())
