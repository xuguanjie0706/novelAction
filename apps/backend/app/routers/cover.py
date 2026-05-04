"""
封面生成路由

POST /api/v1/projects/{project_id}/cover/generate
  - 调用图片类型 LlmProvider（provider_type='image'）的 /v1/images/generations 接口
  - 默认将结果压缩为 WebP 落盘，返回短路径 cover_url（/api/v1/covers/files/...）供入库与 <img src>
  - store_compressed=false 时仍返回 data_url / image_url（大响应）

POST /api/v1/projects/{project_id}/cover/upload
  - multipart 字段 file：用户上传的封面图（JPG/PNG/WebP/GIF），压缩为 WebP 落盘并返回 cover_url

GET  /api/v1/cover/image-providers
  - 返回所有 enabled + provider_type='image' 的提供者列表（前端选择用）
"""
import base64
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
from app.services.llm_config import normalize_openai_base_url

router = APIRouter(tags=["cover"])

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
    cover_url: Optional[str] = None  # 站内静态路径，可写入 projects.cover_url
    data_url: Optional[str] = None   # data:image/png;base64,…  (b64_json 模式)
    image_url: Optional[str] = None  # 部分 provider 直接返回 URL


# ── Helpers ────────────────────────────────────────────────────────────────

def _call_images_generations(
    base_url: str,
    api_key: str,
    model_name: str,
    prompt: str,
    size: str,
    quality: str,
) -> CoverGenerateOut:
    """
    调用 OpenAI 兼容的 /v1/images/generations 接口。
    优先请求 b64_json（避免临时 URL 过期），若 provider 不支持则降级用 url。
    """
    url = normalize_openai_base_url(base_url).rstrip("/") + "/images/generations"
    key = (api_key or "").strip() or "not-required"

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
        raise HTTPException(504, "图片生成超时（>120s），请稍后重试")
    except httpx.ConnectError as e:
        raise HTTPException(502, f"无法连接图片模型网关：{e}")

    if resp.status_code >= 400:
        detail = ""
        try:
            err = resp.json()
            detail = err.get("error", {}).get("message") or str(err)
        except Exception:
            detail = resp.text[:400]
        raise HTTPException(resp.status_code, f"图片模型返回错误：{detail}")

    try:
        data = resp.json()
    except Exception:
        raise HTTPException(502, "图片模型返回非 JSON 响应")

    # OpenAI 格式：{ data: [{ b64_json: "..." }] } 或 { data: [{ url: "..." }] }
    items = data.get("data") or []
    if not items:
        raise HTTPException(502, "图片模型未返回图片数据")

    item = items[0]
    if b64 := item.get("b64_json"):
        return CoverGenerateOut(data_url=f"data:image/png;base64,{b64}")
    if img_url := item.get("url"):
        return CoverGenerateOut(image_url=img_url)

    raise HTTPException(502, "图片模型返回格式未知（无 b64_json 也无 url）")


def _raw_bytes_from_generate_out(out: CoverGenerateOut) -> bytes:
    if out.data_url and "," in out.data_url:
        try:
            b64 = out.data_url.split(",", 1)[1]
            return base64.b64decode(b64)
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
    """上传本地图片作为封面，压缩为 WebP 后写入 data/covers。"""
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
    默认压缩为 WebP 落盘并返回 cover_url；前端可 PATCH /projects/{id} 将 cover_url 写入数据库。
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

    raw_out = _call_images_generations(
        base_url=provider.base_url,
        api_key=provider.api_key or "",
        model_name=provider.model_name,
        prompt=payload.prompt,
        size=payload.size,
        quality=payload.quality,
    )
    if not payload.store_compressed:
        return raw_out
    try:
        blob = _raw_bytes_from_generate_out(raw_out)
        path = compress_and_save_cover_webp(str(project.id), blob)
        return CoverGenerateOut(cover_url=path)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(502, str(e)) from e
