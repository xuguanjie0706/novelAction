"""章节纯文本：叙事正文 vs 稿末 ### ch_ 索引块（与客户端规则对齐）。"""

from __future__ import annotations

import re


def split_plain_manuscript_and_index_block(plain: str) -> tuple[str, str | None]:
    """
    将去 HTML 后的纯文本拆成「叙事正文」与「稿末 ### ch_ / 章节速查索引」块。
    业务库只存叙事时，稿末仅用于解析入库或存在于 llm_call_logs。
    """
    t = (plain or "").replace("\r\n", "\n")
    if not t.strip():
        return "", None
    split = -1
    m = re.search(r"\n(#{1,6}\s*ch_\d+)", t, flags=re.I)
    if m:
        split = m.start() + 1
    else:
        m0 = re.match(r"^\s*(#{1,6}\s*ch_\d+)", t, flags=re.I)
        if m0:
            split = t.find(m0.group(1))
            if split < 0:
                split = 0
    alt_nl = t.find("\n【章节速查索引】")
    if alt_nl >= 0 and (split < 0 or alt_nl + 1 < split):
        split = alt_nl + 1
    st = t.lstrip()
    lead = len(t) - len(st)
    if st.startswith("【章节速查索引】"):
        if split < 0 or lead < split:
            split = lead
    if split < 0:
        return t.strip(), None
    body = t[:split].rstrip().strip()
    index_block = t[split:].strip()
    if not index_block:
        return t.strip(), None
    return body, index_block


def html_to_plain_for_revision(html: str | None) -> str:
    """
    与客户端 `htmlToPlainForSplit` 对齐：段落边界用换行还原，便于在纯文本域做摘录级替换。
    """
    if not (html or "").strip():
        return ""
    t = html
    t = re.sub(r"</p\s*>", "\n\n", t, flags=re.I)
    t = re.sub(r"<br\s*/?>", "\n", t, flags=re.I)
    t = re.sub(r"</div\s*>", "\n", t, flags=re.I)
    t = re.sub(r"</h[1-6]\s*>", "\n\n", t, flags=re.I)
    t = re.sub(r"<[^>]+>", "", t)
    t = t.replace("\u00a0", " ")
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def plain_text_blocks_to_html(plain: str) -> str:
    """与客户端 `plainTextBlocksToHtml` 一致：双换行分段 → <p>。"""
    blocks = [b.strip() for b in re.split(r"\n{2,}", plain) if b.strip()]
    if not blocks:
        return "<p></p>"

    def esc(s: str) -> str:
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")

    return "".join(f"<p>{esc(b)}</p>" for b in blocks)
