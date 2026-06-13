"""金手指绑定节拍：疑 → 证 → 择（系统/传承/天赋等首次觉醒章通用）。

番茄系统流可以快，但须占以下捷径之一，否则读者会觉得「接受太快」：
  1. meta 人设（穿越者熟读网文，快=人设）；
  2. 机制强绑（濒死无否决权，快=规则）；
  3. 即时身体验证（止痛/锁链松/止血，快=被迫信）；
  4. 疑证择三步（非穿越主角的默认解法，150～250 字即可）。

本模块供章纲 prompt、正文 prompt、linter 共用。
"""

from __future__ import annotations

# 章纲 emotion_turn / 正文须能对应的三拍标记（linter 抽样用）
_DOUBT_MARKERS = ("疑", "幻觉", "鬼叫", "不信", "心魔", "做梦", "恍惚", "诈死")
_PROOF_MARKERS = ("证", "验证", "烫", "松", "止血", "倒计时", "止疼", "意识", "拽回", "精血", "幡面", "灌脑", "暖流")
_CHOICE_MARKERS = ("择", "赌", "挤", "被迫", "强绑", "否决", "提取", "绑定", "接受")
_META_MARKERS = ("穿越", "熟读", "网文", "套路", "等的就是")

# 法器流首次认主信号（非系统 UI）
_ARTIFACT_AWAKENING_MARKERS = (
    "认主", "血祭", "精血", "灌脑", "魔诀", "灌入脑海", "血炼",
)
# 首次绑定/觉醒信号（章纲字段须出现，不能仅靠全书金手指名）
_FIRST_AWAKENING_MARKERS = (
    "觉醒", "绑定", "锁定", "首次", "激活", "倒计时", "机械音", "传承", "外挂",
    "金手指", "接入", "载入", "启动",
    *_ARTIFACT_AWAKENING_MARKERS,
)
# 系统流专用（法器流章纲不应依赖「叮」判定觉醒章）
_SYSTEM_AWAKENING_MARKERS = ("叮",)
_FIRST_USE_MARKERS = ("发动", "首用", "首战", "第一次")
# 熟练使用期：打脸/升级戏，不应再套 DB-10
_MATURE_USE_MARKERS = (
    "吸干", "转化", "再跳", "修为点", "闻丹", "捏碎", "撒碎", "休了你", "当面休",
)

# 反败为胜/逆袭类章节信号（payoff 须有「能赢的依据」铺垫，否则读者觉得开挂硬翻）
_REVERSAL_MARKERS = (
    "反败为胜", "逆袭", "翻盘", "反杀", "绝地反击", "扮猪吃虎", "以弱胜强",
    "反压制", "绝处逢生", "触底反弹", "弱势翻", "逆风翻盘", "反制",
)
# 金手指进阶/解锁新能力里程碑信号（首次觉醒之外，任意章节）
_GF_EVOLUTION_MARKERS = (
    "进化", "升级", "解锁", "新能力", "第二阶段", "觉醒新", "晋阶", "二段",
    "突破上限", "蜕变", "新形态", "新功能", "新权限", "新模块",
)

# 关键反转/获得须兑现前文铺垫（②③共用：注入 bind / reversal 脚手架末尾）
_SETUP_CONSUME_LINE = (
    "  ★铺垫依据（立得住）：本章关键反转/获得须兑现【既定事实记忆】或【未回收线索】中"
    "已埋的一条；若前文确无铺垫，至少当场补一句立得住的依据（来历/代价/限制/破绽），"
    "禁止凭空逆袭、禁止临场冒出全新能力。★\n"
)


def is_reversal_chapter(ch: dict) -> bool:
    """章纲是否为反败为胜/逆袭类章节（payoff 须有「能赢的依据」铺垫）。"""
    blob = " ".join([
        ch.get("title") or "",
        ch.get("shuang_type") or "",
        ch.get("yinbao") or "",
        ch.get("shuang_payoff") or ch.get("payoff") or "",
        ch.get("emotion_turn") or "",
    ])
    return any(m in blob for m in _REVERSAL_MARKERS)


def is_gf_evolution_chapter(ch: dict, *, golden_finger_name: str = "") -> bool:
    """金手指进阶/解锁新能力里程碑（任意章节；区别于首次觉醒与熟练打脸）。

    仅在出现明确进阶词且语境与金手指相关时为真，降低对普通打脸章的误报。
    """
    blob = " ".join([
        ch.get("title") or "",
        ch.get("yinbao") or "",
        ch.get("shuang_payoff") or ch.get("payoff") or "",
        ch.get("emotion_turn") or "",
        ch.get("yaqu_setup") or "",
    ])
    if not any(m in blob for m in _GF_EVOLUTION_MARKERS):
        return False
    gf = (golden_finger_name or "").strip()
    if gf and gf in blob:
        return True
    return any(
        k in blob for k in ("系统", "金手指", "能力", "外挂", "传承", "功法", "神通")
    )


def is_awakening_chapter(
    ch: dict,
    *,
    golden_finger_name: str = "",
    golden_chapters: int = 3,
    artifact: bool = False,
) -> bool:
    """章纲是否属金手指首次登场/绑定/首战章（仅黄金前段 + 本章字段启发式）。"""
    num = int(ch.get("chapter_number") or 0)
    if num < 1 or num > golden_chapters:
        return False
    ch_blob = " ".join([
        ch.get("title") or "",
        ch.get("yinbao") or "",
        ch.get("end_hook") or "",
        ch.get("emotion_turn") or "",
        ch.get("yaqu_setup") or "",
    ])
    if any(m in ch_blob for m in _MATURE_USE_MARKERS):
        return False
    if any(m in ch_blob for m in _FIRST_AWAKENING_MARKERS):
        return True
    if not artifact and any(m in ch_blob for m in _SYSTEM_AWAKENING_MARKERS):
        return True
    if any(m in ch_blob for m in _FIRST_USE_MARKERS):
        return True
    # 金手指名仅作弱信号：须本章同时出现「系统」+ 脑中提示类场景
    gf = (golden_finger_name or "").strip()
    if gf and any(k in gf for k in ("系统", "传承", "外挂")):
        if "系统" in ch_blob and any(
            u in ch_blob for u in ("脑中", "脑海", "响起", "提示", "濒死", "锁定")
        ):
            return True
    return False


def bind_ladder_emotion_turn_hint(gf_name: str = "金手指", *, artifact: bool = False) -> str:
    """章纲 emotion_turn 模板（写入 prompt 示例）。"""
    if artifact:
        return (
            f"从麻木/濒死→疑为血炼魔器夺命（疑）→精血狂泄或幡面异动可验证（证）"
            f"→赌命认主或魔诀灌脑接受（择）→{gf_name}生效"
        )
    return (
        f"从濒死恍惚→疑为幻觉/鬼叫（疑）→倒计时或身体微证如止血/锁链松（证）"
        f"→赌命或被迫说出接受指令（择）→{gf_name}生效"
    )


def chapter_outline_bind_block(gf_name: str = "", *, artifact: bool = False) -> str:
    """注入章纲 prompt 的硬约束块。"""
    hint = bind_ladder_emotion_turn_hint(gf_name or "金手指", artifact=artifact)
    proof_line = (
        "  证：给一个即时可验证的反馈（精血骤止、幡面修补、魔诀灌脑、暖流入体）；\n"
        if artifact else
        "  证：给一个即时可验证的身体反馈（倒计时压迫、止痛、锁链松一分、意识被拽回）；\n"
    )
    sys_note = (
        "  ★法器流禁止写「叮」/系统面板；绑定靠血祭认主或魔诀灌脑。★\n"
        if artifact else ""
    )
    return (
        "\n【金手指绑定节拍 · 黄金章专用】\n"
        "若本章为金手指首次觉醒/绑定或首战使用（非熟练打脸章），emotion_turn 必须写清「疑→证→择」：\n"
        "  疑：先怀疑（幻觉、心魔、鬼叫、血炼夺命），禁止一句就全信；\n"
        + proof_line +
        "  择：主角主动但克制地选择（赌命认主/挤出接受），或器物濒死强吸精血（无否决权）。\n"
        + sys_note +
        f"  示例 emotion_turn：{hint}\n"
        "  触发条件须对齐主角当下情绪（复仇/不甘/濒死/麻木），禁用与剧情无关的套话。\n"
    )


def prose_bind_instructions(*, gf_name: str = "", is_meta_protagonist: bool = False, artifact: bool = False) -> str:
    """注入正文写作的补充硬约束。"""
    if is_meta_protagonist:
        return (
            "\n【金手指绑定】主角有网文/穿越认知，可较快接受，但仍须一句点明「等的就是这个」"
            "，禁止无铺垫的疯狂咆哮式同意。\n"
        )
    name = gf_name or "金手指"
    if artifact:
        return (
            "\n【金手指绑定节拍 · 法器流 · 本章硬约束】\n"
            f"「{name}」认主/灌脑须按序写清（约 150～250 字，可快但不可跳）：\n"
            "  ① 疑：先疑为血炼夺命或幻觉，勿秒懂全套机制；\n"
            "  ② 证：精血骤止、幡面异动、魔诀灌脑或暖流入体等可感反馈；\n"
            "  ③ 择：赌命认主、被迫放血或咬牙接受灌脑；禁止「叮」/面板/任务栏。\n"
            + _SETUP_CONSUME_LINE
        )
    return (
        "\n【金手指绑定节拍 · 本章硬约束】\n"
        f"「{name}」首次提示出现后，正文须按序写清（合计约 150～250 字，可快但不可跳）：\n"
        "  ① 疑：主角先怀疑（幻觉/鬼叫/心魔），勿秒懂「系统」全套语法；\n"
        "  ② 证：即时身体反馈（倒计时、止痛、锁链松、意识回拢等）让读者与主角同信；\n"
        "  ③ 择：主动选择用挤出/哑声/赌命，或系统濒死强绑；禁止「虽然不知道这是什么"
        "但疯狂咆哮提取」式硬切。\n"
        "  触发文案对齐当下情绪（不甘/复仇/濒死），勿写无关的「吞噬欲望」。\n"
        + _SETUP_CONSUME_LINE
    )


def prose_earned_reversal_instructions(*, artifact: bool = False) -> str:
    """反败为胜/逆袭章正文硬约束：让翻盘「立得住」，而非凭空开挂硬翻。

    与金手指绑定脚手架可叠加（既觉醒又翻盘的章节两块都注入）。
    """
    note = (
        "动用器物认主后的新威能/精血底牌"
        if artifact
        else "动用【系统面板】/【台账】里已具备的境界·技能·法宝"
    )
    return (
        "\n【反败为胜节拍 · 本章硬约束（让翻盘立得住，禁止凭空开挂）】\n"
        "  ① 劣势确立：先把主角的被动/代价写实（受制于谁、差距多大、输了会怎样），勿一笔带过；\n"
        f"  ② 翻盘依据：主角能赢必须有据可循——{note}、本章前文已埋的破绽/底牌，"
        "禁止临场冒出全新能力；\n"
        "  ③ 对手为何措手不及：给一个合理原因（轻敌、信息差、被引诱、规则盲区），"
        "别让对手无脑挨打；\n"
        "  ④ 代价/张力：翻盘带一点代价或险象（消耗、反噬、险胜），不要零成本碾压；\n"
        "  ⑤ 见证者反应分级递进（愣住→不信→震惊→心服/恐惧），落到章末钩子。\n"
        + _SETUP_CONSUME_LINE
    )


def lint_bind_ladder(emotion_turn: str, *, is_meta: bool = False) -> str | None:
    """检查 emotion_turn 是否含绑定三步；缺则返回 suggestion，否则 None。"""
    et = (emotion_turn or "").strip()
    if not et:
        return "补 emotion_turn：疑→证→择 三步（见 golden_finger_bind 模块）"
    if is_meta and any(m in et for m in _META_MARKERS):
        return None
    has_doubt = any(m in et for m in _DOUBT_MARKERS)
    has_proof = any(m in et for m in _PROOF_MARKERS)
    has_choice = any(m in et for m in _CHOICE_MARKERS) or "→" in et
    if not has_doubt:
        return "emotion_turn 缺「疑」拍：须写怀疑幻觉/心魔/鬼叫等"
    if not (has_proof or has_choice):
        return "emotion_turn 缺「证」或「择」：须写身体验证或被迫/赌命选择"
    return None
