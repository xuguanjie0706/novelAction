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
