"""dabai 写前导演单（pre-warn）共享格式件。

仅含与具体数据模型无关的纯格式逻辑：导演单 system 头 + JSON→注入块格式化，
供实验书架 ``lab_pre_warn`` 复用，避免依赖已退役的主链路 ``pre_warn`` 模块。
"""
from __future__ import annotations

_BEAT_KEYS = ("yaqu", "trigger", "yinbao", "payoff", "hook")
_BEAT_LABELS = {
    "yaqu": "①憋屈",
    "trigger": "②扳机",
    "yinbao": "③引爆",
    "payoff": "④爽点",
    "hook": "⑤钩子",
}

_PREWARN_SYSTEM = (
    "你是番茄/七猫大白文的责编兼导演，在作者落笔前出一份「导演单」。硬要求：\n"
    "1. 事实以【主角当前状态】【本章出场人物当前状态】【前情提要】【相关记忆】为准；\n"
    "1a. ★conflict_notes 只收录「真矛盾」——即：按章纲字面写就会与已写事实直接打架、"
    "读者一眼看出穿帮的硬伤。仅限这几类：已死/已离场的人物被要求出场；主角境界倒退或"
    "无依据跳级（与面板/记忆不符）；人物立场或状态明显相反（如前文已吓破胆/已臣服，"
    "章纲却让其逞凶/再敌对）；已消耗或已失去的资产被要求再用；地点或时间线硬冲突。\n"
    "1b. ★以下一律不算冲突，conflict_notes 留空 []，直接在 beat_execution 里按事实自然落笔即可："
    "章纲是粗线条而正文需补细节；情节顺势演进、措辞不同；程度或语气的轻微差异。"
    "宁可漏报，不要把正常细化写成「冲突裁决」；本章无硬伤就返回 []；\n"
    "2. 所有指令必须具体可执行（写什么、怎么切入），禁止「增强文采」「多留白」类建议；\n"
    "3. bridge_directives 只在确实存在位置/境界变化需要交代时给出，没有就留空数组，"
    "不要凭空编造移动；\n"
    "4. 每个字段一两句话，简短直接。只返回 JSON，不要任何额外文字。"
)


def format_prewarn_block(result: dict | None) -> str:
    """导演单 JSON → 正文 prompt 注入块；结构不完整时返回空串（降级无简报）。"""
    if not isinstance(result, dict):
        return ""
    fact = result.get("fact_lock") or {}
    beats = result.get("beat_execution") or {}
    if not isinstance(fact, dict) or not isinstance(beats, dict):
        return ""

    lines = [
        "【写前导演单（五拍落法与 fact_lock.realm_end 须一致；"
        "开笔境界以【系统面板】/开笔基准为准，高于章纲节拍字面）】",
    ]
    fact_parts = []
    if fact.get("realm"):
        realm_seg = str(fact["realm"])
        sub = fact.get("realm_sub_rank")
        if sub not in (None, "") and "·第" not in realm_seg:
            try:
                realm_seg = f"{realm_seg}·第{int(sub)}层"
            except (TypeError, ValueError):
                pass
        fact_parts.append(f"开笔境界：{realm_seg}")
    if fact.get("realm_end") and fact.get("realm_end") != fact.get("realm"):
        end_seg = str(fact["realm_end"])
        end_sub = fact.get("realm_end_sub_rank")
        if end_sub not in (None, "") and "·第" not in end_seg:
            try:
                end_seg = f"{end_seg}·第{int(end_sub)}层"
            except (TypeError, ValueError):
                pass
        fact_parts.append(f"章末目标：{end_seg}")
    elif fact.get("realm_end"):
        fact_parts.append(f"章末境界：{fact['realm_end']}")
    if fact.get("location"):
        fact_parts.append(f"位置：{fact['location']}")
    on_stage = [str(x) for x in (fact.get("on_stage") or []) if x]
    if on_stage:
        fact_parts.append(f"在场：{'、'.join(on_stage[:8])}")
    if fact_parts:
        lines.append(f"- 开笔事实锁定：{'；'.join(fact_parts)}")
    cast = [c for c in (result.get("cast") or []) if isinstance(c, dict) and c.get("name")]
    if cast:
        segs = []
        for c in cast[:8]:
            nm = str(c.get("name")).strip()
            rs = str(c.get("reason") or "").strip()
            segs.append(f"{nm}（{rs}）" if rs else nm)
        lines.append("- 本章出场人物及出场原因（只写这些人，按原因落到对应拍）：" + "；".join(segs))
    forbidden = [str(x) for x in (fact.get("forbidden") or []) if x]
    if forbidden:
        lines.append(f"- 禁止出现：{'；'.join(forbidden[:5])}")
    for note in [str(x) for x in (result.get("conflict_notes") or []) if x][:4]:
        lines.append(f"- 冲突裁决：{note}")
    for note in [str(x) for x in (result.get("setup_alignment") or []) if x][:4]:
        lines.append(f"- 开局写法对齐：{note}")
    opening = str(result.get("opening_directive") or "").strip()
    if opening:
        lines.append(f"- 开头写法：{opening}")
    setup = str(result.get("setup_check") or "").strip()
    if setup and setup not in ("无", "无关键反转", "none", "None", "N/A", "/"):
        lines.append(f"- 铺垫依据（反转/获得须立得住）：{setup}")
    beat_parts = [
        f"{_BEAT_LABELS[k]}：{str(beats.get(k)).strip()}"
        for k in _BEAT_KEYS
        if str(beats.get(k) or "").strip()
    ]
    if beat_parts:
        lines.append("- 五拍执行：" + "；".join(beat_parts))
    for bridge in [str(x) for x in (result.get("bridge_directives") or []) if x][:3]:
        lines.append(f"- 衔接交代：{bridge}")
    for spec in [s for s in (result.get("asset_specs") or []) if isinstance(s, dict)][:6]:
        name = str(spec.get("name") or "").strip()
        segs = [
            f"{lbl}：{str(spec.get(key)).strip()}"
            for key, lbl in (("usage", "用法"), ("cost", "代价"),
                             ("progression", "进阶"), ("restriction", "限制"))
            if str(spec.get(key) or "").strip()
        ]
        if name and segs:
            lines.append(f"- 技能/道具规格〔{name}〕（须照此写，不得另编）：{'｜'.join(segs)}")
    for rem in [str(x) for x in (result.get("reminders") or []) if x][:3]:
        lines.append(f"- 提醒：{rem}")
    return "\n".join(lines) if len(lines) > 1 else ""
