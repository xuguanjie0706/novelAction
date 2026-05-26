"""
封面生成路由

POST /api/v1/projects/{project_id}/cover/generate
  - 调用图片类型 LlmProvider（provider_type='image'）的 /v1/images/generations 接口
  - 默认将结果压缩为 WebP 持久化；local 返回 /api/v1/covers/files/...，cos 返回腾讯云公网 URL
  - store_compressed=false 时仍返回 data_url / image_url（大响应）
  - 每次调用写入 cover_image_call_logs；网关成功但解码/压缩失败时落盘 data/covers/debug/<stem>/

POST /api/v1/projects/{project_id}/cover/upload
  - multipart 字段 file：用户上传的封面图（JPG/PNG/WebP/GIF），压缩为 WebP 落盘并返回 cover_url

GET  /api/v1/cover/image-providers
  - 返回所有 enabled + provider_type='image' 的提供者列表（前端选择用）

实现拆分：
  - cover_b64_decode.py: base64 解码/纠错/魔数识别
  - cover_gateway.py: 网关调用/审计日志/debug bundle
"""
import logging
from typing import List, Optional
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Project
from app.models.llm_provider import LlmProvider
from app.services.cover_storage import compress_and_save_cover_webp

from app.routers.cover_b64_decode import (
    decode_b64_image_payload,
    normalize_b64_json_from_provider,
)
from app.routers.cover_gateway import (
    CoverGenGatewayCall,
    execute_images_generations,
    http_status_for_gateway_failure,
    insert_cover_image_log,
    try_write_debug_bundle,
    upstream_failure_status,
)

router = APIRouter(tags=["cover"])
logger = logging.getLogger(__name__)

MAX_COVER_UPLOAD_BYTES = 15 * 1024 * 1024


# ── Schema ─────────────────────────────────────────────────────────────────

class ImageProviderBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())
    id: UUID
    name: str
    model_name: str


class CoverGenerateIn(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    llm_provider_id: UUID
    prompt: str = Field(..., max_length=2000)
    size: str = Field("1024x1024", pattern=r"^\d+x\d+$")
    quality: str = Field("standard", pattern=r"^(standard|hd)$")
    store_compressed: bool = True


class CoverGenerateOut(BaseModel):
    """store_compressed 时优先返回 cover_url；否则为 data URL 或外链。"""
    cover_url: Optional[str] = None
    data_url: Optional[str] = None
    image_url: Optional[str] = None


# ── Helpers ────────────────────────────────────────────────────────────────

def _raw_b64_from_out(out: CoverGenerateOut) -> Optional[str]:
    if out.data_url and "," in out.data_url:
        inner = out.data_url.split(",", 1)[1]
        clean = normalize_b64_json_from_provider(inner)
        return clean or None
    return None


def _raw_bytes_from_generate_out(out: CoverGenerateOut) -> bytes:
    if out.data_url and "," in out.data_url:
        try:
            b64 = normalize_b64_json_from_provider(out.data_url.split(",", 1)[1])
            return decode_b64_image_payload(b64)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(502, f"解析 base64 图片失败：{e}") from e
    if out.image_url:
        try:
            with httpx.Client(timeout=60.0, follow_redirects=True) as client:
                r = client.get(out.image_url)
        except httpx.TimeoutException:
            raise HTTPException(504, "下载生成图超时") from None
        except httpx.ConnectError as e:
            raise HTTPException(502, f"无法下载生成图：{e}") from e
        if r.status_code >= 400:
            raise HTTPException(502, f"下载生成图失败：HTTP {r.status_code}")
        return r.content
    raise HTTPException(502, "未获得可保存的图片数据")


def _log_kwargs(provider, payload: CoverGenerateIn):
    """提取审计日志公共参数，减少重复代码。"""
    return dict(
        prompt=payload.prompt, size=payload.size,
        quality=payload.quality, store_compressed=payload.store_compressed,
    )


# ── Routes ─────────────────────────────────────────────────────────────────

@router.get("/cover/image-providers", response_model=List[ImageProviderBrief])
def list_image_providers(db: Session = Depends(get_db)):
    """返回所有启用的图片类提供者，供前端下拉选择。"""
    rows = (
        db.query(LlmProvider)
        .filter(
            LlmProvider.enabled.is_(True),
            LlmProvider.provider_type == "image",
        )
        .order_by(LlmProvider.sort_order.asc(), LlmProvider.updated_at.desc())
        .all()
    )
    return [ImageProviderBrief(id=r.id, name=r.name, model_name=r.model_name) for r in rows]


@router.post("/projects/{project_id}/cover/upload", response_model=CoverGenerateOut)
async def upload_cover(
    project_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """上传本地图片作为封面，压缩为 WebP 后写入本地或腾讯云 COS。"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "项目不存在")

    data = await file.read()
    if len(data) == 0:
        raise HTTPException(400, "空文件")
    if len(data) > MAX_COVER_UPLOAD_BYTES:
        raise HTTPException(400, f"文件过大，请上传小于 {MAX_COVER_UPLOAD_BYTES // (1024 * 1024)}MB 的图片")

    try:
        path = compress_and_save_cover_webp(str(project.id), data)
        return CoverGenerateOut(cover_url=path)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/projects/{project_id}/cover/generate", response_model=CoverGenerateOut)
def generate_cover(
    project_id: str,
    payload: CoverGenerateIn,
    db: Session = Depends(get_db),
):
    """
    用指定的图片提供者为项目生成封面。
    默认压缩为 WebP 持久化并返回 cover_url；前端可 PATCH 写入项目。
    每次调用写入 cover_image_call_logs；解析/压缩失败时优先落盘 payload.b64.txt 便于回溯。
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "项目不存在")

    provider = (
        db.query(LlmProvider)
        .filter(
            LlmProvider.id == payload.llm_provider_id,
            LlmProvider.enabled.is_(True),
            LlmProvider.provider_type == "image",
        )
        .first()
    )
    if not provider:
        raise HTTPException(404, "找不到该图片提供者，请确认已在管理后台启用并设置为 image 类型")

    call = execute_images_generations(
        base_url=provider.base_url,
        api_key=provider.api_key or "",
        model_name=provider.model_name,
        prompt=payload.prompt,
        size=payload.size,
        quality=payload.quality,
        cover_out_cls=CoverGenerateOut,
    )
    pid = str(project.id)
    lk = _log_kwargs(provider, payload)

    # ── 网关失败 ──────────────────────────────────────────────
    if not call.success:
        st = upstream_failure_status(call)
        dbg = try_write_debug_bundle(
            project_id=pid, provider=provider, **lk,
            gateway_url=call.gateway_url, status=st,
            duration_ms=call.elapsed_ms, response_kind="none",
            error_message=call.error_user_message,
            upstream_response_text=call.upstream_response_text,
        )
        insert_cover_image_log(
            db, project=project, provider=provider, **lk,
            status=st, duration_ms=call.elapsed_ms, response_kind="none",
            gateway_url=call.gateway_url, http_status=call.http_status or None,
            error_message=call.error_user_message,
            debug_bundle_rel_path=dbg, result_cover_url=None,
        )
        raise HTTPException(http_status_for_gateway_failure(call), call.error_user_message)

    raw_out = call.out
    assert raw_out is not None
    raw_b64 = _raw_b64_from_out(raw_out)
    response_kind = "b64_json" if raw_b64 else "url"

    # ── 不压缩，直接返回 ─────────────────────────────────────
    if not payload.store_compressed:
        preview_url = raw_out.image_url if raw_out.image_url else None
        insert_cover_image_log(
            db, project=project, provider=provider, **lk,
            status="ok", duration_ms=call.elapsed_ms, response_kind=response_kind,
            gateway_url=call.gateway_url, http_status=call.http_status,
            error_message=None, debug_bundle_rel_path=None,
            result_cover_url=preview_url,
        )
        return raw_out

    # ── 解码原始字节 ─────────────────────────────────────────
    try:
        blob = _raw_bytes_from_generate_out(raw_out)
    except HTTPException as e:
        detail = str(e.detail) if e.detail is not None else "解析或下载图片失败"
        dbg = try_write_debug_bundle(
            project_id=pid, provider=provider, **lk,
            gateway_url=call.gateway_url, status="decode_error",
            duration_ms=call.elapsed_ms, response_kind=response_kind,
            error_message=detail, raw_b64=raw_b64, image_url=raw_out.image_url,
        )
        insert_cover_image_log(
            db, project=project, provider=provider, **lk,
            status="decode_error", duration_ms=call.elapsed_ms,
            response_kind=response_kind, gateway_url=call.gateway_url,
            http_status=call.http_status, error_message=detail,
            debug_bundle_rel_path=dbg, result_cover_url=None,
        )
        raise

    # ── 压缩为 WebP ──────────────────────────────────────────
    try:
        path = compress_and_save_cover_webp(pid, blob)
    except ValueError as e:
        msg = str(e)
        dbg = try_write_debug_bundle(
            project_id=pid, provider=provider, **lk,
            gateway_url=call.gateway_url, status="compress_error",
            duration_ms=call.elapsed_ms, response_kind=response_kind,
            error_message=msg, raw_b64=raw_b64, image_url=raw_out.image_url,
            decoded_bytes=blob,
        )
        insert_cover_image_log(
            db, project=project, provider=provider, **lk,
            status="compress_error", duration_ms=call.elapsed_ms,
            response_kind=response_kind, gateway_url=call.gateway_url,
            http_status=call.http_status, error_message=msg,
            debug_bundle_rel_path=dbg, result_cover_url=None,
        )
        raise HTTPException(502, msg) from e

    # ── 成功 ─────────────────────────────────────────────────
    insert_cover_image_log(
        db, project=project, provider=provider, **lk,
        status="ok", duration_ms=call.elapsed_ms, response_kind=response_kind,
        gateway_url=call.gateway_url, http_status=call.http_status,
        error_message=None, debug_bundle_rel_path=None,
        result_cover_url=path,
    )
    return CoverGenerateOut(cover_url=path)
