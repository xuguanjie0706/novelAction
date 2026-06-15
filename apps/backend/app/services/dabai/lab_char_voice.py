"""dabai 实验书架写章 —— 本章出场人物「声音档案」注入块。

从 ``lab_draft_context`` 拆出（600 行硬上限治理）。职责单一：把本章出场人物的
性格 / 说话风格 / 功能 / 欲望 / 憋屈来源整理成注入块，让每个人物按自己的腔调
发声，消除对话千人一面。台账（资产 / 与主角态度）另由 ``ledger_block`` 注入，
此处不重复。

无外部依赖（不反向 import lab_draft_context，避免循环）：出场人名由调用方传入。
"""
from __future__ import annotations

from app.models.dabai import DabaiProject


def _protagonist_char(project: DabaiProject):
    """主角 DabaiCharacter：role 含『主角』/protagonist 优先，否则第一个核心。"""
    chars = list(project.characters or [])
    for c in chars:
        role = str(c.role or "")
        if "主角" in role or role.lower() == "protagonist":
            return c
    for c in chars:
        if str(c.tier or "") == "核心":
            return c
    return chars[0] if chars else None


def _format_char_voice(c, *, is_protagonist: bool) -> str:
    """单个人物声音档案行：性格 + 说话风格 + 功能 + 欲望/憋屈。"""
    extra = c.extra if isinstance(c.extra, dict) else {}
    head = f"{c.name}（{c.role or '配角'}"
    if c.tier:
        head += f"/{c.tier}"
    if c.start_realm:
        head += f"，{c.start_realm}"
    head += "）"
    bits: list[str] = []
    if c.persona:
        bits.append(f"性格:{str(c.persona)[:60]}")
    speech = extra.get("speech_kit") or extra.get("speech_style")
    if speech:
        bits.append(f"说话风格:{str(speech)[:60]}")
    if c.function:
        bits.append(f"功能:{str(c.function)[:50]}")
    if extra.get("desire"):
        bits.append(f"欲望:{str(extra['desire'])[:40]}")
    if extra.get("wound"):
        bits.append(f"憋屈来源:{str(extra['wound'])[:40]}")
    tail = "；".join(bits) if bits else (
        "按主角一贯口吻发声" if is_protagonist else "按其身份口吻发声"
    )
    return f"  - {head}：{tail}"


def build_char_voice_block(project: DabaiProject, stage_names: list[str]) -> str:
    """本章出场人物声音档案：让每个人按自己的性格/说话风格发声，对话有区分度。

    Args:
        stage_names: 本章出场人名（involved_characters + witnesses，已去重）；
            主角恒列首位，其余按出场顺序、最多 8 人，仅纳入人物表能匹配到档案者。
    """
    by_name = {str(c.name).strip(): c for c in (project.characters or []) if c.name}
    if not by_name:
        return ""
    protag = _protagonist_char(project)
    ordered: list[tuple] = []
    seen: set[str] = set()
    if protag and protag.name:
        ordered.append((protag, True))
        seen.add(str(protag.name).strip())
    for name in stage_names:
        c = by_name.get(name)
        if c and name not in seen:
            ordered.append((c, False))
            seen.add(name)
        if len(ordered) >= 8:
            break
    if not ordered:
        return ""
    lines = [_format_char_voice(c, is_protagonist=p) for c, p in ordered]
    return (
        "【本章出场人物声音档案（每人按其性格与说话风格发声，"
        "对话须有区分度，禁止所有人一个腔调）】\n" + "\n".join(lines)
    )
