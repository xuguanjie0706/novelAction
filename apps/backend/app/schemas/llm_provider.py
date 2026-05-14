from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class LlmProviderBase(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    name: str = Field(..., max_length=200)
    base_url: str = Field(..., max_length=2000)
    model_name: str = Field(..., max_length=200)
    # text = 文本生成（默认）；image = 图片生成（兼容 /v1/images/generations）
    provider_type: str = Field("text", pattern=r"^(text|image)$")
    # 计费档位：heavy（高端大模型）/ standard（中端，默认）/ light（本地/免费，cost=0）
    # 由管理员显式设置，无需依赖模型名关键词猜测，支持任意自定义 API 网关。
    tier: str = Field("standard", pattern=r"^(heavy|standard|light)$")
    enabled: bool = True
    is_default: bool = False
    sort_order: int = 0


class LlmProviderCreate(LlmProviderBase):
    """新建时可传 api_key；留空表示无密钥（部分免费网关）。"""
    api_key: Optional[str] = None


class LlmProviderUpdate(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    name: Optional[str] = Field(None, max_length=200)
    base_url: Optional[str] = Field(None, max_length=2000)
    model_name: Optional[str] = Field(None, max_length=200)
    provider_type: Optional[str] = Field(None, pattern=r"^(text|image)$")
    tier: Optional[str] = Field(None, pattern=r"^(heavy|standard|light)$")
    api_key: Optional[str] = None
    """传 null 或不传表示不改；传空字符串表示清空密钥"""
    enabled: Optional[bool] = None
    is_default: Optional[bool] = None
    sort_order: Optional[int] = None


class LlmProviderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: UUID
    name: str
    base_url: str
    model_name: str
    provider_type: str = "text"
    tier: str = "standard"
    has_api_key: bool
    api_key_hint: Optional[str] = None
    enabled: bool
    is_default: bool
    sort_order: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class LlmTestConnectionIn(BaseModel):
    """临时测试：不要求已入库。"""

    model_config = ConfigDict(protected_namespaces=())

    base_url: str = Field(..., max_length=2000)
    model_name: str = Field(..., max_length=200)
    api_key: Optional[str] = Field(None, max_length=4000)


class LlmTestConnectionOut(BaseModel):
    ok: bool
    message: str
    latency_ms: Optional[int] = None
    http_status: Optional[int] = None


def mask_api_key_hint(raw: Optional[str]) -> tuple[bool, Optional[str]]:
    """是否有密钥 + 末尾提示（不脱敏全文）。"""
    if not raw or not raw.strip():
        return False, None
    s = raw.strip()
    tail = s[-4:] if len(s) >= 4 else s
    return True, f"…{tail}"
