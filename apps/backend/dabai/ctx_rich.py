"""富上下文注入块（不计 token 的完整结构化档案）。

设计动机：ctx_brief 把人物压成人名、故事线压成线名，下游卷骨架/章纲拿不到
「谁是打脸对象 / 初始张力 / 资产归属 / 本卷 Boss」，是章纲同质化与人物乱用的根因。
本模块给 volumes / beat_sequence / chapter_outlines 注入全量档案。

所有 builder 在对应 ctx 键缺失时返回 ""（写作期卷展开 ctx 部分键缺失时自然降级，
台账与既定事实由 story_so_far 块兜底）。
"""

from __future__ import annotations


def _s(val, n: int = 60) -> str:
    return str(val or "").strip()[:n]


def characters_block(ctx: dict) -> str:
    """人物全量档案：职能/欲望/憋屈来源/口癖——打脸对象与见证者轮换的素材库。"""
    chars = ctx.get("characters") or []
    if not chars:
        return ""
    lines = []
    for c in chars[:18]:
        if not isinstance(c, dict) or not c.get("name"):
            continue
        bits = [f"{c['name']}（{_s(c.get('role'), 20)}/{_s(c.get('tier'), 8)}）"]
        if c.get("start_realm"):
            bits.append(f"起始境界:{_s(c['start_realm'], 20)}")
        if c.get("persona"):
            bits.append(f"性格:{_s(c['persona'], 40)}")
        if c.get("function"):
            bits.append(f"职能:{_s(c['function'], 40)}")
        if c.get("desire"):
            bits.append(f"欲望:{_s(c['desire'], 30)}")
        if c.get("wound"):
            bits.append(f"憋屈来源:{_s(c['wound'], 30)}")
        speech = c.get("speech_kit") or c.get("speech_style")
        if speech:
            bits.append(f"口癖/台词风:{_s(speech, 40)}")
        lines.append("  - " + "；".join(bits))
    if not lines:
        return ""
    return (
        "【人物档案（只能用这些人；打脸对象与见证者从中逐章轮换，禁止凭空造名）】\n"
        + "\n".join(lines) + "\n"
    )


def relations_block(ctx: dict) -> str:
    """主角开局关系与张力——前期打脸剧情的燃料，态度变化须有剧情交代。"""
    rels = (ctx.get("story_assets") or {}).get("initial_relations") or []
    if not rels:
        return ""
    lines = [
        f"  - {_s(r.get('from'), 20)}→{_s(r.get('to'), 20)}：{_s(r.get('attitude'), 12)}"
        + (f"（{_s(r.get('tension'), 40)}）" if r.get("tension") else "")
        for r in rels[:12] if isinstance(r, dict) and r.get("to")
    ]
    if not lines:
        return ""
    return (
        "【开局关系张力（敌对→忌惮→臣服就是爽点曲线；态度跳变须有打脸/救场事件支撑）】\n"
        + "\n".join(lines) + "\n"
    )


def assets_block(ctx: dict, volume_number: int | None = None) -> str:
    """剧情资产台账：归属/登场时机——卷章纲围绕这批东西做文章，禁止另造同位宝物。"""
    assets = (ctx.get("story_assets") or {}).get("plot_assets") or []
    if not assets:
        return ""
    lines = []
    for a in assets[:10]:
        if not isinstance(a, dict) or not a.get("name"):
            continue
        debut = "开局已持有" if a.get("debut") == "start" else \
            f"第{a.get('planned_volume', '?')}卷登场"
        star = ""
        if volume_number and a.get("debut") != "start" \
                and int(a.get("planned_volume") or 0) == int(volume_number):
            star = "★本卷必须兑现登场★"
        lines.append(
            f"  - {a['name']}（{_s(a.get('kind'), 8)}/{_s(a.get('plot_role'), 10)}）"
            f"持有:{_s(a.get('owner'), 16) or '无主'}；{debut}{star}；"
            f"{_s(a.get('description'), 50)}"
        )
    if not lines:
        return ""
    return (
        "【剧情资产台账（夺宝/底牌/成长线全从这里取材；未登场资产禁止提前出现在主角手里）】\n"
        + "\n".join(lines) + "\n"
    )


def factions_block(ctx: dict) -> str:
    """势力阵营 + 各自场景池（章纲 location 轮换的素材来源）。"""
    factions = ctx.get("factions") or []
    if not factions:
        return ""
    lines = []
    for f in factions[:8]:
        if not isinstance(f, dict) or not f.get("name"):
            continue
        bits = [f"{f['name']}（{_s(f.get('stance'), 12)}）",
                f"作用:{_s(f.get('role'), 40)}"]
        if f.get("power_tier"):
            bits.append(f"战力:{_s(f.get('power_tier'), 20)}")
        locs = f.get("locations") or []
        if locs:
            bits.append("场景:" + "/".join(_s(x, 14) for x in locs[:6]))
        lines.append("  - " + "；".join(bits))
    if not lines:
        return ""
    return "【势力阵营（打脸靶子与压迫来源的土壤）】\n" + "\n".join(lines) + "\n"


def scene_pool_block(ctx: dict) -> str:
    """全书场景载体池：location 轮换从这里取具体名字，相邻 3 章不得同类。"""
    pool: list[str] = []
    for f in (ctx.get("factions") or []):
        if isinstance(f, dict):
            pool.extend(_s(x, 16) for x in (f.get("locations") or []) if x)
    if not pool:
        return ""
    seen: list[str] = []
    for x in pool:
        if x and x not in seen:
            seen.append(x)
    return (
        "【场景载体池（location 优先从中取具体地名再加事件，如「万宝拍卖行·斗宝」；"
        "相邻 3 章不得同类，整卷至少用 6 种不同载体）】\n  "
        + "、".join(seen[:24]) + "\n"
    )


def antagonist_block(ctx: dict, volume_number: int | None = None) -> str:
    """卷级反派阶梯：每卷的对立面 Boss 与压迫方式（打脸对象不再凭空造）。"""
    ladder = ctx.get("antagonist_ladder") or []
    if not ladder:
        return ""
    lines = []
    for row in ladder[:12]:
        if not isinstance(row, dict):
            continue
        vn = row.get("volume_number")
        mark = "★本卷★" if volume_number and int(vn or 0) == int(volume_number) else ""
        lines.append(
            f"  - 第{vn}卷{mark}：{_s(row.get('boss_name'), 16)}"
            f"（{_s(row.get('boss_faction'), 16)}，{_s(row.get('boss_realm'), 12)}"
            f"/档{row.get('boss_realm_rank', '?')}）"
            f"仇怨:{_s(row.get('motive'), 36)}；压迫:{_s(row.get('pressure_style'), 24)}；"
            f"下场:{_s(row.get('fate'), 24)}"
        )
    if not lines:
        return ""
    return (
        "【卷级反派阶梯（各卷主要对立面以此为准；本卷压迫与卷末高潮必须落在本卷 Boss 身上，"
        "禁止另造同级反派）】\n" + "\n".join(lines) + "\n"
    )


def mystery_block(ctx: dict, volume_number: int | None = None) -> str:
    """跨卷谜题揭示排程：本卷该透出哪块信息，禁止提前说破真相。"""
    mysteries = (ctx.get("mystery_schedule") or {}).get("mysteries") or []
    if not mysteries:
        return ""
    lines = []
    for m in mysteries[:6]:
        if not isinstance(m, dict) or not m.get("name"):
            continue
        head = (f"  - {m['name']}（悬念:{_s(m.get('hook_question'), 30)}；"
                f"第{m.get('final_reveal_volume', '?')}卷揭底）")
        reveals = m.get("reveals") or []
        if volume_number:
            cur = [r for r in reveals
                   if isinstance(r, dict) and int(r.get("volume_number") or 0) == int(volume_number)]
            if cur:
                head += f"\n    ★本卷透出★：{_s(cur[0].get('reveal'), 60)}"
        else:
            head += "".join(
                f"\n    第{r.get('volume_number')}卷透:{_s(r.get('reveal'), 40)}"
                for r in reveals[:8] if isinstance(r, dict)
            )
        lines.append(head)
    if not lines:
        return ""
    return (
        "【谜题揭示排程（长线追读钩子；只透「本卷透出」那一块，揭底卷之前禁止说破真相）】\n"
        + "\n".join(lines) + "\n"
    )


def storylines_block(ctx: dict) -> str:
    """故事线 + 关键节点与计划卷次（卷骨架须写明各线本卷推进到哪）。"""
    sls = ctx.get("storylines") or []
    if not sls:
        return ""
    lines = []
    for s in sls[:6]:
        if not isinstance(s, dict) or not s.get("name"):
            continue
        head = f"  - {s['name']}（{_s(s.get('type'), 10)}）：{_s(s.get('summary'), 50)}"
        nodes = s.get("nodes") or []
        node_bits = [
            f"第{n.get('planned_volume', '?')}卷:{_s(n.get('node'), 26)}"
            for n in nodes[:6] if isinstance(n, dict) and n.get("node")
        ]
        if node_bits:
            head += "\n    节点：" + "；".join(node_bits)
        lines.append(head)
    if not lines:
        return ""
    return (
        "【故事线与关键节点（每卷除主线外至少推进 1 条支线，按节点表落位）】\n"
        + "\n".join(lines) + "\n"
    )


def volume_design_context(ctx: dict) -> str:
    """卷骨架步的全量设计上下文。"""
    return "".join(filter(None, [
        factions_block(ctx),
        characters_block(ctx),
        relations_block(ctx),
        storylines_block(ctx),
        assets_block(ctx),
        antagonist_block(ctx),
        mystery_block(ctx),
    ]))


def chapter_design_context(ctx: dict, volume_number: int | None = None) -> str:
    """章纲（节拍序列 + 五拍展开）的全量设计上下文，按卷过滤反派/谜题/资产。"""
    return "".join(filter(None, [
        characters_block(ctx),
        relations_block(ctx),
        assets_block(ctx, volume_number),
        antagonist_block(ctx, volume_number),
        mystery_block(ctx, volume_number),
        scene_pool_block(ctx),
    ]))
