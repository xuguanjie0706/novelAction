"""
gated_draft_quality.py — 门控写作质检辅助函数

资源边界：
  本模块封装质量门控循环中与**质检**相关的三个函数：
  - _run_quality_check_inline  — 内联执行质检（不走 HTTP），写结果到 DB
  - _check_passed              — 根据门槛判断质检是否通过
  - _build_rewrite_prompt      — 根据质检结果构造重写指令块

  端点主逻辑仍在 gated_draft_routes.py；上下文/存库 helpers 在 gated_draft_helpers.py。
"""
from __future__ import annotations

import textwrap

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import (
    Chapter,
    Character,
    MemoryChunk,
    OutlineNode,
    PowerSystem,
    Project,
    StoryLine,
    WorldSetting,
)
from app.routers.ai.context import (
    build_chapter_index_context,
    build_continuity_context,
    build_plot_dossier_context,
    format_world_setting_context,
)
from app.routers.ai.quality_debt import sync_quality_debts
from app.services.bootstrap.power_registry import build_draft_power_context_from_db
from app.services.ai_service import AIService


async def _run_quality_check_inline(
    db: Session,
    chapter: Chapter,
    project: Project,
    project_id: str,
    svc: AIService,
) -> dict:
    """
    在 gated 循环中内联执行质检，不走 HTTP 路由。

    复用 AIService.quality_check；上下文组装与 quality_routes 保持一致。

    @param db: SQLAlchemy Session
    @param chapter: 已保存最新内容的 Chapter 对象
    @param project: Project 对象
    @param project_id: 项目 UUID 字符串
    @param svc: 已初始化的 AIService 实例
    @returns quality_check 返回的 dict（含 overall_score / dimensions / suggestions / issues）
    @raises Exception: AI 调用失败时向上抛出
    """
    memory_query = (
        db.query(MemoryChunk)
        .outerjoin(Chapter, Chapter.id == MemoryChunk.chapter_id)
        .filter(MemoryChunk.project_id == project_id)
        .order_by(func.coalesce(Chapter.sort_order, MemoryChunk.chapter_number, 0).asc())
    )
    memories = memory_query.limit(200).all()

    settings = db.query(WorldSetting).filter(
        WorldSetting.project_id == project_id
    ).all()

    characters = db.query(Character).filter(
        Character.project_id == project_id
    ).all()

    def _skill_names(known_skills) -> str:
        if not known_skills:
            return "无"
        names = [
            sk.get("skill_name", "") if isinstance(sk, dict) else str(sk)
            for sk in known_skills[:5]
        ]
        return "、".join(n for n in names if n) or "无"

    character_states = [
        f"{c.name}：境界={c.current_realm or '未知'}，"
        f"位置={c.current_location or '未知'}，"
        f"状态={c.current_status or 'alive'}，"
        f"已知技能=[{_skill_names(c.known_skills)}]"
        for c in characters
    ]

    from app.services.ai.storyline_weave_engine import query_storyline_weave_context_block

    outline_nid = str(chapter.outline_node_id) if chapter.outline_node_id else None
    ch_no = chapter.sort_order or 0
    weave_block = query_storyline_weave_context_block(
        db, project_id, [], ch_no, outline_node_id=outline_nid,
    )
    if weave_block:
        storylines_context = [weave_block]
    else:
        active_storylines = db.query(StoryLine).filter(
            StoryLine.project_id == project_id,
            StoryLine.status.in_(["active", "climax"]),
        ).all()
        storylines_context = [
            f"{s.name}（{s.line_type}，{s.status}）：{s.core_conflict or s.description or ''}"
            for s in active_storylines
        ]

    power_systems_summary = [build_draft_power_context_from_db(db, project_id)]

    # 大纲上下文
    outline_context = ""
    node: OutlineNode | None = None
    if chapter.outline_node_id:
        node = db.query(OutlineNode).filter(OutlineNode.id == chapter.outline_node_id).first()
        if node:
            parts = []
            if node.summary:
                parts.append(f"本章摘要：{node.summary}")
            if node.hook:
                parts.append(f"开篇钩子：{node.hook}")
            if node.conflict:
                parts.append(f"核心冲突：{node.conflict}")
            if node.highlight:
                parts.append(f"章末方向：{node.highlight}")
            if node.power_milestone:
                parts.append(f"实力里程碑：{node.power_milestone}")
            if node.emotional_tone:
                parts.append(f"情感基调：{node.emotional_tone}")
            if node.foreshadows_laid:
                foreshadow_descs = [
                    f.get("description", "") if isinstance(f, dict) else str(f)
                    for f in node.foreshadows_laid[:3]
                ]
                parts.append(f"本章埋下伏笔：{'；'.join(foreshadow_descs)}")
            outline_context = "；".join(parts)

    continuity_ctx = build_continuity_context(
        db=db, project_id=project_id, chapter=chapter, outline_node=node,
    )
    chapter_index_ctx = build_chapter_index_context(
        db=db, project_id=project_id, chapter=chapter,
    )
    plot_dossier_ctx = build_plot_dossier_context(
        db=db, project_id=project_id, chapter=chapter,
    )

    check_types = [
        "plot", "character", "setting_consistency", "pacing",
        "hooks", "outline_alignment", "face_slap_payoff",
        "emotional_resonance", "subscribe_intent",
    ]

    result = await svc.quality_check(
        chapter_content=chapter.content,
        chapter_title=chapter.title,
        memories=[m.content for m in memories],
        settings_summary=[
            format_world_setting_context(s, content_limit=2400)
            for s in settings
        ],
        check_types=check_types,
        character_states=character_states,
        storylines_context=storylines_context,
        power_systems_summary=power_systems_summary,
        outline_context=outline_context,
        continuity_context=continuity_ctx,
        chapter_index_context=chapter_index_ctx,
        plot_dossier_context=plot_dossier_ctx,
    )

    # 写库（复用 quality_routes 逻辑）
    chapter.last_quality_score = result.get("overall_score")
    chapter.last_quality_report = result
    chapter.quality_checked_at = func.now()
    sync_quality_debts(db, project_id, chapter, result)
    db.commit()
    db.refresh(chapter)

    return result


def _check_passed(
    qc_result: dict,
    cfg: dict,
    *,
    hook_mandate_active: bool = False,
) -> tuple[bool, list[str]]:
    """
    判断质检是否通过门槛，返回 (passed, failing_dimension_names)。

    当 auto_quality_gate=False 时：质检结果仍会推送给前端供参考，
    但不触发重写循环（始终视为通过），避免只开预警却被强制重写。

    当 ``enforce_face_slap_payoff_when_hook_required`` 为真且本章为爽点结算章
    （与 ``_calc_hook_requirement`` 注入硬约束同判）时，额外要求
    ``face_slap_payoff`` 维度分数 ≥ ``min_face_slap_payoff_score``。

    @param qc_result: quality_check 返回的完整结果 dict
    @param cfg: 生效的 writing_config dict（需含 auto_quality_gate 键）
    @param hook_mandate_active: 本章是否适用爽点硬约束（结算章/高潮期）
    @returns (True, []) 若通过；(False, [...]) 列出未达标维度名
    """
    # auto_quality_gate 关闭时：仅做信息性质检，不触发重写
    if not cfg.get("auto_quality_gate", True):
        return (True, [])

    overall = float(qc_result.get("overall_score") or 0)
    dims = qc_result.get("dimensions") or {}
    subscribe_intent = float((dims.get("subscribe_intent") or {}).get("score") or 0)

    failing: list[str] = []
    if overall < cfg["min_overall_score"]:
        failing.append(f"overall_score({overall:.1f}<{cfg['min_overall_score']})")
    if subscribe_intent < cfg["min_subscribe_intent"]:
        failing.append(f"subscribe_intent({subscribe_intent:.1f}<{cfg['min_subscribe_intent']})")

    if hook_mandate_active and cfg.get("enforce_face_slap_payoff_when_hook_required"):
        min_fs = float(cfg.get("min_face_slap_payoff_score") or 6.0)
        fs = float((dims.get("face_slap_payoff") or {}).get("score") or 0)
        if fs < min_fs:
            failing.append(f"face_slap_payoff({fs:.1f}<{min_fs}，本章为爽点结算/高潮硬约束章)")

    return (len(failing) == 0), failing


def _build_rewrite_prompt(
    qc_result: dict,
    user_prompt: str,
    strategy: str,
    attempt: int,
) -> str:
    """
    根据质检结果与重写策略，构造注入起笔 user_prompt 的修复指令块。

    策略：
      - "patch"        ：定点修复失分区域，保留通过维度的内容结构
      - "full_rewrite" ：全量重写，所有建议作为硬约束，温度更高

    @param qc_result: 上轮质检结果
    @param user_prompt: 原始用户 prompt（透传，保留作者意图）
    @param strategy: "patch" | "full_rewrite"
    @param attempt: 当前尝试轮次（第几次重写）
    @returns 拼接后的完整 user_prompt 字符串
    """
    dims = qc_result.get("dimensions") or {}
    suggestions = qc_result.get("suggestions") or []
    issues = qc_result.get("issues") or []
    overall = qc_result.get("overall_score", 0)

    # 找出失分维度（< 7 视为需要改进）
    weak_dims = [
        f"{k}（{v.get('score', '?')}分）：{v.get('comment', '')}"
        for k, v in dims.items()
        if isinstance(v, dict) and float(v.get("score") or 10) < 7
    ]

    # 找出较好维度（≥ 8 分）
    strong_dims = [k for k, v in dims.items() if isinstance(v, dict) and float(v.get("score") or 0) >= 8]

    # 按失分维度从建议列表里抽出最相关的那几条（匹配维度英文/中文关键词）
    def _pick_dim_suggestions(weak_dim_keys: list[str], all_suggestions: list[str]) -> list[str]:
        dim_keywords = {
            "plot": ["情节", "剧情", "推进"],
            "character": ["人物", "角色", "动机", "性格"],
            "setting_consistency": ["境界", "位置", "设定", "一致"],
            "pacing": ["节奏", "拖沓", "仓促"],
            "hooks": ["钩子", "悬念", "章末"],
            "outline_alignment": ["大纲", "目标"],
            "face_slap_payoff": ["打脸", "爽点", "兑现"],
            "emotional_resonance": ["情感", "揪心", "共鸣"],
            "subscribe_intent": ["追读", "订阅", "翻页"],
        }
        matched: list[str] = []
        seen_idx: set[int] = set()
        for dk in weak_dim_keys:
            for kw in dim_keywords.get(dk, [dk]):
                for i, s in enumerate(all_suggestions):
                    if i in seen_idx:
                        continue
                    if kw in s:
                        matched.append(s)
                        seen_idx.add(i)
        # 补足：失分维度相关建议不足 3 条时，按顺序补
        for i, s in enumerate(all_suggestions):
            if len(matched) >= 4:
                break
            if i not in seen_idx:
                matched.append(s)
                seen_idx.add(i)
        return matched[:4]

    if strategy == "patch":
        weak_dim_keys = [k for k, v in dims.items() if isinstance(v, dict) and float(v.get("score") or 10) < 7]
        targeted_suggestions = _pick_dim_suggestions(weak_dim_keys, suggestions)
        block = textwrap.dedent(f"""

        ===【质量门控 · 第{attempt}轮 · 定点修复 PATCH】===
        上轮整体得分：{overall}/10，未达门槛。本轮只修**失分维度**，其余结构**原样保留**。

        ▍失分维度（本轮唯一修复目标）：
        {chr(10).join(f"  • {d}" for d in weak_dims) if weak_dims else "  （无明显失分维度，仅做章末钩子强化）"}

        ▍针对失分维度的具体修复项（本轮只落实这几条，不要额外发挥）：
        {chr(10).join(f"  {i+1}. {s}" for i, s in enumerate(targeted_suggestions)) if targeted_suggestions else "  （无定向建议，按失分描述微调）"}

        ▍一致性/钩子问题：
        {chr(10).join(f"  • {iss.get('description', '')}" for iss in issues[:3]) if issues else "  （无）"}

        ▍强维度（禁止触动）：{', '.join(strong_dims) if strong_dims else '无'}
        这些维度所在段落的人物对白/场景动作/世界观细节**逐字保留或等义改写**，不要重新构思。

        PATCH 约束：
        - 修改范围控制在失分段落；强维度段落的字句结构保持稳定
        - 保持与上一轮相同的 POV、叙事节奏、人物口吻
        - 章末钩子段落若在失分维度中，必须重写；否则保留
        - 禁止在本轮引入新主线、新角色、新伏笔
        ===
        """)
    else:  # full_rewrite
        block = textwrap.dedent(f"""

        ===【质量门控 · 第{attempt}轮 · 全量重写 FULL REWRITE】===
        ⚠️ 上轮得分 {overall}/10，前几轮定点修复均未达标。
        **本轮请彻底重构本章结构**，允许推翻上一版的场景顺序、POV 切换点、章末钩子设计。

        ▍必须解决的全部问题：
        {chr(10).join(f"  • {iss.get('description', '')}" for iss in issues[:6]) if issues else "  （无具体问题，请整体重构）"}

        ▍全部编辑建议（每一条都须在正文中有对应落地）：
        {chr(10).join(f"  {i+1}. {s}" for i, s in enumerate(suggestions[:10]))}

        ▍重构硬约束：
        - 章末最后一段必须是强钩子：悬念揭开/爽感兑现/伏笔引爆——不得以角色思考或旁白收尾
        - 人物境界/位置/持有物/已习得技能必须与【情节档案】完全吻合
        - 打脸/爽点以具体场景动作落地（动作+表情+台词），不可用「众人哗然」「场面寂静」等概括词带过
        - 允许调整分场顺序与详略分布，但必须服务于本章大纲的核心事件
        - 不得扩写为两章；正文总字数控制在大纲预算 ±15% 内
        ===
        """)

    base = (user_prompt or "").strip()
    return (base + block).strip()
