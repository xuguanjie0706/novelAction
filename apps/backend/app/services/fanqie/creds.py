"""番茄凭据解析：从 DevTools cURL 或裸 Cookie 串提取可用字段。"""
from __future__ import annotations

import re


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


def merge_creds_from_curl(creds: dict, fresh_curl: str) -> dict:
    """
    用 DevTools 复制的 create/upload cURL 刷新 msToken、a_bogus、csrf。

    Cookie 仅在 cURL 含 -b 时覆盖；否则保留原 session。
    """
    text = (fresh_curl or "").strip()
    if not text:
        return dict(creds)

    merged = dict(creds)
    cookies = sanitize_cookie_input(text)
    if cookies:
        merged["cookies"] = cookies
    ms = extract_ms_token(text)
    if ms:
        merged["ms_token"] = ms
    bogus = extract_a_bogus(text)
    if bogus:
        merged["a_bogus"] = bogus
    csrf = extract_csrf_token(text)
    if csrf:
        merged["csrf_token"] = csrf
    return merged
