"""Bootstrap Fanfic Step 0：同人·番茄立项。"""
from __future__ import annotations

from typing import Any

from app.services.bootstrap.parse import parse_json
from app.services.bootstrap.steps.fanfic._helpers import TROPE_LABELS
from app.services.llm_token_budgets import max_tokens_bootstrap_completion

_TROPE_OPTIONS = "穿书（transmigration）/ 重生（rebirth）/ AU平行（au）"


async def gen_fanfic_positioning(svc: Any, ctx: dict) -> dict:
    meta = ctx.get("fanfic_meta") or {}
    trope = meta.get("fanfic_trope", "transmigration")
    system = (
        "你是有20年番茄同人区运营经验的总编。"
        "读者来同人是为了「磕到原著味+吃到新爽点」，不是看二创作者自嗨。"
        "只返回 JSON，不要解释文字。"
    )
    prompt = f"""同人创意（一句话）：{ctx['logline']}
原著作品名：{meta.get('source_work_title', '')}
用户指定同人类型：{TROPE_LABELS.get(trope, trope)}
主视角/CP（可选）：{meta.get('focal_characters') or '（未指定）'}

原著梗概（作者自填，须尊重，禁止与下列矛盾）：
{(meta.get('canon_synopsis') or '')[:3500]}

可选同人类型（须与用户指定一致，fanfic_trope 填英文键）：
{_TROPE_OPTIONS}

返回 JSON：
{{
  "source_work_title": "原著名（照抄用户填写）",
  "fanfic_trope": "transmigration|rebirth|au 之一，与用户指定一致",
  "fanfic_trope_label": "穿书|重生|AU平行",
  "core_satisfaction": "读者每次更新得到的 ONE 核心爽感（15字内，必须画面感，如：看主角用原著剧情打脸原书反派）",
  "fan_expectation": "原著粉来本书围观什么（20字内）",
  "canon_fidelity": "strict|medium|loose — 对原著设定的贴合档位",
  "platform_tags": ["番茄标签 3-5 个，如：穿书、重生、同人、打脸"],
  "algo_hook": "书架推荐语 50字内：身份+原著梗+爽感预告",
  "ooc_taboos": ["原著粉雷区 2-5 条，如：主角突然圣母/强行洗白反派"],
  "differentiation": "与「只复述原著」相比，本书前3章能感知到的差异（30字内）",
  "taboo_check": "是否触碰番茄违禁或严重OOC风险（是/否+一句说明）"
}}

要求：
1. core_satisfaction 必须可「播放画面」
2. ooc_taboos 必须具体，禁止「不要OOC」这种空话
3. 只返回 JSON"""

    last_err = ""
    for attempt in range(3):
        fix = f"\n【请修正：{last_err}】" if last_err else ""
        raw = await svc._call_with_retry(
            system, prompt + fix,
            max_tokens=max_tokens_bootstrap_completion(),
            task="bootstrap.positioning",
        )
        try:
            data = parse_json(raw)
        except Exception:
            last_err = "JSON 解析失败"
            continue
        if not isinstance(data, dict):
            last_err = "根类型须为 JSON 对象"
            continue
        required = {
            "source_work_title", "fanfic_trope", "core_satisfaction",
            "fan_expectation", "platform_tags", "algo_hook",
        }
        if missing := required - data.keys():
            last_err = f"缺少字段：{missing}"
            continue
        if data.get("fanfic_trope") not in TROPE_LABELS:
            data["fanfic_trope"] = trope
        data["fanfic_trope_label"] = TROPE_LABELS.get(
            data.get("fanfic_trope", trope), data.get("fanfic_trope_label", "")
        )
        if not data.get("source_work_title"):
            data["source_work_title"] = meta.get("source_work_title", "")
        return data
    return {}
