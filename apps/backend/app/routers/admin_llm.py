import time
from typing import List, Optional
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import LlmProvider
from app.schemas.llm_provider import (
    LlmProviderCreate,
    LlmProviderUpdate,
    LlmProviderOut,
    LlmTestConnectionIn,
    LlmTestConnectionOut,
    mask_api_key_hint,
)
from app.services.llm_config import clear_other_defaults, normalize_openai_base_url

router = APIRouter(prefix="/admin/llm-providers", tags=["admin-llm"])


def _run_openai_compatible_ping(base_url: str, model_name: str, api_key: Optional[str]) -> LlmTestConnectionOut:
    """对 OpenAI 兼容网关发一条最小 chat 请求，验证联通与鉴权。"""
    base = normalize_openai_base_url(base_url.strip())
    url = f"{base.rstrip('/')}/chat/completions"
    key = (api_key or "").strip() or "not-required"
    t0 = time.perf_counter()
    try:
        with httpx.Client(timeout=25.0, follow_redirects=True) as client:
            r = client.post(
                url,
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model_name.strip(),
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 8,
                },
            )
        latency_ms = int((time.perf_counter() - t0) * 1000)
        if r.status_code >= 400:
            preview = (r.text or "")[:400]
            return LlmTestConnectionOut(
                ok=False,
                message=f"HTTP {r.status_code}: {preview or r.reason_phrase}",
                latency_ms=latency_ms,
                http_status=r.status_code,
            )
        try:
            data = r.json()
        except Exception:
            return LlmTestConnectionOut(
                ok=False,
                message="响应不是合法 JSON",
                latency_ms=latency_ms,
                http_status=r.status_code,
            )
        if isinstance(data, dict) and data.get("choices"):
            return LlmTestConnectionOut(
                ok=True,
                message="上游已返回 choices，联通正常",
                latency_ms=latency_ms,
                http_status=r.status_code,
            )
        err = data.get("error") if isinstance(data, dict) else None
        if isinstance(err, dict):
            msg = err.get("message") or str(err)
        elif isinstance(err, str):
            msg = err
        else:
            msg = (r.text or "")[:300] or "未返回 choices"
        return LlmTestConnectionOut(
            ok=False,
            message=msg,
            latency_ms=latency_ms,
            http_status=r.status_code,
        )
    except httpx.TimeoutException:
        return LlmTestConnectionOut(ok=False, message="连接超时（>25s）")
    except httpx.ConnectError as e:
        return LlmTestConnectionOut(ok=False, message=f"无法连接网关：{e!s}")
    except Exception as e:
        return LlmTestConnectionOut(ok=False, message=f"请求异常：{e!s}")


def _to_out(row: LlmProvider) -> LlmProviderOut:
    has_k, hint = mask_api_key_hint(row.api_key)
    return LlmProviderOut(
        id=row.id,
        name=row.name,
        base_url=row.base_url,
        model_name=row.model_name,
        provider_type=row.provider_type or "text",
        has_api_key=has_k,
        api_key_hint=hint,
        enabled=row.enabled,
        is_default=row.is_default,
        sort_order=row.sort_order,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.post("/test-connection", response_model=LlmTestConnectionOut)
def test_connection_adhoc(payload: LlmTestConnectionIn):
    """使用表单中的 base_url / model / key 做一次联通性检测（不写库）。"""
    return _run_openai_compatible_ping(
        payload.base_url,
        payload.model_name,
        payload.api_key,
    )


@router.post("/{provider_id}/test-connection", response_model=LlmTestConnectionOut)
def test_connection_saved(provider_id: UUID, db: Session = Depends(get_db)):
    """对已保存的一条配置做联通性检测（使用库中密钥）。"""
    row = db.query(LlmProvider).filter(LlmProvider.id == provider_id).first()
    if not row:
        raise HTTPException(404, "大模型配置不存在")
    return _run_openai_compatible_ping(row.base_url, row.model_name, row.api_key)


@router.get("/", response_model=List[LlmProviderOut])
def list_providers(db: Session = Depends(get_db)):
    rows = db.query(LlmProvider).order_by(LlmProvider.sort_order.asc(), LlmProvider.created_at.asc()).all()
    return [_to_out(r) for r in rows]


@router.post("/", response_model=LlmProviderOut, status_code=201)
def create_provider(payload: LlmProviderCreate, db: Session = Depends(get_db)):
    row = LlmProvider(
        name=payload.name.strip(),
        base_url=payload.base_url.strip(),
        model_name=payload.model_name.strip(),
        provider_type=payload.provider_type or "text",
        api_key=(payload.api_key.strip() if payload.api_key else None),
        enabled=payload.enabled,
        is_default=payload.is_default,
        sort_order=payload.sort_order,
    )
    db.add(row)
    db.flush()
    if row.is_default:
        clear_other_defaults(db, row.id)
    db.commit()
    db.refresh(row)
    return _to_out(row)


@router.patch("/{provider_id}", response_model=LlmProviderOut)
def update_provider(provider_id: UUID, payload: LlmProviderUpdate, db: Session = Depends(get_db)):
    row = db.query(LlmProvider).filter(LlmProvider.id == provider_id).first()
    if not row:
        raise HTTPException(404, "大模型配置不存在")
    data = payload.model_dump(exclude_unset=True)
    if "api_key" in data:
        ak = data.pop("api_key")
        if ak == "":
            row.api_key = None
        elif ak is not None:
            row.api_key = ak.strip()
    for k, v in data.items():
        if v is None and k in ("name", "base_url", "model_name"):
            continue
        if k in ("name", "base_url", "model_name") and isinstance(v, str):
            v = v.strip()
        setattr(row, k, v)
    db.flush()
    if row.is_default:
        clear_other_defaults(db, row.id)
    db.commit()
    db.refresh(row)
    return _to_out(row)


@router.delete("/{provider_id}", status_code=204)
def delete_provider(provider_id: UUID, db: Session = Depends(get_db)):
    row = db.query(LlmProvider).filter(LlmProvider.id == provider_id).first()
    if not row:
        raise HTTPException(404, "大模型配置不存在")
    db.delete(row)
    db.commit()


@router.post("/{provider_id}/set-default", response_model=LlmProviderOut)
def set_default_provider(provider_id: UUID, db: Session = Depends(get_db)):
    row = db.query(LlmProvider).filter(LlmProvider.id == provider_id).first()
    if not row:
        raise HTTPException(404, "大模型配置不存在")
    row.is_default = True
    row.enabled = True
    clear_other_defaults(db, row.id)
    db.commit()
    db.refresh(row)
    return _to_out(row)


class TestImageIn(BaseModel):
    prompt: str = "A simple test image, minimal details"


class TestImageOut(BaseModel):
    data_url: Optional[str] = None
    image_url: Optional[str] = None


@router.post("/{provider_id}/test-image", response_model=TestImageOut)
def test_image_provider(provider_id: UUID, payload: TestImageIn, db: Session = Depends(get_db)):
    """
    对已保存的图片类提供者发一次真实 images/generations 请求，验证联通与鉴权。
    返回 data_url 或 image_url 可直接在前端预览。
    """
    row = db.query(LlmProvider).filter(LlmProvider.id == provider_id).first()
    if not row:
        raise HTTPException(404, "大模型配置不存在")
    if (row.provider_type or "text") != "image":
        raise HTTPException(400, "该提供者不是图片类型（provider_type != 'image'）")

    from app.services.llm_config import normalize_openai_base_url
    base = normalize_openai_base_url(row.base_url).rstrip("/")
    url = f"{base}/images/generations"
    key = (row.api_key or "").strip() or "not-required"

    try:
        with httpx.Client(timeout=120.0, follow_redirects=True) as client:
            resp = client.post(
                url,
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={
                    "model": row.model_name,
                    "prompt": payload.prompt,
                    "n": 1,
                    "size": "1024x1024",
                    "response_format": "b64_json",
                },
            )
    except httpx.TimeoutException:
        raise HTTPException(504, "图片生成超时（>120s）")
    except httpx.ConnectError as e:
        raise HTTPException(502, f"无法连接网关：{e}")

    if resp.status_code >= 400:
        try:
            err = resp.json()
            detail = err.get("error", {}).get("message") or str(err)
        except Exception:
            detail = resp.text[:400]
        raise HTTPException(resp.status_code, f"图片模型错误：{detail}")

    try:
        data = resp.json()
    except Exception:
        raise HTTPException(502, "非 JSON 响应")

    items = data.get("data") or []
    if not items:
        raise HTTPException(502, "未返回图片数据")

    item = items[0]
    if b64 := item.get("b64_json"):
        return TestImageOut(data_url=f"data:image/png;base64,{b64}")
    if img_url := item.get("url"):
        return TestImageOut(image_url=img_url)
    raise HTTPException(502, "返回格式未知")
