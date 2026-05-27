"""番茄凭据解析：从 DevTools cURL 或裸 Cookie 串提取可用字段。"""
from __future__ import annotations

import re
from urllib.parse import parse_qs, quote, unquote


def sanitize_cookie_input(raw: str) -> str:
    """
    将用户粘贴的内容规范为 Cookie 请求头字符串。

    支持：
      - 裸 Cookie 串（novel_web_id=...; sessionid=...）
      - 完整 cURL 命令（提取 -b / --cookie 参数）
    """
    text = (raw or "").strip()
    if not text:
        return ""

    # 完整 cURL：优先提取 -b / --cookie
    if text.startswith("curl ") or "-H " in text or "--cookie" in text or " -b " in text:
        patterns = [
            r"-b\s+'([^']+)'",
            r'-b\s+"([^"]+)"',
            r"--cookie\s+'([^']+)'",
            r'--cookie\s+"([^"]+)"',
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.DOTALL)
            if match:
                return match.group(1).strip()

    # 误粘贴了非 Cookie 的 cURL（无 -b 参数）→ 视为无效
    if text.startswith("curl "):
        return ""

    return text


def normalize_cookie_header(cookie_str: str) -> str:
    """
    将 Cookie 头规范为仅含 ASCII，避免 httpx/http.cookiejar 在含中文等字符时 UnicodeEncodeError。

    已 percent-encoded 的值保持不变；裸 Unicode 值按 UTF-8 百分号编码。
    """
    raw = (cookie_str or "").strip()
    if not raw:
        return ""
    try:
        raw.encode("ascii")
        return raw
    except UnicodeEncodeError:
        pass

    parts: list[str] = []
    for segment in raw.split(";"):
        segment = segment.strip()
        if not segment:
            continue
        if "=" not in segment:
            parts.append(segment)
            continue
        name, _, value = segment.partition("=")
        name = name.strip()
        value = value.strip()
        if value and any(ord(ch) > 127 for ch in value):
            value = quote(value, safe="")
        parts.append(f"{name}={value}")
    return "; ".join(parts)


_FANQIE_POST_CREDS_HINT = (
    "上传/创建章节需要 URL 中的 msToken 与 a_bogus（有效期很短）。"
    "请在 DevTools 复制 cover_article（写正文）或 save_doc_history（保存历史）"
    "或 book/create 请求的「Copy as cURL」，整段粘贴到凭据框（不要只复制 -b Cookie）。"
)


def ensure_fanqie_post_creds(creds: dict) -> None:
    """POST 类番茄接口（cover_article / book/create）须带签名参数，否则返回空 text/plain。"""
    if not (creds.get("cookies") or "").strip():
        raise ValueError("番茄凭据未配置，请先连接作家账号")
    if not (creds.get("ms_token") or "").strip() or not (creds.get("a_bogus") or "").strip():
        raise ValueError(_FANQIE_POST_CREDS_HINT)


def extract_ms_token(raw: str) -> str:
    """从 cURL 的 query 或 --data-raw 中提取 msToken（若有）。"""
    text = raw or ""
    match = re.search(r"msToken=([^&\s'\"]+)", text)
    return match.group(1) if match else ""


def extract_csrf_token(raw: str) -> str:
    """从 cURL 请求头中提取 x-secsdk-csrf-token（若有）。"""
    text = raw or ""
    match = re.search(
        r"x-secsdk-csrf-token:\s*([^\s\\'\"]+)",
        text,
        re.IGNORECASE,
    )
    return match.group(1) if match else ""


def extract_a_bogus(raw: str) -> str:
    """从 cURL URL 查询串中提取 a_bogus（创建书籍等接口常需要，有效期很短）。"""
    text = raw or ""
    match = re.search(r"a_bogus=([^&\s'\"]+)", text)
    if not match:
        return ""
    from urllib.parse import unquote

    return unquote(match.group(1))


def extract_referer_enter_from(raw: str) -> str:
    """从 cURL Referer 提取 enter_from（如 newchapter_0 / newdraft）。"""
    text = raw or ""
    match = re.search(r"enter_from=([a-zA-Z0-9_]+)", text)
    return match.group(1) if match else ""


def extract_post_body_fields(raw: str) -> dict[str, str]:
    """从 cURL 的 --data-raw 解析 cover_article 表单字段（book_id / volume 等）。"""
    text = raw or ""
    match = (
        re.search(r"--data-raw\s+'([^']*)'", text, re.DOTALL)
        or re.search(r'--data-raw\s+"([^"]*)"', text, re.DOTALL)
    )
    if not match:
        return {}

    body = match.group(1)
    parsed = parse_qs(body, keep_blank_values=True)

    def _first(key: str) -> str:
        vals = parsed.get(key) or []
        return unquote(vals[0]) if vals else ""

    out: dict[str, str] = {}
    for key in ("book_id", "item_id", "volume_id", "volume_name", "title"):
        val = _first(key)
        if val:
            out[key] = val
    return out


def build_creds_from_curl_text(
    raw: str,
    *,
    csrf_token: str = "",
    ms_token: str = "",
    a_bogus: str = "",
    author_id: str = "",
) -> dict:
    """
    从整段 cURL 或裸 Cookie 构建凭据 dict（连接番茄时一次写入 fanqie_creds.json）。

    自动提取：-b Cookie、URL 中 msToken/a_bogus、x-secsdk-csrf-token、--data-raw 中的卷信息。
    """
    text = (raw or "").strip()
    cookies = sanitize_cookie_input(text)
    if not cookies and text and not text.startswith("curl "):
        cookies = text

    creds: dict[str, str] = {
        "cookies": normalize_cookie_header(cookies),
        "csrf_token": (csrf_token or "").strip() or extract_csrf_token(text),
        "ms_token": (ms_token or "").strip() or extract_ms_token(text),
        "a_bogus": (a_bogus or "").strip() or extract_a_bogus(text),
        "author_id": (author_id or "").strip(),
    }

    body_fields = extract_post_body_fields(text)
    if body_fields.get("book_id"):
        creds["default_book_id"] = body_fields["book_id"]
    if body_fields.get("volume_id"):
        creds["default_volume_id"] = body_fields["volume_id"]
    if body_fields.get("volume_name"):
        creds["default_volume_name"] = body_fields["volume_name"]

    return creds


def creds_summary(creds: dict) -> dict:
    """供 GET/POST /fanqie/config 返回的脱敏摘要。"""
    ms = (creds.get("ms_token") or "").strip()
    bogus = (creds.get("a_bogus") or "").strip()
    return {
        "configured": bool((creds.get("cookies") or "").strip()),
        "has_csrf_token": bool((creds.get("csrf_token") or "").strip()),
        "has_ms_token": bool(ms),
        "has_a_bogus": bool(bogus),
        "ms_token_preview": f"{ms[:16]}…" if len(ms) > 16 else ms,
        "a_bogus_preview": f"{bogus[:16]}…" if len(bogus) > 16 else bogus,
        "default_book_id": creds.get("default_book_id") or "",
        "default_volume_id": creds.get("default_volume_id") or "",
        "default_volume_name": creds.get("default_volume_name") or "",
    }


def merge_creds_from_curl(creds: dict, fresh_curl: str) -> dict:
    """
    用 DevTools 复制的 cover_article / save_doc_history / book/create cURL 刷新签名。

    Cookie 仅在 cURL 含 -b 时覆盖；否则保留原 session；卷信息有则更新 default_*。
    """
    text = (fresh_curl or "").strip()
    if not text:
        return dict(creds)

    parsed = build_creds_from_curl_text(text)
    merged = dict(creds)
    for key in ("cookies", "csrf_token", "ms_token", "a_bogus"):
        if parsed.get(key):
            merged[key] = parsed[key]
    for key in ("default_book_id", "default_volume_id", "default_volume_name"):
        if parsed.get(key):
            merged[key] = parsed[key]
    return merged
