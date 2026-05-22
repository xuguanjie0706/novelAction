"""
transition_advisor.py — 开篇衔接策略知识库

设计动机（来自资深作家视角）：
  网文最常见的"AI 味"有两个根源：①跨章地理跳变，②破境场景千篇一律。
  本模块把经过验证的叙事衔接技法编码为结构化知识，注入 pre_write_warning 的提示词，
  让主编 AI 能在 writing_brief 和专属 transition_directive 字段中给出可执行指令。

与现有系统的连接：
  - gated_draft_helpers._run_pre_write_warning_inline 调用 build_transition_menu_block()
    将技法菜单注入 pre_write_warning prompt
  - writing_tools.pre_write_warning 多一个输出字段 transition_directive
  - _build_pre_warn_prompt_block 渲染 transition_directive 为「▍开篇衔接策略」块

无额外 LLM 调用：全部为纯数据与字符串拼接；复杂判断交由 pre_write_warning 的"30年主编" AI。
"""

from __future__ import annotations

# ═══════════════════════════════════════════════════════════════════════════
# 空间衔接技法库（4种，覆盖99%场景）
# ═══════════════════════════════════════════════════════════════════════════

SPATIAL_TECHNIQUES: list[dict] = [
    {
        "id": "sensory_anchor",
        "name": "感官锚定法",
        "scenario": "位置变化但时间间隔极短（同场）或无需解释的隐性转场",
        "technique": (
            "开篇直接用目标地点的标志性感官细节切入，"
            "不写'走到X'——读者会从感官差异自动感知场景切换。"
        ),
        "template": "[地点感官基准1句]。[主角动作/观察]，[引出本章第一个信息点]。",
        "anti_pattern": "禁止写'苏辰走进X，发现Y'——'走进'是废话过渡，删掉直接写进入后的状态。",
    },
    {
        "id": "time_stamp",
        "name": "时间标注法",
        "scenario": "章间存在2-24小时以上的时间跳跃，角色需要重新出现在新地点",
        "technique": (
            "首句使用时间状语 + 地点破折号结构作为「场景切换标志符」。"
            "读者习得此格式后会自动理解为新场景，无需额外解释。"
        ),
        "template": "[X日后 / 翌日清晨 / 三个时辰后]，[地点]——[主角状态/动作]。",
        "anti_pattern": "禁止写'时间飞逝，X天后苏辰来到了Y'——冗长且破坏节奏。",
    },
    {
        "id": "result_first",
        "name": "结果切入法",
        "scenario": "任务完成/传送/强制移动后抵达新地点，过程不重要",
        "technique": (
            "从到达新地点后的结果状态切入，倒叙式暗示'他已完成了位移'，"
            "绝不写抵达过程。读者关注的是'到了哪里发生了什么'而不是'怎么走过去的'。"
        ),
        "template": "回到[地点]，[主角已处于某状态]。[直接引出本章核心冲突]。",
        "anti_pattern": "禁止补写赶路过程除非赶路本身是本章内容。",
    },
    {
        "id": "pov_switch",
        "name": "视角切换法",
        "scenario": "多视角叙事中切换到另一个角色的POV，或需要外部视角见证主角抵达",
        "technique": (
            "用配角或观察者的视角开篇，描述他们'看到/感知到'主角出现在新地点，"
            "既完成空间交代又带来意外感。"
        ),
        "template": "[配角名]正在[某动作]，突然[感知主角出现]。[切回主角视角]。",
        "anti_pattern": "视角切换必须有叙事价值，不能只是为了交代位置而切视角。",
    },
]

# ═══════════════════════════════════════════════════════════════════════════
# 境界破境衔接技法库（3种）
# ═══════════════════════════════════════════════════════════════════════════

REALM_TECHNIQUES: list[dict] = [
    {
        "id": "physical_three_step",
        "name": "体感三步法",
        "scenario": "主动冲关/闭关突破/战斗中被动突破",
        "technique": (
            "分三个层次写破境体感，每层1-3句，禁止跳过任何层次：\n"
            "  ①【积压爆发】：体内灵力/能量达到临界点的身体感知（温度/震颤/压迫感）\n"
            "  ②【壁垒崩碎】：旧境界屏障瓦解的具体意象（碎裂声/光芒/黑暗消散）\n"
            "  ③【新感知降临】：进入新境界后世界的变化（敌人变弱小/感知范围扩大/新能力涌现）"
        ),
        "template": (
            "①[灵力/能量]如[意象]般在[部位]涌动，[身体反应1-2句]。\n"
            "②[某种象征性意象]轰然崩碎，[旧限制消失的感知]。\n"
            "③天地仿佛[新视角]，[具体感知变化]，他知道——[确认破境]。"
        ),
        "anti_pattern": (
            "禁止：①跳过体感直接说'他突破了X境'（告知型，AI味最重）；"
            "②全程只有光芒/震动的套路描写；③破境超过800字（破境是节点不是主场）。"
        ),
    },
    {
        "id": "external_witness",
        "name": "外力见证法",
        "scenario": "服用丹药/机缘获得/他人传功导致的被动突破",
        "technique": (
            "让配角或环境先于主角'感知到'突破发生，造成外部→内部的叙事顺序。"
            "主角最后确认，而非最先宣告——避免自说自话的自恋式独白。"
        ),
        "template": (
            "周围[人/环境]先出现[异常反应]。\n"
            "苏辰自己还未意识到，直到[某外部信号]——\n"
            "[主角内视/确认，1-2句]。[简短的新境界体感确认]。"
        ),
        "anti_pattern": "禁止：主角自己发表'我突破了/我变强了'的内心独白超过1句。",
    },
    {
        "id": "water_flows",
        "name": "水到渠成法",
        "scenario": "长期积累到达临界点，破境发生在某个情感/剧情的触发瞬间",
        "technique": (
            "破境的触发点必须是情感/意志/领悟，不是灵力量变。"
            "先用1-2句回溯积累感（不是流水账而是一个意象），"
            "再让情感事件成为临门一脚，破境如呼吸般自然。"
        ),
        "template": (
            "[积累感意象1句：如'那些在X的岁月像Y一样压在心头']。\n"
            "[情感触发点1句：看到/想到/听到某事]。\n"
            "[破境如水流般发生，主角几乎没有感觉，1-2句]。\n"
            "[外界/他人确认，1句]。"
        ),
        "anti_pattern": (
            "禁止：无缘无故灵力爆增导致破境（必须有情感/意志触发点）；"
            "禁止：破境后大篇幅内心独白总结成长历程（留到下章或留白）。"
        ),
    },
]


# ═══════════════════════════════════════════════════════════════════════════
# 对外接口
# ═══════════════════════════════════════════════════════════════════════════

def build_transition_menu_block(
    db_location: str,
    outline_power_milestone: str,
    has_location_update: bool = False,
) -> str:
    """
    构建注入 pre_write_warning 提示词的「衔接技法菜单」块。

    AI（30年主编模式）会根据本章上下文从菜单中选择最合适的技法，
    并在 transition_directive 字段给出可执行的具体指令。

    @param db_location:            角色 DB 记录的当前位置（可能滞后）
    @param outline_power_milestone: 本章大纲的实力里程碑字段（空=无破境）
    @param has_location_update:    是否本章预期有位置变化（来自大纲推断）
    @returns 格式化的技法菜单文本块（注入 pre_write_warning prompt）
    """
    spatial_menu = "\n".join(
        f"  [{t['id']}]《{t['name']}》"
        f" | 适用：{t['scenario']}\n"
        f"    模板：{t['template']}\n"
        f"    禁忌：{t['anti_pattern']}"
        for t in SPATIAL_TECHNIQUES
    )
    realm_menu = "\n".join(
        f"  [{t['id']}]《{t['name']}》"
        f" | 适用：{t['scenario']}\n"
        f"    模板：{t['template']}\n"
        f"    禁忌：{t['anti_pattern']}"
        for t in REALM_TECHNIQUES
    ) if outline_power_milestone else "（本章大纲无实力里程碑，无需破境衔接）"

    location_note = (
        f"⚠️ 角色 DB 记录位置：「{db_location}」\n"
        "   注意：若复盘未及时运行，此记录可能滞后于实际叙事位置。\n"
        "   请根据上章记忆/大纲判断本章真实起点，若起点≠DB记录，必须选用空间衔接技法。"
        if db_location else
        "（无 DB 位置记录，根据上章内容和大纲判断起点）"
    )

    realm_note = (
        f"本章大纲实力里程碑：「{outline_power_milestone}」——本章将发生境界突破，必须使用破境衔接技法。"
        if outline_power_milestone else ""
    )

    lines = [
        "\n══════════════════════════════════════",
        "【开篇衔接需求分析（在 transition_directive 字段给出选择）】",
        "",
        "▷ 空间衔接",
        location_note,
        "",
        "可用技法（从中选最合适的一种，填入 transition_directive.spatial_bridge）：",
        spatial_menu,
    ]

    if outline_power_milestone:
        lines += [
            "",
            "▷ 境界破境衔接",
            realm_note,
            "",
            "可用技法（从中选最合适的一种，填入 transition_directive.realm_bridge）：",
            realm_menu,
        ]

    lines.append("══════════════════════════════════════")
    return "\n".join(lines)


def build_transition_directive_schema() -> str:
    """
    返回注入 pre_write_warning JSON schema 的 transition_directive 字段定义。
    供 writing_tools.py 插入到 AI 的 JSON 输出规范中。
    """
    return '''"transition_directive": {
    "spatial_bridge": {
      "needed": true/false,
      "technique_id": "sensory_anchor|time_stamp|result_first|pov_switch",
      "technique_name": "技法名称",
      "instruction": "本章开篇第一段的具体执行指令（一到两句，可执行）"
    },
    "realm_bridge": {
      "needed": true/false,
      "technique_id": "physical_three_step|external_witness|water_flows|none",
      "technique_name": "技法名称或'无需破境'",
      "instruction": "破境段落的具体执行指令（分步骤）"
    }
  }'''
