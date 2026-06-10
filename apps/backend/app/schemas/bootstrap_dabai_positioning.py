"""mode=dabai 立项定位校验 — 先归一化为通用字段再复用 BootstrapPositioning。"""
from __future__ import annotations

from app.schemas.bootstrap_positioning import try_validate_positioning
from app.services.bootstrap.prompts.dabai_prompts import dabai_to_generic_positioning


def try_validate_dabai_positioning(
    data: dict,
    *,
    benchmark: dict | None = None,
) -> tuple[dict | None, str | None]:
    """dabai 立项 gate / auto_mode resume 用；保留 dabai 扩展字段。"""
    if not isinstance(data, dict) or not data:
        return None, "缺少有效的 positioning"
    normalized = dabai_to_generic_positioning(data, benchmark=benchmark)
    validated, err = try_validate_positioning(normalized)
    if err or validated is None:
        return None, err
    merged = {**data, **validated}
    merged["bootstrap_mode"] = "dabai"
    merged.setdefault("writing_style", "plain")
    return merged, None
