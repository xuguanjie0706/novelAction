"""章纲 prompt：两段式（卷级爽点节拍序列 → 小批五拍展开）+ 定向修复。

两段式动机：单批 30 章同时满足五拍×30 + 反同质化 + 境界单调，注意力必衰减，
后半批模板化。先一次调用排好整卷「节拍行」（每章一行：爽点/场景/靶子/境界/钩子），
通过轻量校验后再按小批展开五拍，每批锁定对应节拍行，全局规划与局部展开分离。
"""

from __future__ import annotations

import json

from dabai.config import DabaiConfig
from dabai.ctx_rich import chapter_design_context
from dabai.hooks import hook_library_block
from dabai.first_chapter_opening import first_chapter_opening_block
from dabai.golden_finger_bind import chapter_outline_bind_block
from dabai.non_system import chapter_outline_non_system_note, prefers_non_system
from dabai.naming import character_naming_prompt_block
from dabai.prompt_base import SYS_BASE, benchmark_block, ctx_brief, ladder_block
from dabai.plot_blueprint import plot_blueprint_enabled
from dabai.realm_spine import (
    power_ceiling_prompt_block,
    realm_pace_schedule_note,
)

# ── 共用小块 ─────────────────────────────────────────────────────────────────


def _carry_block(prev_tail: str, gbs: int) -> str:
    """Legacy 120 字钩子承接（无 bridge_block 时降级）。"""
    prev_tail = (prev_tail or "").strip()
    if not prev_tail:
        return ""
    return (
        f"\n【上文结尾（硬性承接）】前一章末钩/爽点：「{prev_tail[:200]}」。"
        f"第{gbs}章必须顺着它起，不得另起炉灶、不得回到已解决的旧危机。\n"
    )


def _bridge_block(ctx: dict, batch: dict, gbs: int) -> str:
    """硬承接包：DB 正文末段 / 完整五拍 / 本 run 已生成末章 / 钩子兜底。"""
    bridge = (batch.get("bridge_block") or ctx.get("bridge_block") or "").strip()
    if bridge:
        return bridge if bridge.startswith("\n") else "\n" + bridge + "\n"
    return _carry_block(batch.get("prev_tail") or ctx.get("prev_tail") or "", gbs)


def _generated_outlines_block(ctx: dict) -> str:
    """本 run 已生成章纲（bootstrap/卷展开批间）。"""
    block = (ctx.get("generated_outlines_block") or "").strip()
    if block:
        return "\n" + block + "\n"
    outlines = ctx.get("generated_chapter_outlines") or []
    if not outlines:
        return ""
    from app.services.dabai.lab_narrative_state import format_generated_outlines_block
    return "\n" + format_generated_outlines_block(outlines) + "\n"


def _narrative_state_head(ctx: dict) -> str:
    """Layer 2 情节状态（优先 narrative_state，兼容 story_so_far）。"""
    story = (ctx.get("narrative_state") or ctx.get("story_so_far") or "").strip()
    if not story:
        return ""
    return (
        "\n【前情与既定事实（全部已发生或已锁定计划；章纲必须自洽；"
        "禁止矛盾、禁止重置、禁止已臣服/已死人物无故复活/翻脸）】\n"
        + story + "\n"
    )


def _realm_spine_block(vol: dict, realm_floor: int | None, ctx: dict) -> str:
    vr_lo = vol.get("realm_start_rank")
    vr_hi = vol.get("realm_end_rank")
    if not (vr_lo or vr_hi or realm_floor):
        return ""
    floor = realm_floor or vr_lo or 1
    vol_planned = int(vol.get("planned_chapters") or 30)
    return (
        "\n【境界脊柱（硬约束，违反即判 REALM 回退）】\n"
        f"  本卷主角境界区间：第 {vr_lo or '?'} 档 → 第 {vr_hi or '?'} 档。\n"
        f"  起步：主角已在第 {floor} 档，每章 realm_rank ★只能 ≥ {floor}★、"
        "全程单调不减、不得超过本卷 realm_end_rank。\n"
        + realm_pace_schedule_note(vol, vol_planned, ctx)
        + "  同境内细层用 realm_sub_rank(1～9) 表达，升大境时重置为 1。\n"
    )


def _volume_head(ctx: dict, vol: dict) -> str:
    extra = vol.get("extra") or {}
    opening = vol.get("opening_setup") or extra.get("opening_setup") or ""
    head = (
        f"本卷大爆点：{vol.get('big_beats')}\n本卷卷末高潮：{vol.get('volume_climax')}\n"
    )
    if opening and int(vol.get("volume_number") or 1) == 1:
        head += (
            f"★第1卷开篇施工图（第1章 yaqu/location 须对齐，禁止另起冲突线）★：{opening}\n"
        )
    if extra.get("boss"):
        head += f"本卷 Boss（压迫与卷末高潮的靶子）：{extra['boss']}\n"
    if extra.get("storyline_moves"):
        head += f"本卷故事线推进：{extra['storyline_moves']}\n"
    if extra.get("mystery_moves"):
        head += f"本卷谜题透出：{extra['mystery_moves']}\n"
    narrative = _narrative_state_head(ctx)
    if narrative:
        head = narrative + "\n" + head
    qc = (ctx.get("qc_feedback") or "").strip()
    if qc and qc not in (ctx.get("narrative_state") or ""):
        head += "\n" + qc + "\n"
    return head


# ── 阶段一：卷级爽点节拍序列 ──────────────────────────────────────────────────

_BEAT_SYS = SYS_BASE + (
    "\n\n【节拍序列专项】你现在只做全局规划，不展开细节：给每章一行节拍，"
    "先把整卷的爽点阶梯、场景轮换、打脸对象轮换、境界爬升一次排好。"
    "这张表是后续逐章展开的施工图，全局协调性优先于单章精彩。"
)


def _beat_skeleton(cfg: DabaiConfig, gbs: int) -> str:
    pool = "、".join(cfg.shuang_pool)
    return (
        "  {\n"
        f'    "chapter_number": {gbs},\n'
        '    "title": "第X章 标题(≤10字，句式轮换)",\n'
        f'    "shuang_type": "爽点类型（从 {pool} 选）",\n'
        '    "target_emotion": "本章目标情绪（一词；整卷要张弛起伏，非一条直线）",\n'
        '    "location": "场景载体（场景池取具体地点+事件）",\n'
        '    "slap_target": "本章打脸/压迫对象（人物档案或反派阶梯中的名字）",\n'
        '    "realm_rank": 1,\n'
        '    "is_big_beat": false,\n'
        '    "one_line": "一句话剧情（憋屈→引爆→钩子的骨架，≤40字）"\n'
        "  }"
    )


def _beat_rules(cfg: DabaiConfig, ctx: dict | None = None) -> str:
    return (
        "节拍硬规则：\n"
        "1. 相邻两章 shuang_type 不同；连续 3 章不得同类 location；"
        "同一 slap_target 不得连续 3 章；\n"
        f"2. 每 {cfg.big_beat_every} 章至少 1 个 is_big_beat=true，"
        "且爆点强度走阶梯（小爽铺垫→中爽推进→卷末最大），卷末高潮落在本卷 Boss 身上；\n"
        "3. realm_rank 单调不减、落在本卷区间内，升档章通常紧跟大机缘/大战；\n"
        "4. 标题句式轮换（悬念式/台词式/反差式/动作式/数字式），"
        "禁止相邻标题以相同 2 字开头；\n"
        "5. 本卷规划登场的剧情资产、谜题透出、故事线节点必须各有落位章"
        "（在 one_line 里点明）；\n"
        "6. ★情绪先于故事★：每章填 target_emotion，整卷情绪要张弛起伏"
        "（憋屈蓄势↔爽感释放↔甜/虐交替），禁止全程同一情绪一条直线。\n"
        + (
            "7. ★情节蓝图★：节拍 one_line 须对齐 benchmark.adaptation_plan.chapter_beat_hints，"
            "可扩写场面细节，骨架不得偏离映射。\n"
            if plot_blueprint_enabled(cfg=cfg, ctx=ctx) else ""
        )
    )


def beat_sequence(ctx: dict, cfg: DabaiConfig) -> tuple[str, str]:
    """【降级路径】阶段一：整卷（或窗口）每章一行的爽点节拍序列。"""
    vol = ctx.get("_target_volume", {})
    w = ctx.get("_beat_window", {})
    gbs, gbe = int(w.get("global_start", 1)), int(w.get("global_end", 1))
    n = gbe - gbs + 1
    user = (
        f"{ctx_brief(ctx)}\n"
        + benchmark_block(ctx)
        + chapter_design_context(ctx, vol.get("volume_number"), global_start=gbs, global_end=gbe)
        + _volume_head(ctx, vol)
        + ladder_block(ctx)
        + _generated_outlines_block(ctx)
        + _bridge_block(ctx, w, gbs)
        + _realm_spine_block(vol, w.get("realm_floor"), ctx)
        + f"\n为《{vol.get('title', '')}》排出全书第 {gbs}～{gbe} 章（共 {n} 章）的"
        "【爽点节拍序列】，每章一行。返回 JSON 数组：\n"
        "[\n" + _beat_skeleton(cfg, gbs) + "\n]\n"
        + _beat_rules(cfg, ctx)
    )
    return _BEAT_SYS, user


# ── 阶段二：小批五拍展开 ──────────────────────────────────────────────────────


def _beat_rows_block(rows: list[dict]) -> str:
    if not rows:
        return ""
    lines = [
        f"  第{r.get('chapter_number')}章｜{r.get('title', '')}｜爽点:{r.get('shuang_type', '')}"
        f"｜场景:{r.get('location', '')}｜靶子:{r.get('slap_target', '')}"
        f"｜境界档:{r.get('realm_rank', '?')}｜大爆点:{'是' if r.get('is_big_beat') else '否'}"
        f"｜剧情:{r.get('one_line', '')}"
        for r in rows
    ]
    return (
        "\n【本批节拍行（施工图，硬约束）】逐章遵循下表：shuang_type / location / "
        "打脸对象 / realm_rank / is_big_beat 以节拍行为准（标题与细节可润色升级，"
        "骨架不得改）：\n" + "\n".join(lines) + "\n"
    )


def _chapter_system(cfg: DabaiConfig) -> str:
    return SYS_BASE + (
        "\n\n【章纲专项 · 爽点节拍器】\n"
        "本任务的核心不是『欲望-障碍-选择-代价』那套精品文链路——"
        "★明确禁止给主角的爽点强加代价/后遗症★。大白文的章是：\n"
        "憋屈势能(yaqu_setup) → 【转折拍 emotion_turn：情绪扳机】 → 爽点引爆(yinbao) → "
        "爽感反馈(shuang_payoff，必须有观众) → 强钩子(end_hook)。\n"
        "★转折拍是关键★：从憋屈到引爆之间必须有一个『扳机』——主角情绪从隐忍/被动 靠一个具体触发点"
        "（一句羞辱、一个细节、一段闪念、一声金手指提示）转到出手/反击，"
        "这样正文才不会情绪硬跳。普通章转折拍示例（非觉醒章禁止套濒死/倒计时口径）：\n"
        "  - 从隐忍赔笑→对方把母亲遗物摔在地上（触发）→眼神骤冷、杀意压不住；\n"
        "  - 从看戏吃瓜→点名要苏挽柔陪酒（触发）→当场起身、踏前一步；\n"
        "  - 从自我怀疑→识海里功法第二层自行运转（触发）→嘴角上扬、稳了。\n"
        "金手指首次觉醒章另须写清『疑→证→择』绑定节拍（见下方硬约束）。\n"
        "【功力要求】你是写了三十年白话网文的老作者，章纲每个字段都按可拍画面写：\n"
        "  - 标题自带钩子（冲突/反差/悬念入题），禁止『修炼』『突破』这类白开水标题；\n"
        "  - yaqu_setup 写到具体的人+具体的不公（谁、当着谁、用什么方式压主角），不写抽象处境；\n"
        "  - yinbao 写清招式/手段/场面调度，反转要有“先抑两拍再爆”的节奏感；\n"
        "  - shuang_payoff 写打脸对象的具体反应（脸色/下跪/改口/围观惊呼），爽感可量化；\n"
        "  - 全卷爽点强度要走阶梯：小爽铺垫→中爽推进→大爆点炸场，禁止平铺直叙一个调门到底；\n"
        "  - 所有人物/势力/功法/道具只能用上文给定的既有设定，禁止凭空新造核心设定。\n"
        "【反同质化（硬约束，违反即废稿）】每章是一集不同的戏，不是同一集换个对手：\n"
        "  - location 场景载体轮换：相邻 3 章不得同类，优先用【场景载体池】里的具体地名；\n"
        "  - 标题句式轮换：悬念式(他敢动手?)/台词式(就凭你也配)/反差式(废物拍出天价)/"
        "动作式(一掌碎碑)/数字式(三息之内) 轮换，"
        "★禁止全批标题同一句式、禁止相邻标题以相同字词开头★；\n"
        "  - 打脸对象与见证者轮换：禁止同一人连续 3 章当靶子，witnesses 阵容逐章有变化；\n"
        "  - 憋屈手法轮换：言语羞辱/资源克扣/规则刁难/当众污蔑/抢功嫁祸/退婚悔约 轮着来，"
        "禁止每章都是『嘲讽主角是废物』一招。\n"
        "【导演预演】你在为下游写手排可拍分镜表：每个字段须具体到谁、在哪、"
        "怎么压/怎么打、见证者如何反应；禁止「局势紧张」「悬念丛生」等抽象套话。\n"
        "【字数分档】普通章 expected_words 2000-2200；is_big_beat 大爆点章 2400-2600；"
        f"黄金前 {cfg.golden_chapters} 章 1800-2200（快进快出）。"
    )


def _golden_rule(cfg: DabaiConfig, gbs: int) -> str:
    if gbs <= cfg.golden_chapters:
        return (
            f"1. 黄金前 {cfg.golden_chapters} 章（含全书第1章）："
            "第1章按【第1章开局定制】从本书主题写具体憋屈+留金手指钩子（禁止退婚踹 cliff）；"
            "金手指在前 2～3 章内见效、首次当众大打脸落在前 3～5 章其中一章——"
            "★具体哪一章见效/打脸按本书节奏自行编排，禁止每本书都卡死在『第2章见效、第3章打脸』同一拍★。\n"
        )
    return "1. 非全书开局：开篇承接上文钩子直接进入本卷冲突，禁止重新介绍金手指/世界观。\n"


def _expand_rules(cfg: DabaiConfig, gbs: int, ctx: dict) -> str:
    return (
        "硬约束：\n"
        + _golden_rule(cfg, gbs) +
        "2. 相邻两章 shuang_type 不得相同；每 "
        f"{cfg.big_beat_every} 章至少一个 is_big_beat=true 的大爆点。\n"
        "3. shuang_payoff 必须写明『当着谁的面、爽在哪』，witnesses 至少 1 人（爽点必须有观众）。\n"
        f"4. 每章 new_info_count ≤ {cfg.max_new_info_per_chapter}"
        "（信息密度上限：一章新引入的设定/人物/名词合计不超过此数）。\n"
        "5. end_hook 必须具体（更强敌人登场/更大机缘/打脸预告），禁用『悬念丛生』『让人期待』套话。\n"
        "6. 禁止给主角爽点强加 choice_cost / 后遗症 / 道德负担。\n"
        "7. witnesses / involved_characters 只能用【人物档案】里的具体正名，"
        "禁止「执法堂甲/乙」「XX弟子A」「XX众」类占位。\n"
        "8. yinbao/shuang_payoff 战力须服从【战力天花板】与本章 realm_rank / realm_sub_rank。\n"
        "9. 每章必填 target_emotion（交付的目标情绪）与 hook_type（章尾钩子 13 式之一）；"
        "相邻两章 hook_type 不得相同，整卷情绪要张弛起伏。\n"
        + hook_library_block()
        + character_naming_prompt_block(ctx, for_chapter=True)
        + power_ceiling_prompt_block(ctx)
        + "\n"
    )


def _chapter_skeleton(gbs: int) -> str:
    return (
        "{\n"
        f'  "chapter_number": {gbs}, "title": "第X章 标题(≤10字)",\n'
        '  "shuang_type": "本章爽点类型(从可用类型选)",\n'
        '  "target_emotion": "本章交付的目标情绪(一词，如 爽感释放/扬眉吐气/憋屈蓄势/甜)",\n'
        '  "hook_type": "章尾钩子类型(13式之一，须与相邻章不同)",\n'
        '  "location": "本章主场景载体(具体地点+事件，如 万宝拍卖行·斗宝；相邻3章不得同类)",\n'
        '  "yaqu_setup": "憋屈势能：谁在压主角/什么不公",\n'
        '  "emotion_turn": "转折拍：从【情绪】→【触发】→【情绪】；金手指觉醒章须含疑→证→择",\n'
        '  "yinbao": "引爆：主角怎么靠金手指反转",\n'
        '  "shuang_payoff": "爽感量化：当着谁的面、爽在哪、对方什么反应",\n'
        '  "witnesses": ["见证者/被打脸者(≥1人)"],\n'
        '  "end_hook": "章末强钩子(具体)",\n'
        '  "new_info_count": 1,\n'
        '  "involved_characters": ["出场人物(用已知人物名)"],\n'
        '  "is_big_beat": false,\n'
        '  "expected_words": 2000,\n'
        '  "realm_rank": 1,\n'
        '  "realm_sub_rank": 1\n'
        "}"
    )


_REALM_NOTE = (
    "\n★realm_rank★ = 本章结束时主角大境界档；★realm_sub_rank★ = 同境内小层(1～9)。"
    "单调不减；落在本卷区间内；战力描写不得超越【战力天花板】。"
)


def _special_blocks(ctx: dict, cfg: DabaiConfig, gbs: int, gbe: int) -> str:
    """金手指绑定节拍 / 非系统口径 / 第1章开局定制（按全局章号判定）。"""
    gf_name = (ctx.get("golden_finger") or {}).get("name", "")
    artifact = prefers_non_system(ctx)
    bind = chapter_outline_bind_block(gf_name, artifact=artifact) \
        if gbs <= cfg.golden_chapters else ""
    non_sys = chapter_outline_non_system_note() if artifact else ""
    ch1 = first_chapter_opening_block(ctx) if gbs <= 1 <= gbe else ""
    return bind + non_sys + ch1


def chapter_outlines(ctx: dict, cfg: DabaiConfig) -> tuple[str, str]:
    """【降级路径】阶段二：按节拍行小批展开五拍章纲。"""
    vol = ctx.get("_target_volume", {})
    n = vol.get("planned_chapters", cfg.volume_chapters)
    batch = ctx.get("_batch", {})
    bs = int(batch.get("batch_start", 1))
    be = int(batch.get("batch_end", n))
    gbs = int(batch.get("global_start", bs))
    gbe = int(batch.get("global_end", be))
    batch_count = be - bs + 1
    user = (
        f"{ctx_brief(ctx)}\n"
        + benchmark_block(ctx)
        + chapter_design_context(ctx, vol.get("volume_number"), global_start=gbs, global_end=gbe)
        + _volume_head(ctx, vol) + "\n"
        f"为《{vol.get('title', '第1卷')}》（phase={vol.get('phase')}，全卷共 {n} 章）"
        f"生成全书第 {gbs}～{gbe} 章章纲（本卷第 {bs}～{be} 章，本批 {batch_count} 章）。\n"
        f"可用爽点类型：{'、'.join(cfg.shuang_pool)}\n"
        + ladder_block(ctx)
        + _beat_rows_block(batch.get("beat_rows") or [])
        + _generated_outlines_block(ctx)
        + _bridge_block(ctx, batch, gbs)
        + _realm_spine_block(vol, batch.get("realm_floor"), ctx)
        + _special_blocks(ctx, cfg, gbs, gbe)
        + _expand_rules(cfg, gbs, ctx) + "\n"
        f"返回 JSON 数组，必须恰好 {batch_count} 个元素（全书第{gbs}～{gbe}章，一章不少），每个：\n"
        + _chapter_skeleton(gbs) + _REALM_NOTE
    )
    return _chapter_system(cfg), user


# ── 单次整卷：beat 施工图 + 五拍展开同一次推理（按次计费主路径）────────────────

_VOLUME_SYS_ADDENDUM = (
    "\n\n【两段式·同次完成】先在 beat_sequence 里把整卷节拍排好"
    "（全局协调爽点阶梯/场景轮换/打脸对象轮换/境界爬升），"
    "再严格按自己排好的节拍行逐章展开 chapter_outlines 五拍——"
    "骨架（shuang_type/location/靶子/realm_rank/is_big_beat）两块必须一致。"
    "全局协调性优先：先排完整张表，再开始展开，禁止边排边写。"
)


def volume_chapters(ctx: dict, cfg: DabaiConfig) -> tuple[str, str]:
    """单次调用产出整卷（窗口）：节拍序列 + 五拍章纲（输出上限须 ≥ 30k token）。"""
    vol = ctx.get("_target_volume", {})
    n = vol.get("planned_chapters", cfg.volume_chapters)
    batch = ctx.get("_batch", {})
    gbs = int(batch.get("global_start", 1))
    gbe = int(batch.get("global_end", n))
    count = gbe - gbs + 1
    user = (
        f"{ctx_brief(ctx)}\n"
        + benchmark_block(ctx)
        + chapter_design_context(ctx, vol.get("volume_number"), global_start=gbs, global_end=gbe)
        + _volume_head(ctx, vol) + "\n"
        f"为《{vol.get('title', '第1卷')}》（phase={vol.get('phase')}，全卷共 {n} 章）"
        f"一次完成全书第 {gbs}～{gbe} 章（共 {count} 章）的节拍序列与五拍章纲。\n"
        f"可用爽点类型：{'、'.join(cfg.shuang_pool)}\n"
        + ladder_block(ctx)
        + _generated_outlines_block(ctx)
        + _bridge_block(ctx, batch, gbs)
        + _realm_spine_block(vol, batch.get("realm_floor"), ctx)
        + _special_blocks(ctx, cfg, gbs, gbe)
        + _beat_rules(cfg, ctx)
        + _expand_rules(cfg, gbs, ctx) + "\n"
        "返回 JSON（两块，元素数都是 "
        f"{count}，章号都是全书第{gbs}～{gbe}章）：\n"
        f"★硬性数量★：beat_sequence 与 chapter_outlines 必须各恰好 {count} 个元素，"
        "逐章完整展开，禁止只写大爆点/跳章摘要/合并多章为一章。\n"
        "{\n"
        '  "beat_sequence": [\n' + _beat_skeleton(cfg, gbs) + "\n  ],\n"
        '  "chapter_outlines": [\n  '
        + _chapter_skeleton(gbs).replace("\n", "\n  ") + "\n  ]\n"
        "}"
        + _REALM_NOTE
    )
    return _chapter_system(cfg) + _VOLUME_SYS_ADDENDUM, user


# ── 定向修复（linter 问题回灌）────────────────────────────────────────────────

_REPAIR_SYS = SYS_BASE + (
    "\n\n【章纲修复专项】你收到的是已生成章纲中被质检拦下的问题章。"
    "只修问题字段、保住已合格的骨架：chapter_number / realm_rank 不得改动，"
    "shuang_type / location 仅在质检点名同质化时才换。只返回修正后的章 JSON 数组。"
)


def chapter_repair(ctx: dict, cfg: DabaiConfig) -> tuple[str, str]:
    """对 lint 出问题的章做定向重写。依赖 ctx['_repair'] = {chapters, issues, neighbors}。"""
    rep = ctx.get("_repair", {})
    chapters = rep.get("chapters") or []
    issues = rep.get("issues") or []
    neighbors = rep.get("neighbors") or []
    vol = ctx.get("_target_volume", {})
    issue_lines = "\n".join(
        f"  - 第{i.get('chapter')}章 [{i.get('rule_id')}] {i.get('message')}"
        + (f"（改法：{i.get('suggestion')}）" if i.get("suggestion") else "")
        for i in issues
    )
    neighbor_lines = "\n".join(
        f"  第{nb.get('chapter_number')}章《{nb.get('title', '')}》"
        f"场景:{nb.get('location', '')} 爽点:{nb.get('shuang_type', '')}"
        for nb in neighbors
    )
    opening_hint = ""
    if any(i.get("rule_id") == "DB-17" for i in issues):
        from dabai.plot_blueprint import ch1_opening_guidance_block

        guidance = ch1_opening_guidance_block(ctx).strip()
        if guidance:
            opening_hint = f"\n{guidance}\n"
        else:
            vols = ctx.get("volumes") or []
            v1 = vols[0] if vols else {}
            extra = v1.get("extra") or {}
            setup = (extra.get("opening_setup") or v1.get("opening_setup") or "").strip()
            if setup:
                opening_hint = f"\n【卷1 opening_setup（第1章 yaqu 须对齐）】\n{setup}\n"
    user = (
        f"{ctx_brief(ctx)}\n"
        + chapter_design_context(ctx, vol.get("volume_number"))
        + opening_hint
        + "\n【质检问题清单（逐条修复）】\n" + issue_lines + "\n"
        + ("\n【相邻章（用于满足轮换规则，本身不要返回）】\n" + neighbor_lines + "\n"
           if neighbor_lines else "")
        + "\n【待修复章纲（原文）】\n"
        + json.dumps(chapters, ensure_ascii=False, indent=1)
        + "\n\n修复要求：\n"
        "1. 只返回上述待修复章（同 chapter_number），JSON 数组，字段结构与原文一致；\n"
        "2. 逐条对照问题清单修复；未被点名的字段尽量保持原样；\n"
        "3. 修复后仍须满足：相邻章 shuang_type/location 轮换、witnesses ≥1、"
        "end_hook 具体、emotion_turn 有扳机、realm_rank 不变。"
    )
    return _REPAIR_SYS, user
