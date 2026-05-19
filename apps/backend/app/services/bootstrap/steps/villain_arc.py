"""Bootstrap Step 9.8：反派独立行动线（卷级）。

设计动机
--------
当前系统里反派只在章级大纲的 villain_action 字段出现，
且是从主角视角出发提问的（"反派这章在做什么"），
缺乏反派自己的欲望→障碍→选择→代价四元组。

一个有自驱力的反派能让主角的每次胜利都"昂贵"，
让每次失败都显得"合理"而非"剧情杀"。

本步骤为主要反派生成卷级独立行动线：
  - 每卷反派有自己的目标、阻碍、关键选择、付出代价
  - 明确标注"本卷反派胜/败/平"的结果（驱动 phase 对齐）
  - 写入 Project.extra['villain_arc'] + ctx，供章纲生成注入
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm.attributes import flag_modified

from app.services.bootstrap.parse import parse_json


async def gen_villain_arc(svc: Any, project, ctx: dict) -> list[dict]:
    """生成主要反派的卷级独立行动线。

    Args:
        svc:     Bootstrap 服务实例（需要 _call_with_retry / db）。
        project: 当前项目模型。
        ctx:     全局 bootstrap 上下文（需要 volumes_summary / char_names /
                 villain_timelines / protagonist）。

    Returns:
        反派行动线列表（每卷一条），同时写入 Project.extra['villain_arc']。
    """
    system = (
        "你是有30年经验的网络小说总编辑，深知：好的反派是主角成长的第二引擎。"
        "只返回 JSON 数组，不要任何解释文字。"
    )

    volumes_summary = ctx.get("volumes_summary", "（未设定）")
    protagonist = ctx.get("protagonist", "主角")
    char_names = ctx.get("char_names", [])
    villain_timelines = ctx.get("villain_timelines", [])
    storyline_summary = ctx.get("storyline_summary", "（未设定）")
    positioning = ctx.get("positioning") or {}
    tropes = "、".join(positioning.get("tropes", []))

    villain_hint = "；".join(villain_timelines) if villain_timelines else "（尚未设定，请根据卷骨架推断）"

    prompt = f"""小说：《{ctx.get('project_title', '')}》（{ctx.get('genre', '')}）
主角：{protagonist}
全体人物：{', '.join(char_names[:20]) or '（未设定）'}
核心爽点：{tropes or '（未设定）'}
主要故事线：{storyline_summary}

【卷级骨架】
{volumes_summary}

【现有反派线索】
{villain_hint}

请为本书主要反派（从人物列表或骨架中识别）生成卷级独立行动线。
反派是有自己欲望的人，不是「主角前进路上的障碍物」。

返回 JSON 数组（每卷一条，顺序与卷骨架一致）：
[
  {{
    "vol_index": 0,
    "vol_title": "卷名",
    "villain_name": "反派姓名（从人物列表选，若无则命名）",
    "vol_goal": "本卷反派主动想要实现什么（必须是具体目标，不是「阻止主角」）",
    "vol_obstacle": "什么阻挡了反派（外部对手/内部矛盾/资源不足）",
    "vol_key_choice": "反派本卷的关键决策（暴露性格，不只是手段）",
    "vol_cost": "这个决策让反派付出的代价（留给下卷的债务）",
    "vol_result": "win/lose/stalemate（本卷反派vs主角格局的总结）",
    "threat_escalation": "本卷末反派的威胁比卷初升级了多少（一句话，需量化）",
    "hidden_move": "反派在主角视角盲区做了什么让读者后来回想觉得「原来如此」的布局"
  }}
]

【编辑铁律】
1. vol_goal 必须是反派自己的欲望，不得写「阻止主角」「打败主角」
2. dark_hour 卷 vol_result 必须是 win（反派大幅领先才能制造真正的至暗）
3. climax 卷 vol_result 必须是 lose（反派的失败必须来自主角的成长，不只是外力）
4. hidden_move 必须是读者在当时看不到、但回头再看会拍大腿的布局
5. vol_cost 不能为空——反派也有代价，否则他不可信
只返回JSON数组，不要解释。"""

    try:
        raw = await svc._call_with_retry(
            system, prompt, max_tokens=2048, task="bootstrap.villain_arc"
        )
        arc = parse_json(raw)
        if not isinstance(arc, list):
            arc = []
    except Exception:
        arc = []

    # 写库
    try:
        base = project.extra if isinstance(project.extra, dict) else {}
        project.extra = {**base, "villain_arc": arc}
        flag_modified(project, "extra")
        svc.db.commit()
    except Exception:
        pass

    # ctx 摘要（供章纲 prompt + 一致性扫描引用）
    if arc:
        ctx["villain_arc"] = arc
        parts = []
        for i, v in enumerate(arc):
            title = v.get("vol_title") or f"卷{v.get('vol_index', i)}"
            goal = (v.get("vol_goal") or "?")[:20]
            parts.append(f"{title}:{v.get('villain_name','?')}→{goal}[{v.get('vol_result','?')}]")
        ctx["villain_arc_summary"] = " | ".join(parts)

    return arc
