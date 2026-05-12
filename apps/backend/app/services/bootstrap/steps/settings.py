"""Bootstrap Step 8：世界观设定卡（含蓝图批次与追加模式）。"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional

from app.models import Project, WorldSetting
from app.services.bootstrap.context import get_genre_kit_block
from app.services.bootstrap.parse import parse_json
from app.services.bootstrap.prompts import (
    GEMINI_SETTING_BLUEPRINTS,
    SETTING_CARD_SCHEMA_BRIEF,
    setting_extra_with_defaults,
)
from app.services.llm_token_budgets import max_tokens_bootstrap_completion

_logger = logging.getLogger(__name__)


async def gen_settings(
    svc: Any,
    project: Project,
    ctx: dict,
    *,
    blueprints: Optional[list] = None,
    prompt_addon: str = "",
):
    """生成纯叙事设定卡；默认按蓝图分批并行调用 AI。"""
    _SETTINGS_BATCH_SIZE = 6
    _BATCH_MAX_TOKENS = 8192

    bps = blueprints if blueprints is not None else GEMINI_SETTING_BLUEPRINTS
    batches = [bps[i:i + _SETTINGS_BATCH_SIZE] for i in range(0, len(bps), _SETTINGS_BATCH_SIZE)]

    faction_brief = ctx.get("faction_summary", "（已独立生成势力档案）")
    power_brief = ctx.get("power_summary", "（已独立生成境界体系）")
    char_names_hint = "、".join(ctx.get("char_names", []))
    faction_names_hint = "、".join(ctx.get("faction_names", []))
    kit_block = get_genre_kit_block(ctx)
    extra_block = f"\n{prompt_addon.strip()}\n" if (prompt_addon or "").strip() else ""

    async def _call_batch(batch: list, batch_idx: int) -> list:
        batch_json = json.dumps(batch, ensure_ascii=False, indent=2)
        prompt = f"""{kit_block}小说：《{ctx['project_title']}》({ctx['genre']})
创意：{ctx['logline']}
立意与类型：{ctx.get('premise', '')[:1000] or '（未填写，请自动提炼）'}
世界观：{ctx['world_overview'][:300]}

【流派编辑手册约束】
- 世界观必须体现流派特有的力量体系、势力格局、社会规则和读者期待（例：玄幻要强调金手指代价与升级仪式，悬疑要强调信息差与嫌疑人布局）
- 禁忌边界必须参考 genre_kit 的 forbidden_examples

已独立生成的结构化数据（设定卡不要重复这些内容）：
- 境界体系：{power_brief}
- 势力档案：{faction_brief}
- 已确定人物（写 who_knows_now 时必须从此列表选名字）：{char_names_hint or '（尚未生成）'}
- 已确定势力（写 who_knows_now 时可引用）：{faction_names_hint or '（尚未生成）'}

请严格按【世界设定蓝图（第{batch_idx + 1}批）】生成全部 {len(batch)} 张设定卡，不要少卡、不要合并卡。
世界设定蓝图（本批）：
{batch_json}

{SETTING_CARD_SCHEMA_BRIEF}

要求：
1) 必须生成本批蓝图中的全部 {len(batch)} 张设定卡，顺序与蓝图一致
2) 每张卡 title/category/tags/importance/stage 必须与蓝图一致，写入 extra
3) section=core 的卡必须填写 extra.core 的全部字段
4) section=focus 的卡必须填写 extra.focus 的全部字段
5) 每张卡 content 至少180字，有可落地的名词、规则、代价、例外和冲突
6) 不要重复已有的境界体系或势力信息
7) 每张卡 extra 含 reveal_timing、who_knows_now（规则见上 schema 说明）
{extra_block}
只返回JSON数组，不要解释。"""

        raw = await svc._call_with_retry(
            "你是网络小说世界观设计专家。只返回JSON数组。",
            prompt,
            max_tokens=_BATCH_MAX_TOKENS,
            task="bootstrap.settings",
        )
        data = parse_json(raw)
        if not isinstance(data, list):
            data = data.get("settings", [])
        return data

    batch_results = await asyncio.gather(
        *[_call_batch(b, i) for i, b in enumerate(batches)],
        return_exceptions=True,
    )

    results = []
    for i, batch_data in enumerate(batch_results):
        if isinstance(batch_data, BaseException):
            _logger.warning("settings 第%d批生成失败，已跳过：%s", i + 1, batch_data)
            continue
        for item in batch_data:
            extra = setting_extra_with_defaults(item)
            s = WorldSetting(
                project_id=project.id,
                title=item.get("title", "设定"),
                content=item.get("content", ""),
                tags=item.get("tags", []),
                extra=extra,
            )
            svc.db.add(s)
            results.append(s)

    svc.db.commit()
    ctx["settings_summary"] = " | ".join(
        f"{s.title}：{(s.content or '')[:80]}" for s in results
    )
    return results


async def gen_settings_append(svc: Any, project: Project, ctx: dict, *, user_hint: str, count: int):
    """在已有设定基础上追加若干张自拟标题的纯叙事设定卡。"""
    system = "你是网络小说世界观设计专家。只返回JSON数组。"
    existing = (
        svc.db.query(WorldSetting)
        .filter(WorldSetting.project_id == project.id)
        .order_by(WorldSetting.created_at)
        .all()
    )
    existing_titles = [(s.title or "").strip() for s in existing if (s.title or "").strip()]
    brief = " | ".join(f"{s.title}：{(s.content or '')[:80]}" for s in existing[:20])

    char_names_hint = "、".join(ctx.get("char_names", []))
    faction_names_hint = "、".join(ctx.get("faction_names", []))
    kit_block = get_genre_kit_block(ctx)

    prompt = f"""{kit_block}小说：《{ctx['project_title']}》({ctx['genre']})
创意：{ctx['logline']}
立意与类型：{ctx.get('premise', '')[:1000] or '（未填写，请自动提炼）'}
世界观：{ctx['world_overview'][:400]}

已独立生成的结构化数据（不要整段复制成档案，仅作叙事参照）：
- 境界体系：{ctx.get('power_summary', '')}
- 势力档案：{ctx.get('faction_summary', '')}

【已有设定卡标题】（禁止重复或仅改一字的近似重名；内容可与旧卡互补但不要逐句复述）
{json.dumps(existing_titles, ensure_ascii=False)}

已有设定摘要（防撞车）：
{brief[:2400]}

【追加需求】
{user_hint}

请再生成恰好 {count} 张新的「纯叙事型」世界观设定卡。标题自拟，须与已有标题明显不同。
分类的 extra.category 必须是以下之一：世界背景、地理场景、历史传说、文化风俗、规则法则、其他。
尽量覆盖至少 3 种不同分类。
每张卡须含：title, content（≥160字）, tags（数组）, extra。
extra 须含 category、importance（core/major/flavor）、stage（early/mid/late/full）、
reveal_timing、who_knows_now（须优先使用真实人物名与势力名：人物 {char_names_hint or '无'}；势力 {faction_names_hint or '无'}；若确实无人则写「佚名路人/地方商会」等具体群体，禁用「主角」「反派」泛称）。
每张为 focus 型：extra.focus 必填 summary, story_function, conflict_seed, cost_or_risk, affected_people, exception_or_loophole, visual_anchor（各一句，可落地）。
只返回JSON数组，不要解释。"""

    raw = await svc._call_with_retry(
        system,
        prompt,
        max_tokens=max_tokens_bootstrap_completion(),
        task="bootstrap.settings",
    )
    data = parse_json(raw)
    if not isinstance(data, list):
        data = data.get("settings", [])
    results = []
    for item in data:
        extra = setting_extra_with_defaults(item)
        s = WorldSetting(
            project_id=project.id,
            title=item.get("title", "追加设定"),
            content=item.get("content", ""),
            tags=item.get("tags", []) if isinstance(item.get("tags"), list) else [],
            extra=extra,
        )
        svc.db.add(s)
        results.append(s)
    svc.db.commit()
    prev = ctx.get("settings_summary") or ""
    new_bits = " | ".join(f"{s.title}：{(s.content or '')[:80]}" for s in results)
    ctx["settings_summary"] = (prev + " | " + new_bits).strip(" |")
    return results
