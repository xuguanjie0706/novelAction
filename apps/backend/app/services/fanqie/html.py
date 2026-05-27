"""番茄编辑器 HTML：纯文本段落 → <p> 标签。"""


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
