"""
draft_context.py — 起草路由的上下文组装 helpers

拆分结构：
  - draft_ctx_reader.py: 读者模拟反馈 + 复盘指令
  - draft_ctx_promise.py: ReaderPromise 注入 + hook 趋势预警
  - 本文件: Scene 蓝图 + 人物摘要 + 力量体系块 + 叙事弧注入 + re-export

禁止事项：
- 禁止在此模块新增 APIRouter 端点
- 禁止引入 DBSession 之外的副作用
"""
from __future__ import annotations

import json
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from app.models import Character, ChapterIndex, OutlineNode, Scene
from app.routers.ai.text_utils import truncate

if TYPE_CHECKING:
    from app.models import Chapter

# ── re-export：保持外部 import 路径不变 ──────────────────────────
from app.routers.ai.draft_ctx_reader import (  # noqa: F401
    build_reader_feedback_context as _build_reader_feedback_context,
    build_prev_directives as _build_prev_directives,
)
from app.routers.ai.draft_ctx_promise import (  # noqa: F401
    append_hook_trend_warning as _append_hook_trend_warning,
    build_reader_promise_context as _build_reader_promise_context,
)


# ═══════════════════════════════════════════════════════════════
# Scene 蓝图格式化辅助
# ═══════════════════════════════════════════════════════════════

def _build_scene_blueprint(
    db: Session, project_id: str, chapter: "Chapter", outline_node: "OutlineNode | None",
) -> str:
    """
    查询本章对应的 Scene 记录，格式化为结构化分场蓝图文本。

    @returns 格式化后的分场蓝图字符串；无 Scene 记录时返回空字符串。
    """
    scenes: list[Scene] = []

    if outline_node is not None:
        scenes = (
            db.query(Scene).filter(
                Scene.project_id == project_id, Scene.outline_node_id == outline_node.id,
            ).order_by(Scene.order).all()
        )

    if not scenes and chapter.id is not None:
        scenes = (
            db.query(Scene).filter(
                Scene.project_id == project_id, Scene.chapter_id == chapter.id,
            ).order_by(Scene.order).all()
        )

    if not scenes:
        return ""

    char_ids: set = set()
    for sc in scenes:
        if sc.pov_character_id:
            char_ids.add(str(sc.pov_character_id))
        for cid in (sc.characters_on_stage or []):
            char_ids.add(str(cid))

    id_to_name: dict[str, str] = {}
    if char_ids:
        rows = db.query(Character.id, Character.name).filter(Character.id.in_(char_ids)).all()
        id_to_name = {str(r.id): r.name for r in rows}

    total_budget = sum(sc.word_budget or 0 for sc in scenes)
    lines: list[str] = [
        f"【本章分场蓝图（共 {len(scenes)} 场，总预算约 {total_budget} 字）】",
        "严格按此结构逐场写作，每场字数在预算 ±15% 内；每场以钩子收束，串联下一场。", "",
    ]
    pacing_zh = {"fast": "快节奏", "mid": "中节奏", "slow": "慢节奏"}

    for sc in scenes:
        pov_name = id_to_name.get(str(sc.pov_character_id), "") if sc.pov_character_id else ""
        on_stage = [id_to_name.get(str(cid), str(cid)) for cid in (sc.characters_on_stage or [])]
        on_stage_str = "、".join(n for n in on_stage if n) or ""
        pacing_str = pacing_zh.get(sc.pacing or "mid", sc.pacing or "mid")
        hook_stars = "⭐" * min(max(sc.hook_strength or 3, 1), 5)
        budget = sc.word_budget or 400

        scene_lines = [f"▶ 场 {sc.order}｜{sc.title or '（无标题）'}  （预算 {budget} 字，{pacing_str}）"]
        if sc.location_name:
            scene_lines.append(f"  地点：{sc.location_name}")
        if sc.time:
            scene_lines.append(f"  时间：{sc.time}")
        if pov_name:
            scene_lines.append(f"  POV：{pov_name}")
        if on_stage_str:
            scene_lines.append(f"  在场：{on_stage_str}")
        if sc.goal:
            scene_lines.append(f"  目标：{sc.goal}")
        if sc.conflict:
            scene_lines.append(f"  冲突：{sc.conflict}")
        if sc.turn:
            scene_lines.append(f"  转折：{sc.turn}")
        if sc.hook:
            scene_lines.append(f"  钩子：{sc.hook}（强度 {hook_stars}）")
        if sc.sensory_focus and sc.sensory_focus != "mixed":
            sense_zh = {"sight": "视觉", "sound": "听觉", "smell": "嗅觉",
                        "taste": "味觉", "touch": "触觉"}
            scene_lines.append(f"  感官焦点：{sense_zh.get(sc.sensory_focus, sc.sensory_focus)}")
        lines.extend(scene_lines)
        lines.append("")

    return "\n".join(lines).rstrip()


# ═══════════════════════════════════════════════════════════════
# 人物清单与摘要构建
# ═══════════════════════════════════════════════════════════════

def _build_character_summary(
    db: Session, project_id: str, characters: list,
    outline_node, chapter,
) -> tuple[str, list[str]]:
    """构建章节人物摘要字符串与本章人物清单（manifest）。"""
    involved_ids: set = set()
    if outline_node and outline_node.involved_character_ids:
        involved_ids = set(str(cid) for cid in (outline_node.involved_character_ids or []))

    def _char_skill_names(known_skills) -> str:
        if not known_skills:
            return ""
        names = [
            sk.get("skill_name", "") if isinstance(sk, dict) else str(sk)
            for sk in known_skills[:10]
        ]
        return "、".join(n for n in names if n)

    chapter_manifest_names: list[str] = []
    if involved_ids:
        priority = [c for c in characters if str(c.id) in involved_ids]
        display_chars = priority
        chapter_manifest_names = [c.name for c in priority]
    else:
        display_chars = characters

    if not chapter_manifest_names:
        seen: set[str] = set()
        fallback_names: list[str] = []
        for c in characters:
            if not c.name:
                continue
            is_core = c.role in ("protagonist", "antagonist") or (c.character_tier == "core")
            if is_core and c.name not in seen:
                fallback_names.append(c.name)
                seen.add(c.name)

        if chapter.sort_order is not None and chapter.sort_order > 1:
            recent_indexes = (
                db.query(ChapterIndex).filter(
                    ChapterIndex.project_id == project_id,
                    ChapterIndex.chapter_number < chapter.sort_order,
                    ChapterIndex.chapter_number >= max(1, chapter.sort_order - 5),
                ).order_by(ChapterIndex.chapter_number.desc()).all()
            )
            for ci in recent_indexes:
                for fa in (ci.first_appearances or [])[:8]:
                    name = (fa.get("name") if isinstance(fa, dict) else "") or ""
                    name = name.strip()
                    if name and name not in seen:
                        fallback_names.append(name)
                        seen.add(name)
                if len(fallback_names) >= 12:
                    break

        chapter_manifest_names = fallback_names[:12]

    char_lines = []
    for c in display_chars:
        parts = [f"{c.name}（{c.role}"]
        if c.alias:
            parts.append(f"别名:{c.alias}")
        if c.current_realm:
            parts.append(f"境界:{c.current_realm}")
        if c.realm_rank is not None:
            parts.append(f"境界序号:{c.realm_rank}")
        if c.current_location:
            parts.append(f"位置:{c.current_location}")
        if c.current_status and c.current_status != "alive":
            parts.append(f"状态:{c.current_status}")
        skills_str = _char_skill_names(c.known_skills)
        if skills_str:
            parts.append(f"技能:[{skills_str}]")
        parts.append(f"）性格:{(c.personality or '')[:40]}")
        if c.motivation:
            parts.append(f"动机:{truncate(c.motivation, 180)}")
        if c.values:
            parts.append(f"价值观:{truncate(c.values, 180)}")
        if c.fear:
            parts.append(f"恐惧:{truncate(c.fear, 140)}")
        if c.secrets:
            parts.append(f"秘密:{truncate(c.secrets, 180)}")
        if c.known_skills:
            parts.append(f"技能明细:{json.dumps(c.known_skills, ensure_ascii=False)[:1200]}")
        if c.owned_items:
            parts.append(f"持有物:{json.dumps(c.owned_items, ensure_ascii=False)[:1200]}")

        _speech_kit = (c.speech_kit or {}) if isinstance(c.speech_kit, dict) else {}
        if _speech_kit:
            _sig_words = [str(w) for w in (_speech_kit.get("signature_words") or []) if w][:5]
            if _sig_words:
                parts.append(f"标志词:[{'、'.join(_sig_words)}]")
            _samples = [str(s) for s in (_speech_kit.get("sample_dialogues") or []) if s][-3:]
            if _samples:
                parts.append("样本台词:「" + "」｜「".join(_samples) + "」")
            _evo_notes = _speech_kit.get("recent_evolution_notes") or []
            if _evo_notes:
                _latest_evo = str(_evo_notes[-1])[:80]
                if _latest_evo:
                    parts.append(f"近期声音演变:{_latest_evo}")

        _arc_stages = c.arc_stages if isinstance(c.arc_stages, list) else []
        _cur_stage = next(
            (s for s in _arc_stages if isinstance(s, dict) and not s.get("completed")),
            _arc_stages[-1] if _arc_stages else None,
        )
        if _cur_stage and isinstance(_cur_stage, dict):
            _stage_name = (_cur_stage.get("name") or _cur_stage.get("stage") or "").strip()
            _stage_goal = (_cur_stage.get("goal") or _cur_stage.get("description") or "").strip()
            if _stage_name:
                parts.append(f"成长弧:[{_stage_name}]{f'({_stage_goal[:50]})' if _stage_goal else ''}")
        char_lines.append("".join(parts))

    return "\n".join(char_lines), chapter_manifest_names


# ═══════════════════════════════════════════════════════════════
# 多轴力量体系（写章注入）
# ═══════════════════════════════════════════════════════════════

def build_power_systems_draft_block(db: "Session", project_id: str) -> str:
    """写章路径统一力量体系块（多轴 registry + 道心 + 天地法则）。"""
    from app.services.bootstrap.power_registry import build_draft_power_context_from_db
    return build_draft_power_context_from_db(db, project_id)


# ═══════════════════════════════════════════════════════════════
# 情绪节律 + 反派行动线注入
# ═══════════════════════════════════════════════════════════════

def _build_narrative_arc_context(
    project_extra: dict, outline_node: "OutlineNode | None",
    db: "Session | None" = None,
) -> str:
    """
    从 ``Project.extra`` 中取出当前卷对应的 emotion_arc 和 villain_arc，
    格式化为写章硬约束文本块。

    @param project_extra: ``Project.extra`` 字典
    @param outline_node: 当前章节的 OutlineNode（可为 None）
    @param db: SQLAlchemy Session（解析父卷时使用）
    @returns 格式化文本块；无数据时返回空字符串
    """
    if not isinstance(project_extra, dict):
        return ""

    emotion_arc: list = project_extra.get("emotion_arc") or []
    villain_arc: list = project_extra.get("villain_arc") or []
    if not emotion_arc and not villain_arc:
        return ""

    # ── 确定当前卷索引 ──
    vol_index: int | None = None
    if outline_node is not None:
        _extra_vi = (outline_node.extra or {}).get("vol_index")
        if isinstance(_extra_vi, int):
            vol_index = _extra_vi
        if vol_index is None and db is not None and outline_node.parent_id is not None:
            try:
                vol_node = db.query(OutlineNode).filter(
                    OutlineNode.id == outline_node.parent_id
                ).first()
                if vol_node is not None and vol_node.sort_order is not None:
                    vol_index = int(vol_node.sort_order)
            except Exception:
                pass
    if vol_index is None:
        vol_index = 0

    def _find_by_vol(arc_list: list, idx: int) -> dict | None:
        if not arc_list:
            return None
        exact = next((v for v in arc_list if isinstance(v, dict) and v.get("vol_index") == idx), None)
        if exact:
            return exact
        by_order = next((v for v in arc_list if isinstance(v, dict) and v.get("sort_order") == idx), None)
        if by_order:
            return by_order
        return arc_list[0] if isinstance(arc_list[0], dict) else None

    cur_emotion = _find_by_vol(emotion_arc, vol_index)
    cur_villain = _find_by_vol(villain_arc, vol_index)
    if cur_emotion is None and cur_villain is None:
        return ""

    lines: list[str] = ["【本卷叙事规划约束（写章必须贯彻，禁止随意突破）】"]

    if cur_emotion:
        tone = (cur_emotion.get("tone") or cur_emotion.get("main_tone") or "").strip()
        deposit = (cur_emotion.get("deposit") or cur_emotion.get("accumulate") or "").strip()
        withdraw = (cur_emotion.get("withdraw") or cur_emotion.get("release") or "").strip()
        net_balance = (cur_emotion.get("net_balance") or cur_emotion.get("balance") or "").strip()

        lines.append("▎情绪节律（情感账户状态）")
        if tone:
            lines.append(f"  当前卷基调：{tone}")
        if deposit:
            lines.append(f"  情绪储量（压抑蓄积）：{truncate(deposit, 120)}")
        if withdraw:
            lines.append(f"  释放节点：{truncate(withdraw, 120)}")
        if net_balance:
            lines.append(f"  净余额走向：{truncate(net_balance, 120)}")
        if tone and ("克制" in tone or "蓄力" in tone or "压抑" in tone):
            lines.append(
                "  ⚠️ 硬约束：本卷处于情绪蓄力阶段，禁止提前引爆大爽点；"
                "本章以压迫、积累、暗流为主，高光瞬间控制在小规模，为后续卷保留爆发空间。"
            )
        elif tone and ("释放" in tone or "爆发" in tone or "高潮" in tone):
            lines.append(
                "  ✅ 约束：本卷处于情绪释放阶段，可安排显著爽点，但需同时埋下下一轮蓄力种子。"
            )

    if cur_villain:
        villain_name = (cur_villain.get("villain") or cur_villain.get("name") or "").strip()
        desire = (cur_villain.get("desire") or cur_villain.get("goal") or "").strip()
        obstacle = (cur_villain.get("obstacle") or "").strip()
        choice = (cur_villain.get("choice") or cur_villain.get("action") or "").strip()
        cost = (cur_villain.get("cost") or cur_villain.get("price") or "").strip()
        blind_spot = (cur_villain.get("blind_spot") or cur_villain.get("weakness") or "").strip()

        name_label = f"反派【{villain_name}】" if villain_name else "反派"
        lines.append(f"▎{name_label}本卷行动逻辑")
        if desire:
            lines.append(f"  欲望/目标：{truncate(desire, 100)}")
        if obstacle:
            lines.append(f"  当前障碍：{truncate(obstacle, 100)}")
        if choice:
            lines.append(f"  采取手段：{truncate(choice, 120)}")
        if cost:
            lines.append(f"  付出代价：{truncate(cost, 100)}")
        if blind_spot:
            lines.append(f"  ⚠️ 盲点（AI 写反派时严禁越过此边界）：{truncate(blind_spot, 160)}")
        lines.append(
            "  写反派台词/行动时必须符合以上逻辑，"
            "不得让反派表现出对其盲点已知悉或提前防范的迹象。"
        )

    return "\n".join(lines)
