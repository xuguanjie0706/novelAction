"""斗破式大白文玄幻线（mode=doupo）专属 prompt 集合。

设计动机
--------
本线对标《斗破苍穹》式「斗气大陆」纯爽文：力量体系是斗气等级（斗者→斗帝），
**不是修仙灵气/天劫/飞剑/渡劫**；叙事贴地、限制视角、白话直给，**禁止上帝旁白**
（「殊不知 / 命运的齿轮 / 多年以后他才知道」一类全知视角辞藻）。

与通用线的关系
--------------
doupo 完全基于「通用（sequential）」线：复用通用 project / storylines / antagonist /
characters / skills_items / volumes / memory / mysteries / opening_contract / consistency
等中立步骤，仅在三处做题材语义替换（立项 / 单斗气主轴 / 精简世界卡）+ 一处合并
（势力+卷级对立面），另对共享 volumes 步骤挂一个「大纲质量增强」prompt hook。零番茄代码耦合。

> 注：势力/功法/法宝的安排——功法/法宝要精确挂人物 UUID，须在人物建档之后生成，
> 故不与势力同批；势力+卷级对立面合并为一次 LLM（人物前），功法+法宝走通用 CORE
> ``skills_items``（人物后）。详见 steps/doupo/factions_antagonist_doupo.py 头注。

红线：本文件 ≤ 600 行。
"""
from __future__ import annotations

# ──────────────────────────────────────────────────────
# 公共：禁上帝视角 + 白话直白铁律（多处复用）
# ──────────────────────────────────────────────────────

NO_GOD_VIEW_RULE = (
    "【斗破式大白文·叙事铁律（所有产物共同遵守）】\n"
    "1. 力量体系是『斗气』，等级感来自斗气阶位与斗技品阶，**严禁**写成修仙："
    "不准出现灵气/灵根/经脉/金丹/元婴/渡天劫/飞剑御空/破碎虚空成仙一类修仙母题。\n"
    "2. 全程贴地、限制视角：只写主角（或当前视点人物）当下能看到、听到、想到的东西。"
    "**严禁上帝旁白**——不准写『殊不知』『命运的齿轮开始转动』『多年以后他才明白』"
    "『此时无人知晓』『冥冥之中』这类全知/预叙辞藻。\n"
    "3. 白话直给：句子短、信息密度低、读一遍就懂；新名词就近用一句大白话解释。"
    "禁止意境堆砌、禁止含蓄留白、禁止文绉绉的形容。\n"
    "4. 爽点直白可感：变强/打脸/夺宝/扮猪吃虎，要写清『谁、对谁、凭什么、爽在哪』，"
    "不要把高光藏在隐喻里。"
)


# ──────────────────────────────────────────────────────
# Step 0：斗破式立项（产物字段对齐 xianxia positioning schema，复用其校验）
# ──────────────────────────────────────────────────────

def build_doupo_positioning_prompt(*, logline: str, premise: str) -> str:
    """斗破式立项 prompt：输出与 BootstrapXianxiaPositioning 同字段的 JSON 对象。"""
    return f"""你是深耕番茄男频「斗破苍穹式斗气大陆」纯爽文的资深主编。
现在要为下面这条创意召开立项会议，**只返回一个 JSON 对象**，不要任何解释。

一句话创意：{logline}
补充设定：{premise or "（无）"}

请用斗气大陆纯爽文的第一性原理立项——爽感引擎是『斗气等级的爬升 + 越阶斗技碾压 +
炼药/异火/古帝传承式金手指 + 扮猪吃虎打脸』，绝不是修仙渡劫成仙，也绝不是社交宫斗。

只返回如下结构（值全部用大白话，禁止文绉绉）：
{{
  "subgenre": "斗气大陆细分类型（如：家族崛起流 / 学院流 / 废材逆袭流 / 炼药师流），一句话",
  "core_satisfaction": "本书最核心、贯穿全书的爽感是什么（一句话讲清，例：从被退婚的废柴一路斗气越阶把曾经羞辱他的人全踩在脚下）",
  "progression_fantasy": "升级幻想曲线：主角从什么阶位起步、靠什么手段一路爬到什么阶位（写斗气阶位，不写修仙境界）",
  "tension_source": "冲突/张力的主要来源（家族倾轧 / 强敌追杀 / 资源争夺 / 婚约羞辱 等，写具体）",
  "opening_fortune": "开局机缘/金手指是什么、怎么到主角手里（例：神秘老者的灵魂寄居在戒指里、一缕异火、一本古帝残卷）",
  "power_fantasy_curve": "升级碾压节奏（例：每3章一次小越阶压制，每10-15章一次大阶位突破+打脸高潮）",
  "reader_tags": ["读者一眼能认的标签，3-6个，如 废材逆袭、扮猪吃虎、炼药师、异火、退婚流"],
  "completion_hook": "追读钩子：开局凭什么让读者第一章就想追下去（一句话）",
  "taboo_check": "本书要避开的雷点（一句话，例：禁止主角圣母、禁止拖沓、禁止修仙化）"
}}
注意：subgenre 与 core_satisfaction 必填且不能空。全部字段说人话。"""


def doupo_to_generic_positioning(dp: dict) -> dict:
    """斗破立项 → 通用 positioning（供中立复用步骤 gen_project / storylines / memory 读取）。

    pace_type 固定 fast、writing_style 固定 plain；face_slap_pattern 用『越阶碾压打脸节奏』，
    emotional_arc 用斗气升级曲线。字段名沿用通用契约以保证下游零改动。
    """
    return {
        "target_audience": f"番茄男频·斗气大陆{dp.get('subgenre', '')}读者",
        "tropes": dp.get("reader_tags", []),
        "reference_works": ["斗破苍穹式斗气大陆爽文"],
        "selling_point": dp.get("core_satisfaction", ""),
        "face_slap_pattern": dp.get("power_fantasy_curve", "")
        or "每3章一次小越阶压制，每10-15章一次大阶位突破+当众打脸",
        "emotional_arc": f"斗气升级曲线：{dp.get('progression_fantasy', '废材→斗帝')}",
        "pace_type": "fast",
        "writing_style": "plain",
        "taboo_lines": (
            [str(dp["taboo_check"])] if dp.get("taboo_check") else ["禁止修仙化、禁止上帝视角旁白"]
        ),
    }


# ──────────────────────────────────────────────────────
# Step 2：单斗气主轴（replaces 通用 power_systems 的修仙多轴）
# ──────────────────────────────────────────────────────

def build_doupo_power_axis_prompt(ctx: dict) -> tuple[str, str]:
    """单条斗气主轴 prompt：返回 (system, prompt)；产物为 PowerSystem 旧格式 JSON 数组。"""
    system = (
        "你是斗气大陆纯爽文的力量体系架构师，深知读者的爽感来自『阶位爬升 + 越阶碾压』。"
        "只返回一个 JSON 数组，不要任何解释文字。"
    )
    dp = ctx.get("doupo_positioning") or {}
    prompt = f"""{NO_GOD_VIEW_RULE}

为这本斗气大陆爽文设计**唯一一条**力量主轴（斗气阶位体系），不要任何平行/副轴。
小说定位：{dp.get('subgenre', '斗气大陆玄幻')}
核心爽感：{dp.get('core_satisfaction', '越阶碾压、打脸逆袭')}
升级曲线：{dp.get('progression_fantasy', '废材起步，一路斗气越阶')}

要求：
- 一条主轴 9~11 个大阶位，由低到高严格递增；命名走斗气大陆风（参考但不照抄：斗者/斗师/
  大斗师/斗灵/斗王/斗皇/斗宗/斗尊/半圣/斗圣/斗帝），可适度自创以避免雷同，但必须一眼能懂高低。
- 每个阶位给一句大白话说明『到了这一阶能做到什么、和上一阶差在哪』，禁止修仙化描述。
- 升级靠『吞噬天地斗气淬炼斗之气、服食丹药、修炼斗技/功法』，**不是吸灵气、不渡天劫**。
- 突破代价要真实：越往上越难、需要资源/瓶颈/外力，杜绝随便就突破。

只返回如下 JSON 数组（数组里通常只有 1 个对象＝主轴）：
[
  {{
    "name": "主轴名称（如：斗气大陆斗者体系）",
    "system_type": "cultivation",
    "axis_role": "primary",
    "description": "这条斗气体系是什么、怎么变强（60字内，大白话）",
    "cultivation_method": "修炼方式（吞噬/淬炼斗之气 + 修炼斗技 + 丹药辅助，40字内）",
    "breakthrough_condition": "突破/越阶的通用条件与代价（40字内，禁止渡劫飞升）",
    "special_rules": "斗气大陆通用规则（如：异火榜、斗技品阶=黄玄地天、炼药师地位崇高，60字内）",
    "protagonist_start_rank": 1,
    "protagonist_end_rank": 9,
    "levels": [
      {{"name": "阶位名（从低到高第1个）", "rank": 1, "description": "一句大白话：到这一阶能干什么"}},
      {{"name": "阶位名（第2个）", "rank": 2, "description": "……"}}
    ]
  }}
]
levels 必须 9~11 项、rank 从 1 严格递增不重复。
protagonist_start_rank 取主角开局阶位（通常 1~2，废材流可为 1），
protagonist_end_rank 取全书结局阶位（接近但不必到顶，给后续留空间）。
只返回 JSON 数组，不要说明文字。"""
    return system, prompt


# ──────────────────────────────────────────────────────
# Step 8：精简斗气大陆世界设定卡（replaces 通用 settings）
# ──────────────────────────────────────────────────────

# 「设定内容减少」：只保留斗气大陆纯爽文最必要的 6 张蓝图（通用线默认 ~10+ 张）。
DOUPO_BLUEPRINT_TITLES = (
    "作品立意",                # 一句话锁主题与读者承诺
    "世界底层规则",            # 斗气根基（替代修仙灵气）
    "时代格局与阶层结构",      # 家族/学院/势力的强弱与压迫
    "突破副作用与失败代价",    # 越阶代价，防升级廉价化
    "资源经济与稀缺机制",      # 丹药/异火/斗技传承的争夺
    "远古战争与失落真相",      # 主角金手指/传承的来源 + 全书级悬念
)

DOUPO_SETTINGS_ADDON = (
    "【斗气大陆世界设定铁律（精简版，只写必要的）】\n"
    "1. 底层力量统一是『斗气』：靠吞噬淬炼天地斗气、服丹、练斗技变强。"
    "**严禁**灵气/灵根/经脉/金丹/渡劫/飞剑/成仙等修仙设定。\n"
    "2. 『突破副作用与失败代价』卡要写清：每次大阶位越级要过什么瓶颈、要多少斗气/丹药/外力，"
    "越往上越难——变强必须有阻力。\n"
    "3. 『资源经济』卡要落地丹药、异火榜、斗技品阶、炼药师地位这条争夺链，它是夺宝/暴富爽点的燃料。\n"
    "4. 每张卡都要大白话直给：给得出可直接写进正文的名词、规则、代价、冲突；"
    "禁止意境堆砌、禁止上帝旁白。\n"
    "5. 与斗气主轴、金手指咬合：能被金手指利用或制约的设定，请在 content 里点明。"
)


# ──────────────────────────────────────────────────────
# 共享 volumes 步骤的 prompt hook：斗破式大纲质量增强块
# ──────────────────────────────────────────────────────

def build_doupo_volumes_block(ctx: dict) -> str:
    """挂在共享 volumes 步骤上的「大纲质量增强 + 斗气节奏预算」块。

    由 collect_step_hooks("volumes", ctx) 在 build_volumes_prompt 内收集拼接。
    目标：让卷骨架更合理（斗气进度逐卷分摊、杜绝第一卷爬满）、更直白、有强钩子。
    全书章数/卷数/各卷 planned_chapters 统一走 ``doupo_volume_chapter_plan(target_words)``。
    """
    from app.services.outline_planning import (
        TARGET_WORDS_PER_CHAPTER,
        doupo_volume_chapter_plan,
    )

    tw = int(ctx.get("target_words") or 1_200_000)
    plan = doupo_volume_chapter_plan(tw)
    total_vols = plan["total_volumes"]
    total_chapters = plan["total_chapters"]
    quotas: list[int] = plan["chapter_quotas"]

    quota_lines = []
    for i, q in enumerate(quotas):
        note = "（开局卷·钩子密、节奏快）" if i == 0 and len(quotas) > 1 else ""
        quota_lines.append(f"  第{i + 1}卷：planned_chapters={q}{note}")
    book_block = (
        "\n【全书篇幅（与建书 target_words 锁定，planned_chapters 必须逐卷照填）】\n"
        f"  全书目标：{plan['target_words']:,}字 / 约{total_chapters}章"
        f"（每章约{TARGET_WORDS_PER_CHAPTER}字）/ {total_vols}卷\n"
        "  卷章配额：第1卷30章快节奏开局，第2～末-1卷各60章，末卷取剩余章数。\n"
        + "\n".join(quota_lines)
        + f"\n  ⚠️ 返回 JSON 数组长度必须等于 {total_vols}；"
        f"各卷 planned_chapters 必须与上表完全一致，不得自编或均分。\n"
    )

    names: list[str] = ctx.get("power_level_names") or []
    budget_line = ""
    if names:
        n = len(names)
        start = 0
        end = max(start, n - 2)  # 结局不必到顶，给续作留空间
        span = max(1, end - start)
        per_vol = max(1, round(span / max(1, total_vols)))
        caps: list[str] = []
        for v in range(1, total_vols + 1):
            cap_idx = min(end, start + per_vol * v)
            caps.append(f"卷{v}≤{names[cap_idx]}")
        budget_line = (
            "\n【斗气进度预算（逐卷封顶，杜绝『第一卷就爬满』）】\n"
            f"主轴阶位（低→高）：{' < '.join(names)}\n"
            f"主角开局约在『{names[start]}』，全书结局约到『{names[end]}』，不要写到最顶阶。\n"
            f"各卷主角斗气阶位**上限**建议：{'；'.join(caps)}。\n"
            "每卷只允许小步爬升，大阶位突破要留到卷末高潮，并配代价与铺垫。\n"
        )

    return (
        f"{NO_GOD_VIEW_RULE}\n"
        f"{book_block}"
        "【斗破式卷大纲质量铁律（务必逐条满足）】\n"
        "1. 每卷一个清晰的『核心目标 + 主要对手 + 卷末高潮打脸/突破』，一句话能讲清这卷在爽什么。\n"
        "2. 卷与卷强承接：上一卷结尾留的钩子（仇敌、宝物线索、身世谜团）必须在下一卷被接住，"
        "禁止断裂、禁止重复刷同一种冲突。\n"
        "3. 反派按卷升级成阶梯：每卷 Boss 的斗气阶位/势力层级都比上一卷高一档，主角靠成长去够。\n"
        "4. beat_highlights 燃点与 volume_climax 高潮一律大白话直给：写清『谁、和谁、为什么打、"
        "主角凭什么赢、爽在哪』，禁止含蓄留白、禁止上帝旁白。\n"
        "5. 节奏合理：第一卷仅30章，钩子更密、爽点 3~5 章一次；后续各卷60章，每卷至少一次明确打脸或越阶碾压。"
        f"{budget_line}"
    )
