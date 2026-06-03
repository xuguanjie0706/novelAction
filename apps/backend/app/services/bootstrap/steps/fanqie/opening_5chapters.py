"""【已移出 Bootstrap】开局五章工程 — 仅保留供存量数据兼容。

2026-06：番茄 Bootstrap 不再调用本步骤；第 1 章起章纲在大纲页「展开章纲」时与全书一致由 AI 生成。
若 Project.extra 仍含 opening_5chapters，expand-chapters 可物化 1–5 章（见 fanqie_volume_expand）。
"""
from __future__ import annotations

from typing import Any

from app.models import Project
from app.services.bootstrap.parse import parse_json
from app.services.llm_token_budgets import max_tokens_bootstrap_completion


async def gen_opening_5chapters(svc: Any, project: Project, ctx: dict) -> dict:
    """
    生成开局五章精确结构：每章的结构蓝图 + 钩子文案 + 完读率预估。

    同时创建对应的 OutlineNode（chapter_plan 类型）。

    @returns opening_5chapters dict
    """
    system = (
        "你是番茄小说开局优化专家，深知番茄算法以完读率衡量质量。"
        "只返回 JSON，不要解释文字。"
    )
    fanqie_pos = ctx.get("fanqie_positioning") or {}
    contrast = ctx.get("contrast_design") or {}
    gf = ctx.get("golden_finger") or {}
    fsm = ctx.get("face_slap_map") or {}
    intro_seq = (ctx.get("_intro_sequence") or
                 (project.extra or {}).get("character_intro_sequence") or [])

    first_slap_ch = fsm.get("first_slap_chapter", 3)
    chars_ch1 = [c for c in intro_seq if c.get("chapter", 99) <= 1]
    chars_ch3 = [c for c in intro_seq if c.get("chapter", 99) <= 3]

    prompt = f"""小说：《{ctx['project_title']}》
类型公式：{fanqie_pos.get('genre_archetype', '')}
核心爽感：{fanqie_pos.get('core_satisfaction', '')}
主角初始状态：{contrast.get('initial_state_headline', '')}
触发事件：{contrast.get('trigger_event', '')}（约{contrast.get('trigger_word_estimate', '800字前')}）
金手指：{gf.get('finger_name', '')}（{gf.get('visualization_style', '')}）
首次打脸：第{first_slap_ch}章，场景：{fsm.get('first_slap_preview', '')}
第1章出场角色（最多3个）：{', '.join(c.get('name','') for c in chars_ch1[:3]) or '主角+1-2人'}
前3章出场角色（最多5个）：{', '.join(c.get('name','') for c in chars_ch3[:5]) or '按需'}
算法友好钩子：{fanqie_pos.get('algo_hook', '')}
创意：{ctx['logline']}

设计开局五章精确结构（每章约1800-2200字），返回 JSON：
{{
  "chapter_1": {{
    "title": "章节标题（可选，5字内）",
    "structure": {{
      "opening_200_words": "前200字必须完成的3件事（具体到场景/信息/情绪节奏）",
      "act_1_setup": "建立场景段（0-400字）：主角处境+核心羞辱发生",
      "act_2_trigger": "触发段（400-{_trigger_word(contrast)}字）：触发事件经过",
      "act_3_finger": "金手指激活段（{_trigger_word(contrast)}-结尾）：激活过程+第一感知",
      "ending_hook": "最后50字的钩子：读者放下手机前的最后一个悬念（必须是问句形式）"
    }},
    "opening_line": "第一句话建议（必须含：主角身份+所处困境+一个具体动作，20字内）",
    "completion_rate_target": 60,
    "completion_rate_boost": "提升完读率的关键设计（一句话）"
  }},
  "chapter_2": {{
    "title": "章节标题（可选）",
    "core_event": "本章核心事件（金手指第一次发挥效果，必须产生一个可见优势）",
    "small_win": "第一次小爽点的具体画面（20字内）",
    "new_character": "本章新登场角色（如有）及登场方式",
    "ending_hook": "本章末尾钩子（必须让读者觉得'不看下章不行'）",
    "completion_rate_target": 50
  }},
  "chapter_3": {{
    "title": "章节标题（可选）",
    "core_event": "本章核心事件",
    "first_slap_scene": "首次打脸的完整画面（谁在场+主角如何碾压+对方反应，35字内）",
    "emotion_peak": "本章情绪最高点（一句话）",
    "ending_hook": "本章末尾钩子",
    "completion_rate_target": 45
  }},
  "chapter_4": {{
    "core_event": "本章核心事件（引入更大威胁/更大诱惑）",
    "escalation": "比前三章更大的冲突/期待（一句话）",
    "ending_hook": "本章末尾钩子",
    "completion_rate_target": 40
  }},
  "chapter_5": {{
    "core_event": "本章核心事件",
    "commitment_hook": "让读者产生「不追不行」感的关键设计（具体手法：强敌登场/秘密揭示/关系逆转/etc，25字内）",
    "ending_hook": "本章末尾钩子",
    "completion_rate_target": 40
  }},
  "opening_traps": ["开局必须避免的3个具体坑（针对本书类型和设定的风险，不要通用废话）"],
  "first_sentence": "全书第一句话（正式建议稿，≤25字，必须含主角身份+困境+一个具体动作）"
}}

硬约束：
1. chapter_1.opening_line 和 first_sentence 必须不同，各有侧重
2. chapter_3.first_slap_scene 必须是「动作画面」而非旁白叙述
3. 每章 ending_hook 必须是不同类型（悬念/期待/恐惧/好奇/愤怒），禁止重复同一类型
4. completion_rate_target 按指定数字填，不能改
5. 只返回 JSON"""

    last_err = ""
    for attempt in range(3):
        fix = f"\n【请修正：{last_err}】" if last_err else ""
        raw = await svc._call_with_retry(
            system, prompt + fix,
            max_tokens=max_tokens_bootstrap_completion(),
            task="bootstrap.opening_contract",
        )
        try:
            data = parse_json(raw)
        except Exception:
            last_err = "JSON 解析失败"
            continue
        if not isinstance(data, dict):
            last_err = "须为 JSON 对象"
            continue
        if not all(f"chapter_{i}" in data for i in range(1, 4)):
            last_err = "须包含 chapter_1 ~ chapter_3"
            continue

        # 持久化
        extra = dict(project.extra or {})
        extra["opening_5chapters"] = data
        project.extra = extra
        svc.db.commit()

        from app.services.bootstrap.fanqie_normalize import ensure_fanqie_opening_volume

        # 番茄契约：Bootstrap 只落卷纲 + extra.opening_5chapters；章纲在「展开章纲」时物化
        ensure_fanqie_opening_volume(svc.db, project, {**ctx, "opening_5chapters": data})

        from app.services.bootstrap.reader_promise_seed import seed_reader_promises

        fanqie_seeds: list[dict] = []
        for ch_num in range(1, 6):
            ch = data.get(f"chapter_{ch_num}") or {}
            if not isinstance(ch, dict):
                continue
            hook = (ch.get("ending_hook") or "").strip()
            if hook:
                fanqie_seeds.append({
                    "text": hook,
                    "promise_type": "chapter_ending",
                    "source_chapter_number": ch_num,
                    "expected_chapter_window": 2 if ch_num < 5 else 1,
                    "priority": 5 if ch_num >= 5 else 4,
                    "audience_aware": 4,
                    "contract_key": f"chapter_{ch_num}_ending_hook",
                })
            if ch_num == 5:
                commit = (ch.get("commitment_hook") or "").strip()
                if commit:
                    fanqie_seeds.append({
                        "text": commit,
                        "promise_type": "chapter_ending",
                        "source_chapter_number": 5,
                        "expected_chapter_window": 1,
                        "priority": 5,
                        "audience_aware": 5,
                        "contract_key": "chapter_5_commitment_hook",
                    })
        first_sentence = (data.get("first_sentence") or "").strip()
        if first_sentence:
            fanqie_seeds.append({
                "text": first_sentence,
                "promise_type": "name_implication",
                "source_chapter_number": 1,
                "expected_chapter_window": 0,
                "priority": 2,
                "audience_aware": 2,
                "contract_key": "first_sentence",
            })
        seed_reader_promises(svc, project, fanqie_seeds, origin="bootstrap_fanqie_opening_5chapters")

        ctx["opening_5chapters"] = data
        return data

    return {}


def _trigger_word(contrast: dict) -> str:
    est = contrast.get("trigger_word_estimate", "")
    import re
    m = re.search(r"\d+", est)
    return m.group() if m else "800"

