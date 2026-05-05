import hashlib
import json
import re
from typing import Optional
from uuid import UUID


def plain_text(html: str | None) -> str:
    return re.sub(r"<[^>]+>", "", html or "").strip()


def truncate(text: str | None, limit: int) -> str:
    clean = (text or "").strip()
    return clean[:limit]


def extract_patch_text(value) -> str:
    if isinstance(value, dict):
        for key in ("replacement", "suggestion", "suggested_fix", "patch", "description"):
            text = value.get(key)
            if isinstance(text, str) and text.strip():
                return text.strip()
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, str):
        return value.strip()
    return ""


def strip_tail_meta_lines(text: str | None) -> str:
    """过滤章末结构化元信息，避免误当正文承接。"""
    lines = str(text or "").splitlines()
    cleaned: list[str] = []
    for line in lines:
        raw = line.strip()
        if not raw:
            cleaned.append(line)
            continue
        if re.match(r"^\*{0,2}\s*章末钩子强度", raw):
            continue
        if re.match(r"^\*{0,2}\s*伏笔埋设", raw):
            continue
        if re.match(r"^[-•]\s*F[-_ ]?\d{1,4}\s*[:：\-]", raw, flags=re.IGNORECASE):
            continue
        if re.search(r"\bch[_-]?\d+\s*(回收|铺垫)\b", raw, flags=re.IGNORECASE):
            continue
        cleaned.append(line)
    return "\n".join(cleaned).strip()


def brief_text(value: str | None, limit: int = 90) -> str:
    return truncate(value, limit).replace("\n", " ")


def format_brief_line(name: str, attrs: list[str]) -> str:
    clean_attrs = [attr for attr in attrs if attr]
    return f"{name}（{'；'.join(clean_attrs)}）" if clean_attrs else name


def safe_uuid(raw: Optional[str]):
    if not raw:
        return None
    try:
        return UUID(str(raw))
    except Exception:
        return None


def chapter_debrief_content_hash(content: str) -> str:
    return hashlib.sha256((content or "").encode("utf-8")).hexdigest()
