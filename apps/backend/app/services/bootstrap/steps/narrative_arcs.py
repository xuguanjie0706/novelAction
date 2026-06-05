"""Bootstrap Step 9.5+9.8 合并：情绪节律图 + 反派行动线（一次 LLM 调用）。

设计动机（2026-06）
------------------
两步同属「总编辑卷级叙事规划」：输入同为卷骨架 + 立项定位，采样档相同，
原先并行两次调用重复发送 ~1.3k 输入 token。合并后 AI 可对齐
「本卷情绪基调 ↔ 反派胜败格局」，产物仍分别写入 extra 键，下游无感。
单步 regen 仍走 ``gen_emotion_arc`` / ``gen_villain_arc``。
"""
from __future__ import annotations

from typing import Any

from app.services.bootstrap.narrative_arc_gen import (
    apply_ladder_boss_names,
    call_json_object_with_retry,
    merge_project_extra_fields,
    write_emotion_arc_ctx,
    write_villain_arc_ctx,
)

_TASK = "bootstrap.narrative_arcs"


def _validate_narrative_arcs(data: Any) -> tuple[list[dict], list[dict], str | None]:
    if not isinstance(data, dict):
        return [], [], "须为 JSON 对象"
    emotion = data.get("emotion_arc")
    villain = data.get("villain_arc")
    if not isinstance(emotion, list) or not emotion:
        return [], [], "emotion_arc 须为非空数组"
    if not isinstance(villain, list) or not villain:
        return [], [], "villain_arc 须为非空数组"
    em_rows = [r for r in emotion if isinstance(r, dict)]
    vil_rows = [r for r in villain if isinstance(r, dict)]
    if len(em_rows) < 1 or len(vil_rows) < 1:
        return [], [], "两个数组均须至少含 1 条有效对象"
    return em_rows, vil_rows, None


async def gen_narrative_arcs(
    svc: Any,
    project,
    ctx: dict,
    *,
    persist: bool = True,
) -> tuple[list[dict], list[dict]]:
    """一次调用生成 emotion_arc + villain_arc，写入 ctx 与 Project.extra。"""
    system = (
        "你是有30年经验的网络小说总编辑，同时负责读者情绪账户与反派自驱行动线。"
        "只返回 JSON 对象，不要任何解释文字。"
    )

    volumes_summary = ctx.get("volumes_summary", "（未设定）")
    positioning = ctx.get("positioning") or {}
    tropes = "、".join(positioning.get("tropes", []))
    emotional_arc_setting = positioning.get("emotional_arc", "medium")
    pace_type = positioning.get("pace_type", "medium")
    protagonist = ctx.get("protagonist", "主角")
    char_names = ctx.get("char_names", [])
    storyline_summary = ctx.get("storyline_summary", "（未设定）")
    ladder_summary = ctx.get("antagonist_ladder_summary") or "（未设定）"
    ladder: list[dict] = list(ctx.get("antagonist_ladder") or [])
    villain_timelines = ctx.get("villain_timelines", [])
    villain_hint = "；".join(villain_timelines) if villain_timelines else "（尚未设定，请根据卷骨架推断）"

    prompt = f"""小说：《{ctx.get('project_title', '')}》（{ctx.get('genre', '')}）
主角：{protagonist}
全体人物：{', '.join(char_names[:20]) or '（未设定）'}
核心爽点：{tropes or '（未设定）'}
感情线占比设定：{emotional_arc_setting}
节奏类型：{pace_type}
主要故事线：{storyline_summary}

【卷级骨架】
{volumes_summary}

【卷级对立面登记表（villain_name 必须逐卷引用，禁止另起新名）】
{ladder_summary}

【现有反派线索】
{villain_hint}

请同时完成两项总编辑任务，返回 JSON 对象（两个数组顺序均与卷骨架一致）：

{{
  "emotion_arc": [
    {{
      "vol_index": 0,
      "vol_title": "卷名（与骨架一致）",
      "phase": "opening",
      "dominant_emotion": "主色调（exciting/warm/tense/epic/sad/mysterious/romantic，单选）",
      "emotional_deposit": "读者本卷情绪收益（20字内）",
      "emotional_cost": "读者本卷情绪消耗（20字内；若无虐主填'轻微紧张'）",
      "net_balance": "positive/neutral/negative",
      "arc_note": "本卷情绪设计关键决策（30字内）"
    }}
  ],
  "villain_arc": [
    {{
      "vol_index": 0,
      "vol_title": "卷名",
      "villain_name": "必须与对立面登记表当卷 boss_name 一致",
      "vol_goal": "反派本卷主动目标（不得写「阻止主角」）",
      "vol_obstacle": "阻挡反派的因素",
      "vol_key_choice": "反派关键决策（暴露性格）",
      "vol_cost": "反派付出的代价（留给下卷债务）",
      "vol_result": "win/lose/stalemate",
      "threat_escalation": "本卷末威胁升级（量化一句话）",
      "hidden_move": "主角视角盲区的布局（回头拍大腿）"
    }}
  ]
}}

【情绪节律铁律】
1. 连续3卷 net_balance=negative 须有 positive 穿插
2. climax/ending 卷 net_balance 必须是 positive
3. dark_hour 卷 dominant_emotion 不能全是 sad
4. opening 卷 net_balance 必须是 positive

【反派行动线铁律】
1. vol_goal 必须是反派自己的欲望
2. dark_hour 卷 vol_result 必须是 win
3. climax 卷 vol_result 必须是 lose
4. vol_cost 不能为空

【对齐铁律】
同一 vol_index 上：dark_hour 卷情绪 net_balance=negative 时反派 vol_result 宜为 win；
climax 卷情绪 positive 时反派 vol_result 必须是 lose。
只返回 JSON 对象，不要解释。"""

    data = await call_json_object_with_retry(svc, system, prompt, task=_TASK)
    emotion_arc, villain_arc, err = _validate_narrative_arcs(data)
    if err:
        raise ValueError(f"[narrative_arcs] {err}")

    villain_arc = apply_ladder_boss_names(villain_arc, ladder)
    write_emotion_arc_ctx(ctx, emotion_arc)
    write_villain_arc_ctx(ctx, villain_arc)

    if persist:
        merge_project_extra_fields(
            svc,
            project,
            {"emotion_arc": emotion_arc, "villain_arc": villain_arc},
        )

    return emotion_arc, villain_arc
