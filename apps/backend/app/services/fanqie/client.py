"""
番茄 API 代理客户端：凭据 I/O + httpx 转发。

路由层只负责 HTTP 契约，实际请求逻辑集中在此模块。
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx
from fastapi import HTTPException

from app.services.fanqie.creds import (
    extract_a_bogus,
    extract_csrf_token,
    extract_ms_token,
    sanitize_cookie_input,
)

CREDS_FILE = Path(os.getenv("FANQIE_CREDS_FILE", "fanqie_creds.json"))
BASE = "https://fanqienovel.com"
COMMON_PARAMS = {"aid": "2503", "app_name": "muye_novel"}
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/148.0.0.0 Safari/537.36"
)


def load_creds() -> dict:
    if CREDS_FILE.exists():
        return json.loads(CREDS_FILE.read_text(encoding="utf-8"))
    return {}


def save_creds(data: dict) -> None:
    CREDS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def prepare_creds_from_body(
    cookies_raw: str,
    *,
    csrf_token: str = "",
    ms_token: str = "",
    a_bogus: str = "",
    author_id: str = "",
) -> dict:
    """解析用户提交的凭据（支持整段 cURL 粘贴）。"""
    raw = cookies_raw or ""
    cookies = sanitize_cookie_input(raw)
    if not cookies:
        raise HTTPException(
            status_code=400,
            detail="无法解析 Cookie：请粘贴 DevTools cURL 中 -b '...' 的内容，或裸 Cookie 串",
        )
    return {
        "cookies": cookies,
        "csrf_token": (csrf_token or "").strip() or extract_csrf_token(raw),
        "ms_token": (ms_token or "").strip() or extract_ms_token(raw),
        "a_bogus": (a_bogus or "").strip() or extract_a_bogus(raw),
        "author_id": (author_id or "").strip(),
    }


def _auth_params(creds: dict) -> dict[str, str]:
    params = {**COMMON_PARAMS}
    ms = creds.get("ms_token", "").strip()
    if ms:
        params["msToken"] = ms
    bogus = creds.get("a_bogus", "").strip()
    if bogus:
        params["a_bogus"] = bogus
    return params


def make_client(creds: dict, referer: str | None = None) -> httpx.AsyncClient:
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "zh-CN,zh;q=0.9",
        "user-agent": USER_AGENT,
        "origin": BASE,
        "referer": referer or f"{BASE}/main/writer/book-manage",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "cookie": creds.get("cookies", ""),
    }
    csrf = creds.get("csrf_token", "").strip()
    if csrf:
        headers["x-secsdk-csrf-token"] = csrf
    return httpx.AsyncClient(
        base_url=BASE,
        headers=headers,
        timeout=20.0,
        follow_redirects=True,
    )


def require_creds() -> dict:
    creds = load_creds()
    if not creds.get("cookies"):
        raise HTTPException(status_code=403, detail="番茄凭据未配置，请先 POST /api/v1/fanqie/config")
    return creds


async def proxy_get(
    path: str,
    params: dict | None = None,
    *,
    referer: str | None = None,
) -> Any:
    creds = require_creds()
    merged = {**_auth_params(creds), **(params or {})}
    try:
        async with make_client(creds, referer=referer) as client:
            resp = await client.get(path, params=merged)
    except httpx.TimeoutException:
        raise HTTPException(status_code=502, detail="番茄 API 请求超时（20s）")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"请求异常: {type(exc).__name__}: {exc}")
    return _parse_json_response(resp)


async def proxy_post(
    path: str,
    data: dict[str, str],
    *,
    referer: str | None = None,
    content_type: str = "application/x-www-form-urlencoded;charset=UTF-8",
    creds: dict | None = None,
) -> Any:
    active = creds or require_creds()
    merged = _auth_params(active)
    headers_extra = {"content-type": content_type}
    try:
        async with make_client(active, referer=referer) as client:
            resp = await client.post(
                path,
                params=merged,
                data=data,
                headers=headers_extra,
            )
    except httpx.TimeoutException:
        raise HTTPException(status_code=502, detail="番茄 API 请求超时（20s）")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"请求异常: {type(exc).__name__}: {exc}")
    return _parse_json_response(resp)


async def proxy_post_multipart(
    path: str,
    *,
    files: dict[str, tuple[str, bytes, str]],
    referer: str | None = None,
    creds: dict | None = None,
) -> Any:
    """multipart/form-data POST（封面上传 upfile 等）。"""
    active = creds or require_creds()
    merged = _auth_params(active)
    try:
        async with make_client(active, referer=referer) as client:
            resp = await client.post(path, params=merged, files=files)
    except httpx.TimeoutException:
        raise HTTPException(status_code=502, detail="番茄 API 请求超时（20s）")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"请求异常: {type(exc).__name__}: {exc}")
    return _parse_json_response(resp)


def _parse_json_response(resp: httpx.Response) -> Any:
    if resp.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"番茄 API 返回 HTTP {resp.status_code}，路径可能有误",
        )
    ct = resp.headers.get("content-type", "")
    if "json" not in ct:
        preview = resp.text[:200].replace("\n", " ")
        raise HTTPException(
            status_code=502,
            detail=f"番茄返回非 JSON（Content-Type: {ct}），Cookie 可能已过期。响应预览: {preview}",
        )
    body = resp.json()
    code = body.get("code", -1)
    if code != 0:
        msg = body.get("message") or body.get("msg") or json.dumps(body, ensure_ascii=False)[:200]
        raise HTTPException(status_code=502, detail=f"番茄 API 错误 code={code}: {msg}")
    return body.get("data", body)
