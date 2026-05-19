"""Bootstrap Step 5：人物库。"""

from __future__ import annotations

from typing import Any

from app.models import Character, Project
from app.services.bootstrap.context import get_genre_kit_block
from app.services.bootstrap.parse import parse_json, safe_int
from app.services.llm_token_budgets import max_tokens_bootstrap_completion


async def gen_characters(svc: Any, project: Project, ctx: dict):
    system = "你是网络小说人物设计专家。只返回JSON数组。"
    power_hint = (
        f"\n境界体系（current_realm 必须从此列表选择）：{ctx.get('power_summary', '')}"
        if ctx.get('power_level_names') else ""
    )
    kit_block = get_genre_kit_block(ctx)
    prompt = f"""{kit_block}小说：《{ctx['project_title']}》({ctx['genre']})
创意：{ctx['logline']}
立意与类型：{ctx.get('premise', '')[:800] or '（未填写）'}
故事核：冲突={ctx['story_core'].get('conflict','')}，主题={ctx['story_core'].get('theme','')}{power_hint}

【流派编辑手册约束（必须严格遵守）】
- 角色配额必须符合 genre_kit 的 side_character_quota
- 说话风格必须符合 dialogue_tone 和 forbidden_examples（严禁出现本流派禁忌的开局/对白方式）
- speech_kit 中的 signature_words / sample_dialogues 必须体现流派特有的咬字习惯和禁忌词

⚠️ 你正在生成"主线核心卡司（Core Cast）"——这8人是全书贯穿的主线角色，不是全书所有人物。
后续章节写作时会按剧情需要动态补充配角，这里只需确定主线固定角色。

生成8个人物（至少：1主角+3核心配角+2反派+2师长/势力角色），返回JSON数组：
[
  {{
    "name": "姓名", "role": "protagonist",
    "character_tier": "core",
    "gender": "男", "age": "17", "faction": "所属势力",
    "personality": "性格（2句话）",
    "background": "背景经历（3句话）",
    "motivation": "核心动机",
    "arc": "人物弧线（从X到Y的成长）",
    "arc_stages": [
      {{"stage": "阶段名", "realm": "此阶段境界", "state": "人物状态", "chapter_range": "预计章节范围如1-30"}}
    ],
    "current_realm": "当前境界（或能力层级）",
    "speech_style": "说话风格（自由文本，一句话）",
    "speech_kit": {{
      "signature_words": ["最常说的1-3个标志性词语/口头禅"],
      "sentence_length_pref": "短句/中句/长句偏好",
      "taboo_words": ["绝对不会说的词或句式"],
      "sample_dialogues": ["5-8句典型台词，体现说话习惯"],
      "inner_monologue_style": "内心独白风格（克制/细腻/直白/诗化等）"
    }},
    "values": "价值观",
    "fear": "最恐惧的东西——必须具体，且这个恐惧在故事中会被迫直面",
    "secrets": "不愿公开的秘密——必须具体，且这个秘密暴露后会引发实质性后果",
    "strengths": ["特质1", "特质2"],
    "weaknesses": ["弱点1"],
    "special_traits": ["特殊能力或标志性特征"],
    "debt_to": "对哪个角色（用名字）有未还的恩情/仇怨/承诺？欠了什么？（15字内；若无则填空）",
    "detonation_vol": "上述欠债预计在第几卷被引爆或清偿？（填卷号整数，如2；若无欠债填0）"
  }}
]
role 只能是: protagonist / supporting / antagonist
character_tier 代表该人物在全书中的叙事层级，只能是以下4个值之一：
- core       = 核心长线：贯穿全书始终，长期驱动主线或重要支线（主角、主要反派、全书固定伙伴）
- arc        = 弧线支柱：在某卷或某段剧情中主导走向，随该弧线完结后淡出或阵亡
- plot       = 剧情推手：短期出现以推进特定情节节点，之后退场
- background = 背景填充：丰富世界厚度与氛围，无强情节绑定
请根据每个人物在故事中的实际定位严格判断，不要全部填 core。
debt_to 要求：主角必须对至少1个人有欠债；主要反派必须对主角或某配角有欠债（仇怨或嫉妒型）；这些欠债要分散在不同卷引爆，制造持续的人物动力。
arc_stages 要求：每人至少 2 个成长阶段（主角/核心反派 3-4 个）；realm 必须从境界白名单选择；chapter_range 覆盖全书跨度。

---
【第二部分】再追加生成5个「开局配角」（仅第一卷活跃，character_tier 固定为 "plot"）：
这些人物丰富开局前30章的世界厚度，无需长线设计，但每人在卷一必须有具体的情节功能。
典型角色类型（按需选用）：反派爪牙/小Boss、同辈竞争者/欺凌者、商人/情报贩子、门派长老/考官、普通市民/路人甲（提供信息或见证主角爆发）。

每个配角只需填写精简字段：
{{
  "name": "姓名",
  "role": "supporting 或 antagonist",
  "character_tier": "plot",
  "gender": "性别",
  "age": "年龄",
  "faction": "所属势力（已有势力名或留空）",
  "personality": "性格一句话",
  "motivation": "在卷一的行为动机（一句话）",
  "current_realm": "当前境界（与已有境界体系一致）",
  "vol1_function": "在第一卷30章内的具体剧情功能（必须具体：如'第5章欺凌主角引发第一次反击'、'第12章提供关键情报后消失'）",
  "debt_to": "",
  "detonation_vol": 0,
  "speech_kit": {{"signature_words": [], "sentence_length_pref": "短句", "taboo_words": [], "sample_dialogues": [], "inner_monologue_style": "直白"}},
  "values": "", "fear": "", "secrets": "", "strengths": [], "weaknesses": [], "special_traits": []
}}
请将这5个配角追加到同一JSON数组末尾，不要分开返回。

【JSON 可解析性（硬性）】根为 JSON 数组；所有字符串值内禁止出现未转义的英文双引号 " ，对白请用中文直角引号「」或不用引号。
每人 sample_dialogues 合计不超过 4 条、每条不超过 40 字，避免输出过长被网关截断导致 JSON 断裂。"""

    raw = await svc._call_with_retry(
        system,
        prompt,
        max_tokens=max_tokens_bootstrap_completion(),
        task="bootstrap.characters",
    )
    data = parse_json(raw)
    if not isinstance(data, list):
        data = data.get("characters", [])

    _VALID_TIERS = {"core", "arc", "plot", "background"}
    results = []
    for item in data:
        tier = item.get("character_tier", "core")
        if tier not in _VALID_TIERS:
            tier = "core"
        char_extra: dict = {}
        debt_to = (item.get("debt_to") or "").strip()
        if debt_to:
            char_extra["debt_to"] = debt_to
        det_vol_raw = item.get("detonation_vol")
        det_vol = safe_int(det_vol_raw, default=0)
        if det_vol and det_vol > 0:
            char_extra["detonation_vol"] = det_vol
        vol1_func = (item.get("vol1_function") or "").strip()
        if vol1_func:
            char_extra["vol1_function"] = vol1_func
        faction_name = item.get("faction") or ""
        faction_id_val = ctx.get("faction_name_to_id", {}).get(faction_name) or None
        raw_stages = item.get("arc_stages")
        arc_stages = raw_stages if isinstance(raw_stages, list) else []
        c = Character(
            project_id=project.id,
            name=item.get("name", "未命名"),
            role=item.get("role", "supporting"),
            character_tier=tier,
            gender=item.get("gender"),
            age=item.get("age"),
            faction=faction_name or None,
            faction_id=faction_id_val,
            personality=item.get("personality"),
            background=item.get("background"),
            motivation=item.get("motivation"),
            arc=item.get("arc"),
            arc_stages=arc_stages,
            current_realm=item.get("current_realm"),
            speech_style=item.get("speech_style"),
            speech_kit=item.get("speech_kit") or {},
            values=item.get("values"),
            fear=item.get("fear"),
            secrets=item.get("secrets"),
            strengths=item.get("strengths", []),
            weaknesses=item.get("weaknesses", []),
            special_traits=item.get("special_traits", []),
            extra=char_extra if char_extra else None,
        )
        svc.db.add(c)
        results.append(c)

    svc.db.commit()
    ctx["char_names"] = [c.name for c in results]
    ctx["protagonist"] = next((c.name for c in results if c.role == "protagonist"), "主角")
    ctx["char_realms"] = {
        c.name: (c.current_realm or "未知") for c in results
    }
    ctx["char_name_to_id"] = {c.name: str(c.id) for c in results}
    ctx["char_id_list"] = [{"id": str(c.id), "name": c.name} for c in results]
    ctx["core_char_names"] = [
        c.name for c in results if c.character_tier in ("core", "arc")
    ]
    ctx["plot_npc_summary"] = "; ".join(
        f"{c.name}（{c.extra.get('vol1_function', '') if c.extra else ''}）"
        for c in results
        if c.character_tier == "plot" and c.extra and c.extra.get("vol1_function")
    )
    # 主角及核心角色的心理档案，供 vol1_chapter_plans / expand_outline 注入
    # 包含驱动章节行为的底层字段：恐惧、欲望、价值观、人物弧线
    ctx["char_profiles"] = {
        c.name: {
            "core_wound": (c.fear or "").strip(),
            "current_desire": (c.motivation or "").strip(),
            "biggest_lie": "",  # 由 arc 隐含，暂不单独生成；后续可扩展
            "relationship_pressure": "",
            "values": (c.values or "").strip(),
            "arc": (c.arc or "").strip(),
        }
        for c in results
        if c.role == "protagonist" or c.character_tier in ("core", "arc")
    }
    return results
