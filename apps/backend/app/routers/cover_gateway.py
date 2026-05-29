"""
cover_gateway.py — 封面图片网关调用与审计日志

职责：
- 调用 OpenAI 兼容的 /v1/images/generations 接口
- 构建审计日志记录（cover_image_call_logs 表）
- debug bundle 写入
- 网关返回状态分类

不含路由端点，仅被 cover.py 路由调用。
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Optional
from uuid import UUID

import httpx
from sqlalchemy.orm import Session

from app.models import CoverImageCallLog, Project
from app.models.llm_provider import LlmProvider
from app.services.cover_generate_debug import debug_stem_timestamp, write_cover_debug_bundle
from app.services.llm_config import normalize_openai_base_url

from app.routers.cover_b64_decode import normalize_b64_json_from_provider

logger = logging.getLogger(__name__)


# ── Schema（网关结果） ───────────────────────────────────────────

@dataclass
class CoverGenGatewayCall:
    """图片网关一次调用的结果（供路由与 cover_image_call_logs 共用）。"""

    success: bool
    out: Optional[object] = None  # CoverGenerateOut（避免循环引用，类型在 cover.py）
    elapsed_ms: int = 0
    http_status: int = 0
    gateway_url: str = ""
    error_user_message: str = ""
    upstream_response_text: Optional[str] = None


# ── 网关调用 ─────────────────────────────────────────────────────

def format_gateway_url(base_url: str) -> str:
    u = normalize_openai_base_url(base_url).rstrip("/")
    from urllib.parse import urlparse
    parsed = urlparse(u)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}/v1/images/generations"
    return f"{u}/images/generations"


def execute_images_generations(
    base_url: str,
    api_key: str,
    model_name: str,
    prompt: str,
    size: str,
    quality: str,
    *,
    cover_out_cls,
) -> CoverGenGatewayCall:
    """
    调用 OpenAI 兼容的 /v1/images/generations。
    不抛 HTTPException，由路由统一写审计日志后再映射为 HTTP 错误。

    Args:
        cover_out_cls: CoverGenerateOut 类引用（避免循环引用）
    """
    gateway_url = format_gateway_url(base_url)
    url = normalize_openai_base_url(base_url).rstrip("/") + "/images/generations"
    key = (api_key or "").strip() or "not-required"
    t0 = time.monotonic()

    payload = {
        "model": model_name,
        "prompt": prompt,
        "n": 1,
        "size": size,
        "quality": quality,
        "response_format": "b64_json",
    }

    try:
        with httpx.Client(timeout=120.0, follow_redirects=True) as client:
            resp = client.post(
                url,
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
    except httpx.TimeoutException:
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        return CoverGenGatewayCall(
            False, elapsed_ms=elapsed_ms, gateway_url=gateway_url,
            error_user_message="图片生成超时（>120s），请稍后重试",
        )
    except httpx.ConnectError as e:
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        return CoverGenGatewayCall(
            False, elapsed_ms=elapsed_ms, gateway_url=gateway_url,
            error_user_message=f"无法连接图片模型网关：{e}",
        )

    elapsed_ms = int((time.monotonic() - t0) * 1000)

    if resp.status_code >= 400:
        detail = ""
        try:
            err = resp.json()
            detail = err.get("error", {}).get("message") or str(err)
        except Exception:
            detail = resp.text[:400]
        return CoverGenGatewayCall(
            False, elapsed_ms=elapsed_ms, http_status=resp.status_code,
            gateway_url=gateway_url,
            error_user_message=f"图片模型返回错误：{detail}",
            upstream_response_text=resp.text[:50_000],
        )

    try:
        data = resp.json()
    except Exception:
        return CoverGenGatewayCall(
            False, elapsed_ms=elapsed_ms, http_status=resp.status_code,
            gateway_url=gateway_url,
            error_user_message="图片模型返回非 JSON 响应",
            upstream_response_text=resp.text[:50_000],
        )

    items = data.get("data") or []
    if not items:
        return CoverGenGatewayCall(
            False, elapsed_ms=elapsed_ms, http_status=resp.status_code,
            gateway_url=gateway_url,
            error_user_message="图片模型未返回图片数据",
            upstream_response_text=json.dumps(data, ensure_ascii=False)[:50_000],
        )

    item = items[0]
    if b64 := item.get("b64_json"):
        clean = normalize_b64_json_from_provider(b64)
        return CoverGenGatewayCall(
            True,
            out=cover_out_cls(data_url=f"data:image/png;base64,{clean}"),
            elapsed_ms=elapsed_ms, http_status=resp.status_code,
            gateway_url=gateway_url,
        )
    if img_url := item.get("url"):
        return CoverGenGatewayCall(
            True,
            out=cover_out_cls(image_url=img_url),
            elapsed_ms=elapsed_ms, http_status=resp.status_code,
            gateway_url=gateway_url,
        )

    return CoverGenGatewayCall(
        False, elapsed_ms=elapsed_ms, http_status=resp.status_code,
        gateway_url=gateway_url,
        error_user_message="图片模型返回格式未知（无 b64_json 也无 url）",
        upstream_response_text=json.dumps(data, ensure_ascii=False)[:50_000],
    )


# ── 状态分类 ─────────────────────────────────────────────────────

def upstream_failure_status(call: CoverGenGatewayCall) -> str:
    msg = call.error_user_message
    if "超时" in msg:
        return "upstream_network"
    if "无法连接" in msg:
        return "upstream_network"
    if call.http_status and call.http_status >= 400:
        return "upstream_http"
    if "未返回图片数据" in msg:
        return "upstream_empty"
    if "非 JSON" in msg or "格式未知" in msg:
        return "upstream_bad_json"
    return "upstream_error"


def http_status_for_gateway_failure(call: CoverGenGatewayCall) -> int:
    if "超时" in call.error_user_message:
        return 504
    if "无法连接" in call.error_user_message:
        return 502
    if call.http_status and 400 <= call.http_status < 600:
        return call.http_status
    return 502


# ── 审计日志 ─────────────────────────────────────────────────────

def insert_cover_image_log(
    db: Session,
    *,
    project: Project,
    provider: LlmProvider,
    prompt: str,
    size: str,
    quality: str,
    store_compressed: bool,
    status: str,
    duration_ms: int,
    response_kind: str,
    gateway_url: str,
    http_status: Optional[int],
    error_message: Optional[str],
    debug_bundle_rel_path: Optional[str],
    result_cover_url: Optional[str] = None,
) -> UUID:
    row = CoverImageCallLog(
        project_id=project.id,
        llm_provider_id=provider.id,
        provider_name=provider.name,
        model_name=provider.model_name,
        prompt=prompt,
        size=size,
        quality=quality,
        store_compressed=store_compressed,
        status=status,
        http_status=http_status,
        error_message=error_message,
        duration_ms=duration_ms,
        response_kind=response_kind,
        gateway_url=gateway_url,
        debug_bundle_rel_path=debug_bundle_rel_path,
        result_cover_url=result_cover_url,
    )
    db.add(row)
    db.flush()
    db.commit()
    return row.id


# ── Debug Bundle ─────────────────────────────────────────────────

def try_write_debug_bundle(
    *,
    project_id: str,
    provider: LlmProvider,
    prompt: str,
    size: str,
    quality: str,
    store_compressed: bool,
    gateway_url: str,
    status: str,
    duration_ms: int,
    response_kind: str,
    error_message: Optional[str],
    raw_b64: Optional[str] = None,
    image_url: Optional[str] = None,
    upstream_response_text: Optional[str] = None,
    decoded_bytes: Optional[bytes] = None,
) -> Optional[str]:
    try:
        return write_cover_debug_bundle(
            project_id=project_id,
            stem_suffix=debug_stem_timestamp(),
            meta={
                "project_id": project_id,
                "llm_provider_id": str(provider.id),
                "provider_name": provider.name,
                "model_name": provider.model_name,
                "gateway_url": gateway_url,
                "size": size,
                "quality": quality,
                "store_compressed": store_compressed,
                "status": status,
                "duration_ms": duration_ms,
                "response_kind": response_kind,
                "error_message": error_message,
                "prompt": prompt,
            },
            raw_b64=raw_b64,
            image_url=image_url,
            upstream_response_text=upstream_response_text,
            decoded_bytes=decoded_bytes,
        )
    except Exception:
        logger.exception("写入封面调试包失败")
        return None
