"""建书前：根据原著名与同人创意，一次 LLM 生成 3 条原著梗概候选。"""
from __future__ import annotations

from typing import Any

from app.services.bootstrap.parse import parse_json
from app.services.bootstrap.steps.fanfic._helpers import TROPE_LABELS
from app.services.llm_token_budgets import max_tokens_bootstrap_completion

_MIN_SYNOPSIS_LEN = 80
_OPTION_COUNT = 3


def _build_prompt(
    *,
    source_work_title: str,
    logline: str,
    fanfic_trope: str,
    focal_characters: str,
) -> tuple[str, str]:
    trope_label = TROPE_LABELS.get(fanfic_trope, fanfic_trope)
    system = (
        "你是熟悉网文与同人创作的编辑。"
        "根据作品名与公开常识，撰写原著梗概要点（非逐字摘抄版权原文）。"
        "只返回 JSON，不要解释文字。"
    )
    focal = focal_characters.strip() or "（未指定）"
    prompt = f"""原著名：{source_work_title}
同人创意（一句话）：{logline.strip() or "（未填）"}
同人类型：{trope_label}
主视角/CP（可选）：{focal}

请基于你对该作品的公开认知，生成 {_OPTION_COUNT} 条**不同侧重点**的原著梗概候选，供作者选一条作为后续同人规划的「原著约束」。

每条梗概须：
- 不少于 {_MIN_SYNOPSIS_LEN} 个汉字
- 覆盖：世界观/时代背景、主要势力或阵营、核心力量体系（若有）、主线矛盾或结局走向、2～4 个关键人物及其关系
- 三条之间侧重点须明显不同，例如：①主线时间线全景 ②人物关系与感情线 ③力量体系与关键节点
- 禁止大段照搬原文台词；禁止声称「已阅读全书原文」；若作品较冷门，可据书名合理推断并标注「据公开资料」

返回 JSON（根对象）：
{{
  "options": [
    {{"label": "10字内侧写标签，如「主线脉络」", "synopsis": "梗概正文…"}},
    …共 {_OPTION_COUNT} 条
  ]
}}

只返回 JSON。"""
    return system, prompt


def _normalize_options(raw: list[Any]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for i, item in enumerate(raw[: _OPTION_COUNT + 2]):
        if not isinstance(item, dict):
            continue
        synopsis = str(item.get("synopsis") or "").strip()
        if len(synopsis) < _MIN_SYNOPSIS_LEN:
            continue
        label = str(item.get("label") or f"候选{i + 1}").strip() or f"候选{i + 1}"
        out.append({"id": f"opt_{len(out) + 1}", "label": label[:20], "synopsis": synopsis})
        if len(out) >= _OPTION_COUNT:
            break
    return out


async def gen_canon_synopsis_options(
    svc: Any,
    *,
    source_work_title: str,
    logline: str = "",
    fanfic_trope: str = "transmigration",
    focal_characters: str = "",
) -> list[dict[str, str]]:
    """一次 LLM 调用，返回 3 条可被选中的原著梗概候选。"""
    title = source_work_title.strip()
    if not title:
        raise ValueError("原著名不能为空")

    system, prompt = _build_prompt(
        source_work_title=title,
        logline=logline,
        fanfic_trope=fanfic_trope,
        focal_characters=focal_characters,
    )

    last_err = ""
    for attempt in range(3):
        fix = f"\n【请修正：{last_err}】" if last_err else ""
        raw = await svc._call_with_retry(
            system,
            prompt + fix,
            max_tokens=max_tokens_bootstrap_completion(),
            task="bootstrap.fanfic_synopsis",
        )
        try:
            data = parse_json(raw)
        except Exception:
            last_err = "JSON 解析失败"
            continue
        if not isinstance(data, dict):
            last_err = "根类型须为 JSON 对象"
            continue
        options_raw = data.get("options")
        if not isinstance(options_raw, list):
            last_err = "缺少 options 数组"
            continue
        normalized = _normalize_options(options_raw)
        if len(normalized) < _OPTION_COUNT:
            last_err = f"有效梗概不足 {_OPTION_COUNT} 条（每条至少 {_MIN_SYNOPSIS_LEN} 字）"
            continue
        return normalized[:_OPTION_COUNT]

    raise RuntimeError(last_err or "梗概生成失败")
