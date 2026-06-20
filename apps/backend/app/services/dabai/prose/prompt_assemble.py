"""正文 prompt 按优先级 DAG 组装。"""
from __future__ import annotations

from dabai.golden_finger_bind import (
    is_awakening_chapter,
    is_gf_evolution_chapter,
    is_reversal_chapter,
    prose_bind_instructions,
    prose_earned_reversal_instructions,
)
from dabai.non_system import prefers_non_system, prose_system_taboo_block

from app.models.dabai import DabaiChapterOutline, DabaiProject
from app.services.dabai.intensity import intensity_prose_block
from app.services.dabai.lab_char_voice import build_char_voice_block
from app.services.dabai.lab_ledger import protagonist_name
from app.services.dabai.lab_prompt_shared import POV_LIMITED_RULES, build_witness_lock_block
from app.services.dabai.lab_word_budget import (
    chapter_word_target,
    format_per_scene_budget_lines,
    resolve_prose_word_bounds,
)
from app.services.dabai.lab_prompt_shared import prewarn_cast_names
from app.services.dabai.prose.beat_contract import (
    format_execution_block,
    format_outline_constraints_block,
    format_outline_full_block,
    resolve_beats,
)
from app.services.dabai.prose.opening_policy import ch1_benchmark_block
from app.services.dabai.prose.prompt_blocks import (
    PRIORITY_RULES,
    SYSTEM_BASE,
    SYSTEM_BASE_ARTIFACT,
    build_continuity_system_rules,
)


def _volume_for_chapter(project: DabaiProject, ch: DabaiChapterOutline):
    vols = getattr(project, "volumes", None) or []
    volume_id = getattr(ch, "volume_id", None)
    if volume_id:
        for v in vols:
            if str(v.id) == str(volume_id):
                return v
    if int(ch.chapter_number or 0) == 1:
        for v in vols:
            if int(v.volume_number or 0) == 1:
                return v
    return None


def build_prose_prompt(
    project: DabaiProject,
    ch: DabaiChapterOutline,
    *,
    prev_tail: str = "",
    recent_plot_block: str = "",
    pre_warn_block: str = "",
    scene_block: str = "",
    ledger_block: str = "",
    memory_block: str = "",
    clue_block: str = "",
    panel_block: str = "",
    prev_full_block: str = "",
    prev_hook_block: str = "",
    narrative_state_block: str = "",
    char_voice_block: str = "",
    location_bridge_block: str = "",
    qc_feedback_block: str = "",
    forward_qc_block: str = "",
    chapter_boundary_block: str = "",
    realm_writing_block: str = "",
    scene_plan: dict | None = None,
    pre_warn_result: dict | None = None,
    replace_existing: bool = False,
    prior_content: str = "",
    user_instruction: str = "",
    intensity: str = "standard",
) -> tuple[str, str]:
    """构造实验书架正文写作 (system, user)。"""
    gf = project.golden_finger or {}
    artifact = prefers_non_system({
        "logline": project.logline or "",
        "positioning": project.positioning or {},
        "golden_finger": gf,
        "benchmark": project.benchmark or {},
    })
    ladder = project.power_ladder or {}
    levels = "、".join(x.get("name", "") for x in (ladder.get("levels") or [])[:7])
    chars = "、".join(c.name for c in project.characters[:8])
    protag = protagonist_name(project)

    scene_bounds = resolve_prose_word_bounds(scene_plan, ch)
    if scene_bounds:
        target, lo, hi = scene_bounds
    else:
        target = chapter_word_target(ch)
        lo = max(1600, target - 200)
        hi = target + 200
    has_scene_plan = bool(scene_block.strip() and scene_bounds)
    has_prewarn = bool(pre_warn_block.strip() and pre_warn_result)

    contract = resolve_beats(ch, pre_warn_result)
    realm_block = (realm_writing_block.strip() + "\n") if realm_writing_block.strip() else ""

    sp = (project.benchmark or {}).get("style_profile") or {}
    style_line = "｜".join(
        f"{label}:{sp[key]}" for key, label in (
            ("sentence_style", "句式"), ("pacing", "节奏"),
            ("dialogue_density", "对话密度"), ("narration_voice", "腔调"),
        ) if sp.get(key)
    )
    style_block = (
        f"\n文风对标（贴风格写，★禁止照抄对标原句★）：{style_line}\n"
        if style_line else ""
    )

    pos_top = project.positioning or {}

    def _pos_bit(label: str, key: str) -> str:
        v = pos_top.get(key)
        if isinstance(v, list):
            v = "、".join(str(x) for x in v[:4])
        v = str(v or "").strip()
        return f"{label}:{v[:60]}" if v else ""

    pos_bits = [b for b in (
        _pos_bit("目标读者", "target_audience"),
        _pos_bit("爽点模式", "face_slap_pattern"),
        _pos_bit("情感基调", "emotional_arc"),
        _pos_bit("卖点", "selling_point"),
        _pos_bit("节奏", "pace_type"),
    ) if b]
    positioning_block = (
        "\n【全书定位锚（正文须服务此读者与爽感取向，统一全书声音）】\n  "
        + "｜".join(pos_bits) + "\n"
        if pos_bits else ""
    )

    gf_name = gf.get("name", "")
    ch_dict = {
        "chapter_number": ch.chapter_number,
        "title": ch.title,
        "yinbao": ch.yinbao,
        "end_hook": ch.end_hook,
        "shuang_type": ch.shuang_type,
        "shuang_payoff": ch.shuang_payoff,
        "emotion_turn": ch.emotion_turn,
        "yaqu_setup": ch.yaqu_setup,
    }
    bind_parts: list[str] = []
    if is_awakening_chapter(ch_dict, golden_finger_name=gf_name, artifact=artifact) \
            or is_gf_evolution_chapter(ch_dict, golden_finger_name=gf_name):
        bind_parts.append(prose_bind_instructions(gf_name=gf_name, artifact=artifact))
    if is_reversal_chapter(ch_dict):
        bind_parts.append(prose_earned_reversal_instructions(artifact=artifact))
    bind_block = "".join(bind_parts)

    cast_names = prewarn_cast_names(pre_warn_result)
    if cast_names:
        rebuilt = build_char_voice_block(project, cast_names)
        if rebuilt:
            char_voice_block = rebuilt

    has_continuity = bool(
        prev_tail.strip() or recent_plot_block.strip() or prev_full_block.strip()
    )
    system = (SYSTEM_BASE_ARTIFACT if artifact else SYSTEM_BASE)
    system += PRIORITY_RULES
    system += POV_LIMITED_RULES
    system += intensity_prose_block(intensity)
    if has_continuity:
        system += build_continuity_system_rules(
            has_prewarn=has_prewarn, has_scene=has_scene_plan,
        )
    if artifact:
        system += prose_system_taboo_block()
    if char_voice_block.strip():
        system += (
            "\n★人物声音区分（硬约束）★：对话按【出场人物声音档案】各自的性格与说话风格写，"
            "不同人物的用词、句长、语气要有可分辨差异；主角保持其一贯腔调，"
            "禁止所有人一个腔调，禁止用旁白替代人物开口。"
        )

    user_parts = [
        f"《{project.title or project.logline}》第{ch.chapter_number}章",
        f"POV 主角：{protag}（全文须用此名，禁止改名或用「少年/他」代称开章）",
        f"金手指：{gf.get('name', '')}（{gf.get('core_ability', '')}）",
        f"境界阶梯：{levels}",
        f"可用人物：{chars}",
        f"{positioning_block}{style_block}{realm_block}{bind_block}".strip(),
    ]
    user_parts = [p for p in user_parts if p]

    if char_voice_block.strip():
        user_parts.append(char_voice_block.strip())
    if narrative_state_block.strip():
        user_parts.append(narrative_state_block.strip())
    if recent_plot_block.strip():
        user_parts.append(recent_plot_block.strip())
    if panel_block.strip():
        user_parts.append(panel_block.strip())
    if memory_block.strip():
        user_parts.append(memory_block.strip())
    if clue_block.strip():
        user_parts.append(clue_block.strip())
    if ledger_block.strip():
        user_parts.append(ledger_block.strip())
    if int(ch.chapter_number or 0) == 1:
        ch1_block = ch1_benchmark_block(project, _volume_for_chapter(project, ch))
        if ch1_block.strip():
            user_parts.append(ch1_block.strip())
    if prev_full_block.strip():
        user_parts.append(prev_full_block.strip())
    if prev_hook_block.strip():
        user_parts.append(prev_hook_block.strip())
    if prev_tail.strip() and not prev_full_block.strip():
        user_parts.append(f"【上章结尾（须紧接下一瞬间续写）】\n{prev_tail.strip()}")
    if location_bridge_block.strip() and not pre_warn_block.strip():
        user_parts.append(location_bridge_block.strip())
    witness_block = build_witness_lock_block(ch)
    if witness_block:
        user_parts.append(witness_block)
    if pre_warn_block.strip():
        user_parts.append(pre_warn_block.strip())
    if scene_block.strip():
        user_parts.append(scene_block.strip())
    if replace_existing and prior_content.strip():
        user_parts.append(
            "【上一版正文节选（须换写法：禁止复用相同开头句、相同段落顺序与相同对话原句）】\n"
            + prior_content.strip()[:450]
        )
    if replace_existing and qc_feedback_block.strip():
        user_parts.append(qc_feedback_block.strip())
    if forward_qc_block.strip():
        user_parts.append(forward_qc_block.strip())
    if chapter_boundary_block.strip():
        user_parts.append(chapter_boundary_block.strip())

    if contract.has_execution:
        user_parts.append(format_execution_block(contract))
        user_parts.append(format_outline_constraints_block(ch))
    else:
        user_parts.append("【本章爽点节拍（章节要素，必须逐项落实）】")
        user_parts.append(format_outline_full_block(ch))

    if scene_block.strip():
        per_scene = ""
        if scene_plan and isinstance(scene_plan.get("scenes"), list):
            per_scene = format_per_scene_budget_lines(scene_plan["scenes"])
        task = (
            f"按上面【分场调度】逐场写出第{ch.chapter_number}章正文，五拍执行是总纲、分场是施工图。"
            f"全章合计 {target} 字（允许 {lo}～{hi}），★严禁超过 {hi} 字★。"
            "每场按其 word_budget 写足但不得超标；台词弹药必须用上；"
            "★最后一镜须落本章「章末钩子」，写完钩子立刻停笔。★"
        )
        if per_scene:
            task += f"\n【逐场篇幅上限（硬约束）】\n{per_scene}"
        task += "开笔须对齐【对标改编指引】/导演单，禁止照抄章纲或对标书原句。直接开写正文。"
    else:
        task = (
            f"按上面五拍执行写出第{ch.chapter_number}章正文。"
            f"目标 {target} 字（允许 {lo}～{hi}），严禁超过 {hi} 字。"
            "推进：①憋屈→②扳机→③引爆→④爽点+见证者→⑤章末钩子。"
            "开笔对齐对标改编/导演单，禁止照抄章纲 yaqu 原句。直接开写正文。"
        )
    if replace_existing:
        task = (
            "【整章重写】" + task
            + "以导演单五拍执行为准，情节结果不变但表述须与上一版明显不同。"
        )
        if location_bridge_block.strip() or "衔接交代" in pre_warn_block:
            task += "★跨场景衔接不可省略：开篇仍须先写位移/转场。★"
    user_parts.append(task)

    tabs = (project.positioning or {}).get("taboo_lines")
    if isinstance(tabs, list) and tabs:
        user_parts.append(f"禁忌：{'；'.join(str(t) for t in tabs[:3])}")

    instr = (user_instruction or "").strip()
    if instr:
        system += (
            "\n9. 【作者写作指令】优先级高于导演单/分场表述（情节底线与禁忌仍须遵守）。"
        )
        user_parts.append(
            "【作者写作指令（★最高优先级★）】\n" + instr[:2000]
        )

    return system, "\n\n".join(user_parts)
