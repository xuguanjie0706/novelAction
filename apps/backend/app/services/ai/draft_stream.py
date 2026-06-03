"""AUTO-GENERATED mixin chunk from legacy ai_service — see package docstring."""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import List, AsyncGenerator, Optional
from uuid import UUID

logger = logging.getLogger(__name__)

from sqlalchemy.orm import Session

from app.config import settings
from app.services.llm_config import normalize_openai_base_url, resolve_gemini_connection
from app.services.llm_task_profiles import resolve_task_profile
from app.services.llm_token_budgets import (
    max_tokens_auto_debrief,
    max_tokens_chapter_quality_check,
    max_tokens_coherence_apply,
    max_tokens_coherence_check,
    max_tokens_draft_stream,
    max_tokens_expand_outline,
    max_tokens_extract_memory,
    max_tokens_outline_quality_check,
    max_tokens_plan_full_structure,
    max_tokens_quality_micro_patch,
    max_tokens_suggest_stream,
)
from app.services.llm_call_log import log_llm_call
from app.services.genre_kit import get_genre_guardrail, normalize_genre
from app.services.xuanhuan_lexicon import (
    format_modern_blacklist_for_prompt,
    is_xuanhuan_like_genre,
)
from app.utils.chapter_manuscript import split_plain_manuscript_and_index_block

from app.services.ai.guardrails import genre_guardrail_text


class DraftStreamMixin:
    async def draft_assist_stream(
        self,
        chapter_title: str,
        outline_hook: str,
        outline_summary: str,
        outline_conflict: str,
        outline_highlight: str,
        outline_foreshadow: str,
        prev_chapter_tail: str,
        world_summary: str,
        character_summary: str,
        memory_summary: str,
        existing_content: str,
        premise: str = "",
        user_prompt: str = "",
        replace_existing: bool = False,
        # 故事线、实力里程碑、情感基调
        storyline_summary: str = "",
        outline_power_milestone: str = "",
        outline_emotional_tone: str = "",
        # 第二道锁：本章故事日 + 人物清单约束
        story_day: str = "",
        chapter_manifest: list = None,
        # 生成前从数据库整理出的事实账本，约束跨章连续性
        continuity_context: str = "",
        chapter_index_context: str = "",
        quality_debt_context: str = "",
        writing_brief_context: str = "",
        # 线索页「伏笔管理」+ 章节索引情节档案（与质检同源），独立预算避免被连续性账本截断
        plot_dossier_context: str = "",
        # 本章字数目标（来自 OutlineNode.expected_words）
        word_target: int = 2300,
        # 卷阶段（OutlineNode.phase / volume.extra.phase），用于切 prompt 模板与采样档位
        phase: Optional[str] = None,
        # 立项定位（Project.extra.positioning），用于把读者画像 / 爽点节奏注入 prompt
        positioning: Optional[dict] = None,
        # 写入 llm_call_logs.context，便于对账（含模型完整原文 output_payload.text）
        stream_log_context: dict | None = None,
        # 作品类型（如 Project.genre）；玄幻/仙侠等会注入「禁现代科幻词」正文护栏
        genre: str = "",
        # 复盘闭环：来自上一章复盘的 next_chapter_directives，高优先级注入
        prev_directives: str = "",
        # P2-W5-2 戏份预算 + 强制 POV
        pov_character_name: str = "",
        character_screen_time: Optional[dict] = None,
        # 三层调度：章纲 → 分场蓝图（Scene records 格式化后注入，无数据时为空字符串）
        scene_blueprint: str = "",
        # 读者承诺台账：当前章节窗口内的 open ReaderPromise，分必须/可以兑现两级
        reader_promise_context: str = "",
        # 写前简报（由 pre_write_warning 生成）：主角状态锁定 + 本章写法指导 + 必发事件 + 幻觉预防。
        # 独立于 user_prompt（800字上限），享有 2500 字专属预算，位置优先于"作者补充要求"。
        # 仅在门控写作且 pre_write_warning_enabled=True 时由 gated_draft_routes 填入；
        # 普通 draft-assist/stream 调用传空字符串即可（默认值）。
        pre_write_brief: str = "",
        # 空间连续性约束（由 gated_draft_routes._build_location_context 生成）：
        # 列出各主角当前位置 + Location.sensory_signature，注入为硬约束，防感官/位置跨章漂移。
        # 有内容时插入 prompt 中【本章大纲计划】之前，无内容时跳过（不产生空白行）。
        location_context: str = "",
        # 境界快照：{人物名: 当前境界} 字典，由路由层从 Character 表取最新值注入。
        # 独立于 character_summary，作为写章硬约束注入 final_reminder，防境界倒退。
        realm_snapshot: Optional[dict] = None,
        # 多轴力量体系块（primary/path/artifact/sect + 道心/天地法则），由 _build_draft_context 注入。
        power_systems_context: str = "",
        # 跨章桥接：上章锁定节拍 / hook 冲突预警 / 认知边界 / 语风锚点 / 反 AI 腔 + 情绪预算
        # （见 draft_continuity_bridge.py，已聚合 draft_style_guard 风格守门块）
        draft_bridge_context: str = "",
    ) -> AsyncGenerator[str, None]:
        """
        根据大纲计划 + 完整故事上下文，流式生成本章起笔或续写建议。
        像一位有30年经验的作家，把世界观、人物弧、伏笔、故事线进展自然织入文字。

        Args:
            phase: 卷阶段，决定模板分支与采样档位。
                可选：``opening`` / ``rising`` / ``turning`` / ``dark_hour`` / ``climax`` / ``ending``。
                未提供时按"中段章节"模板写。
            scene_blueprint: 由 _build_scene_blueprint 生成的分场蓝图文本；
                有内容时注入【本章大纲计划】区域，替代平铺式单字段描述，
                提供逐场 POV/冲突/转折/钩子/字数预算等精确指导。
            positioning: ``Project.extra.positioning`` JSON——读者画像 / 爽点类型 / 打脸频率 / 情感线占比 /
                节奏类型。用于把作品基本面注入正文 prompt，避免每章独立漂移。
        """
        from app.services.llm_task_profiles import phase_to_draft_task

        # P2.5: 每次起笔开始前清空截断警告，供调用方在流结束后通过 svc._truncation_warnings 读取本次结果
        self._truncation_warnings = []

        has_content = bool(
            not replace_existing and existing_content and len(existing_content.strip()) > 50
        )
        large_context = self._large_context_enabled()

        # ── 阶段化 system prompt：开篇/起飞/转折/至暗/高潮/收束 各有侧重 ────────────
        phase_norm = (phase or "").strip().lower()
        phase_brief_map = {
            "opening": (
                "【当前卷阶段：开局期 / 新手村】\n"
                "- 钩子密度高：每 800-1000 字至少一个张力点（疑问、压迫、伏笔、冲突）\n"
                "- 信息密度高：开篇 200 字内必须落地世界、主角状态、核心痛点\n"
                "- 爽点节奏：3 章一小爽，禁止纯铺垫章；当章必须有可被读者复述的「高光瞬间」\n"
                "- 字数偏短（建议 ±200 字内贴近 2200 字），节奏要紧；忌用大段心理流水账\n"
                "- 文本比例参考：对话 40% / 行动场景 40% / 心理独白 20%（对话段视觉上更轻，利于追读）"
            ),
            "rising": (
                "【当前卷阶段：起飞期 / 扩张期】\n"
                "- 势力面扩展、感情线接入；每章保留至少一条 hook\n"
                "- 允许中等节奏的铺垫，但必须有「小爽收束」或反转预告\n"
                "- 控制信息量，避免一章塞太多新设定\n"
                "- 文本比例参考：对话 35% / 行动场景 40% / 心理独白 25%"
            ),
            "turning": (
                "【当前卷阶段：转折期】\n"
                "- 推进核心矛盾升级；老角色态度转变；至少一处反转或代价兑现\n"
                "- 节奏中速，对话比心理多；不要回避负面情绪\n"
                "- 文本比例参考：对话 35% / 行动场景 35% / 心理独白 30%"
            ),
            "dark_hour": (
                "【当前卷阶段：至暗期】\n"
                "- 允许「虐」，节奏放缓，让代价具象、让选择艰难\n"
                "- 主角处境恶化，不要急于反弹；情绪基调克制不浮夸\n"
                "- 字数可适度拉长（接近 2800 字），多用具体场景渲染压力\n"
                "- 文本比例参考：心理独白 40% / 行动场景 35% / 对话 25%（心理戏为主，但独白单段不超200字）"
            ),
            "climax": (
                "【当前卷阶段：高潮期】\n"
                "- 所有伏笔在本卷内必须给读者明确反馈（回收 / 提级 / 公开）\n"
                "- 爆点拉满：动作 / 情绪 / 信息揭示三选二；字数允许 3000-3300 字\n"
                "- 章末必须留下卷尾级钩子（更大反派 / 新地图 / 关键人物动向）\n"
                "- 文本比例参考：行动场景 55% / 对话 30% / 心理独白 15%（此阶段减少独白，让动作说话）"
            ),
            "ending": (
                "【当前卷阶段：收束期】\n"
                "- 给读者交代感，但保留下一卷悬念种子\n"
                "- 不要总结性独白；用一个画面或对话句结束本章\n"
                "- 文本比例参考：行动场景 40% / 对话 35% / 心理独白 25%"
            ),
        }
        phase_brief = phase_brief_map.get(phase_norm, "")

        # ── 立项定位：读者画像 / 爽点类型 / 节奏（每章都要看见，不再让 AI 临场猜）────────
        positioning_brief = ""
        if positioning and isinstance(positioning, dict):
            parts = []
            if positioning.get("target_audience"):
                parts.append(f"目标读者：{positioning['target_audience']}")
            if positioning.get("tropes"):
                tropes = positioning["tropes"]
                if isinstance(tropes, list):
                    tropes = "、".join(str(t) for t in tropes if t)
                parts.append(f"核心爽点类型：{tropes}")
            if positioning.get("face_slap_pattern"):
                parts.append(f"打脸频率：{positioning['face_slap_pattern']}")
            if positioning.get("emotional_arc"):
                parts.append(f"情感线占比：{positioning['emotional_arc']}")
            if positioning.get("pace_type"):
                parts.append(f"节奏类型：{positioning['pace_type']}")
            if positioning.get("selling_point"):
                parts.append(f"卖点钩子：{positioning['selling_point']}")
            if parts:
                positioning_brief = "【作品基本面（必须每章贯彻）】\n" + "\n".join(parts)

        # ── 写作风格档位（作者建书时选定，全书贯彻；存于 Project.extra.positioning.writing_style）──
        # plain=白话直白（降低阅读门槛，小白友好）/ standard=默认 / dense=老白文。
        writing_style = "standard"
        if positioning and isinstance(positioning, dict):
            _ws = str(positioning.get("writing_style") or "").strip().lower()
            if _ws in ("plain", "standard", "dense"):
                writing_style = _ws

        # ── system 瘦身：只保留身份 + 核心原则；硬约束（钩子/严禁/截图/POV/quota）下沉到 ──
        # ── user prompt 末尾的「写作前最后重读」块，紧贴生成指令，遵从率显著高于堆在 system 顶部 ──
        # 身份句随风格档位切换：plain 强调"一看就懂"，dense 保持"文笔老练"。
        if writing_style == "plain":
            _identity = (
                "你是擅长写「节奏明快、一看就懂」爽文的网络小说作家，深谙追读节奏。"
                "你的读者多为只在手机上快速浏览的小白读者，最讨厌看不懂、要回翻。"
            )
        else:
            _identity = "你是拥有30年经验的网络小说作家，文笔老练，深谙追读节奏。"
        # 核心原则第 5 条按风格分叉：standard/dense 走老白文"让事件自己说话、不要
        # 解释旁白"；plain（番茄纯爽文）相反——把事情讲明白是第一要务，故只保留
        # "不要废话/元信息/AI 自指"这一层，移除"不要解释旁白"。
        # 这样从源头消除"前面禁止解释、后面又松绑解释"的 prompt 内部矛盾。
        if writing_style == "plain":
            _principle_5 = (
                "5. 直接给出正文，但要把事情讲明白：用大白话交代清楚发生了什么、"
                "为什么、谁更强；不要追加任何索引/总结/元信息块；不要 AI 自指词、"
                "不要\"好的\"之类的废话"
            )
        else:
            _principle_5 = (
                "5. 直接给出正文：不要解释、不要旁白、不要\"好的\"之类的废话；"
                "不要追加任何索引/总结/元信息块；不要 AI 自指词"
            )
        system = _identity + """
你的任务是根据章节计划与故事背景，输出一段高质量的本章正文。

【核心写作原则】
1. 严格落实「开篇钩子」意图，第一句话就要抓人
2. 世界观与人物当前境界、状态、技能须与既有设定吻合，不得矛盾
3. 人物的行动、心理须符合其弧线、动机、价值观；既有故事线必须顺势推进
4. 上一章结尾、本章实力里程碑、情感基调要有分量地接续
""" + _principle_5

        # ── 风格档位简报：plain 注入助读约束，dense 强化密度，standard 不注入（行为不变）──
        readability_brief = ""
        if writing_style == "plain":
            readability_brief = (
                "【白话直白模式（必须每章贯彻，优先级高于文采追求）】\n"
                "- 句子短：尽量一句一个意思，单句一般不超过 40 字；少用层层嵌套的长定语。\n"
                "- 新名词随手解释：境界、功法、势力、专有名词首次出现时，就近用一句大白话点明它是什么、有多强。\n"
                "- 因果讲清楚：关键转折给读者一句「为什么会这样」的交代，不要靠读者自己脑补。\n"
                "- 允许适度复述：可以用一两句简短回顾前情，帮读者跟上，不必怕重复。\n"
                "- 一次只抛一个新设定：同一段里不要同时塞多个新概念、新人物、新地名。\n"
                "- 用词口语化：少用生僻字和古奥词藻，优先选读者一眼认得的常用词。"
            )
        elif writing_style == "dense":
            readability_brief = (
                "【老白文模式】\n"
                "- 保持较高的信息密度与文采，允许凝练老练的句式与较强的留白。"
            )

        genre_gr = genre_guardrail_text(genre)
        if genre_gr.strip():
            system = system + "\n\n" + genre_gr

        if positioning_brief:
            system = system + "\n\n" + positioning_brief
        if readability_brief:
            system = system + "\n\n" + readability_brief
        if phase_brief:
            system = system + "\n\n" + phase_brief
        if prev_directives.strip():
            system = system + "\n\n【上一章复盘闭环指令（最高优先级，必须先满足再写正文）】\n" + prev_directives.strip()

        # ── 写作硬约束：拼成 final_reminder 块，放在 user prompt 末尾紧贴生成指令 ──
        # 这些是「高频违反 / 必须看见」的规则，放 system 容易被中段稀释；移到末尾后召回率更高。
        # ── 境界锁定块：从 realm_snapshot 生成硬约束，防倒退 ──────────────────────────
        realm_lock_block = ""
        if realm_snapshot and isinstance(realm_snapshot, dict):
            _realm_lines = [
                f"  {name}：当前境界={realm}（本章及后续章节不得出现任何低于此境界的描写或突破至此境界以下的情节）"
                for name, realm in realm_snapshot.items()
                if name and realm
            ]
            if _realm_lines:
                realm_lock_block = (
                    "\n\n▍境界状态锁定（⚠️ 最高级别约束，违反即视为严重连续性错误）\n"
                    "以下为各关键人物截至本章的最新境界，写作中绝对禁止降级或写出低于此水准的技法：\n"
                    + "\n".join(_realm_lines)
                    + "\n  若本章大纲明确写有境界突破情节，突破后的境界须高于上方记录，不得逆转。"
                )

        # 严禁清单按风格分叉（而非"先禁后松绑"）：standard/dense 用为老白文密度
        # 服务的全量清单；plain（番茄纯爽文）整段替换为直白版——移除"流水账连接词"
        # "解释性旁白连续3句"这两条会误伤可读性的规则，并正向追加番茄爽文要素。
        if writing_style == "plain":
            _forbid_block = """▍严禁清单（白话直白版）
- 排比式抒情开篇：「少年抬头望向天空」「天地间一片寂静」「时间仿佛静止」
- 单段心理独白超过 200 字（情绪要直给，但不要长篇内心戏）
- 滥用「突然」作为段落起点
- 生僻字、古奥词藻、需要读者回翻才懂的绕句
- AI 自指词（「作为一个 AI」「根据您的要求」「我来为您」）

▍白话直白硬要求（番茄纯爽文，优先级最高）
- 把事情讲明白：关键转折给读者一句「为什么会这样」，允许连续多句解释性叙述。
- 多对话、少叙述：靠人物对话推进剧情，压缩大段景物与环境铺陈。
- 段落短：每段 2～3 句即换行，适配手机阅读。
- 爽点前置：开头 200 字内就要出现冲突或钩子，不铺垫。
- 金手指/实力数值化：升级、打脸、获得，用读者一眼能感知的强弱对比表达；未进入【认知边界】已公开名单的设定全名，旁白禁止直呼（用黑火/异火/经脉异变等），主角内心也避免科普式点名。
- 情绪直给：主角爽了就明写爽、憋屈就明写憋屈，不含蓄留白。
- 打脸/反转落到具体：必写被打脸者的脸色/动作/原话，且至少一句围观者反应（惊呼、议论、前后态度对比），禁止用「场面一时哗然」「众人震惊」「气氛凝重」一笔带过。
- 关键场面给镜头：用具体动作、对话、感官细节呈现冲突，杜绝「气氛很紧张」「场面很激烈」「实力差距巨大」这类抽象总结代替画面。
- 允许承接连接词（于是/然后/接着）理清因果与时间顺序，只是不要通篇流水账。"""
        else:
            _forbid_block = """▍严禁清单
- 流水账连接词：「然后…接着…于是…此时…」
- 排比式抒情开篇：「少年抬头望向天空」「天地间一片寂静」「时间仿佛静止」
- 单段心理独白超过 200 字
- 解释性旁白连续 3 句以上（让事件本身说话）
- 滥用「突然」作为段落起点
- AI 自指词（「作为一个 AI」「根据您的要求」「我来为您」）"""

        final_reminder = """【⚠️ 写作前最后重读（违反任意一条视为本章不合格）】

▍章末钩子（最后一段 ≤80 字，必须满足以下之一）
A) 出现新的未解之谜或揭示
B) 强敌 / 关键 NPC 登场但未交手
C) 关键人物开口未说完，话被掐断
D) 主角被推到决策悬崖
严禁章末用总结句、抒情句、陈述性收束（如「夜更深了」「一切归于平静」）；钩子必须紧贴正文事件，不允许另起一段意义不明的「画外音」。

""" + _forbid_block + """

▍反「AI 味」三连硬约束（每章必须遵守，违反任意一条视为本章不合格）
1. 反转必有铺垫：任何转折 / 反转 / 危机解除，其因由（伏笔、前文信息、人物已知动机、已登记设定）必须在本章前文或既有上下文中可追溯。严禁天降转折、巧合救场、反派突然降智、主角临场顿悟却无来由。读者读到时应能回看到「原来如此」，而非「凭什么」。
2. 单一有限视角：全程用单一角色的有限视角叙事（大纲未指定 POV 时默认主角视角）。严禁全知 / 上帝视角；不得叙述当前视角人物不可能知道的信息或直接写他人内心活动；确需切换视角必须另起一场并分段交代，禁止段内频繁跳视角。
3. 设定不得凭空新增：只能使用上文已登记的世界观 / 势力 / 功法 / 道具 / 境界设定。确需引入新元素时，必须在其发挥作用「之前」先用至少一处具体铺垫交代来由，严禁「其实早有准备」「碰巧随身带着」「原来一直都会」式即用即造。金手指的能力范围与代价以既有设定为准，不得为了让主角脱困而临时扩张金手指（除非大纲给出有铺垫的升级节点）。

▍截图时刻（每章至少 1 处，自然融入正文，不需要另起段落标注）
A) 狠话档：主角或反派一句话让读者觉得「太绝了」（要有力度，不要矫情）
B) 细节档：让人背脊发凉或忍俊不禁的五感具象细节
C) 反转档：前文铺垫，章末或中段一句颠覆读者判断的话

▍每一场戏都必须服务作品基本面：读者定位、核心命题、爽点承诺、禁忌边界。"""

        # P2-W5-2 三层调度硬约束按需追加
        if pov_character_name:
            final_reminder += (
                f"\n\n▍强制 POV：{pov_character_name}\n"
                "必须使用该角色的第一人称或第三人称有限视点，严禁全知视角或中途切换 POV。"
            )
        if character_screen_time:
            st = "、".join(f"{k} {v}%" for k, v in character_screen_time.items())
            final_reminder += f"\n\n▍戏份预算（建议在 ±5% 内）：{st}"
        final_reminder += (
            "\n\n▍配角配额：本章在场命名角色 ≤ 主1 + 核心配角3 + 反派2 + 师长2；"
            "多余角色合并或用无名路人（如「一名弟子」「路人」）处理。"
        )
        # （白话直白模式的松绑已在上方「严禁清单」分叉时整段替换，无需再追加补充块）
        # 境界锁定块追加到最后（紧贴生成指令，召回率最高）
        if realm_lock_block:
            final_reminder += realm_lock_block

        # 根据大纲 word_target 动态计算续写字数
        # 下限 1900：存量章纲的 expected_words 仍是旧低预算（番茄 ~1500），靠这里抬升，
        # 使「整体加长」对已展开章节在写正文时也生效，而非只对未来章纲。
        full_target = max(1900, int(word_target or 2300))
        cont_target_lo = max(1000, round(full_target * 0.5))
        cont_target_hi = max(1400, round(full_target * 0.7))

        if replace_existing:
            task_line = (
                f"【整章重写】请根据本章大纲与故事背景，写出全新正文约{full_target}字（±200字），"
                "不要复述或抄袭旧稿套话；若旧稿与大纲冲突，以大纲为准。"
                "正文不要包含章节标题行，直接从故事第一句话开始叙事。"
            )
        elif has_content:
            existing_tail_limit = 4000
            task_line = (
                f"当前已写内容（最后{existing_tail_limit}字供衔接参考）：\n"
                f"{self._clip_context(existing_content, 500, 4000, from_end=True)}\n\n"
                f"请根据章节计划，续写接下来约{cont_target_lo}-{cont_target_hi}字的正文，保持章节爽点与情绪推进："
                "正文不要包含章节标题行，直接从故事第一句话开始叙事。"
            )
        else:
            task_line = f"请根据章节计划，写出本章完整初稿约{full_target}字（±200字），第一句话必须立刻抓住读者，并在章末留下追读钩子：正文不要包含章节标题行，直接从故事第一句话开始叙事。"

        # 长上下文：优先保证故事连续性，尽量注入完整设定与记忆。
        premise_part = (
            self._clip_context(premise, 1200, 12000)
            if premise
            else "（未填写；请从创意、人物和大纲中提炼作品基本面，但不得违背既有设定）"
        )
        world_part = self._clip_context(world_summary, 200, 12000) if world_summary else "（未设定）"
        power_part = ""
        if power_systems_context and power_systems_context.strip():
            power_part = (
                f"\n力量体系（多轴，写作须严格对齐，禁止自创未登记境界/道途/法宝阶）：\n"
                f"{self._clip_context(power_systems_context.strip(), 400, 2400, field_name='power_systems')}\n"
            )
        char_part = self._clip_context(character_summary, 300, 12000) if character_summary else "（未设定）"
        mem_part = (
            f"\n近期关键事件：{self._clip_context(memory_summary, 150, 12000)}"
            if memory_summary else ""
        )
        prev_part = (
            self._clip_context(prev_chapter_tail, 300, 4000, from_end=True)
            if prev_chapter_tail else "（这是第一章，无前情）"
        )
        prev_continuity_hard = ""
        if (prev_chapter_tail or "").strip():
            tail200 = self._clip_context(
                prev_chapter_tail.strip(), 200, 4000, from_end=True
            )
            prev_continuity_hard = (
                "\n\n▍【上文衔接·硬约束】\n"
                f"以下为上章正文末尾（最多 200 字，权威续接锚点）：\n「{tail200}」\n\n"
                "硬规则：本章正文开头约 200 字必须直接承接上述末尾的**下一瞬间**（情境、视点、悬念、语势），"
                "禁止把时间倒回上章已写完的节拍（觉醒/重组/口头休妻/黑火初涌等不得再演一遍），"
                "禁止无交代的时间或空间跳切、禁止另起炉灶改换场次。"
            )
        bridge_part = ""
        if (draft_bridge_context or "").strip():
            bridge_part = (
                "\n\n"
                + self._clip_context(
                    draft_bridge_context.strip(), 3000, 9000, field_name="draft_bridge"
                )
            )
        continuity_part = (
            f"\n【连续性账本 / 不得违背】\n{self._clip_context(continuity_context, 2000, 24000)}\n"
            if continuity_context
            else ""
        )
        chapter_index_part = (
            f"\n【章节速查索引】\n{self._clip_context(chapter_index_context, 1600, 20000)}\n"
            if chapter_index_context
            else ""
        )
        plot_dossier_part = (
            f"\n【情节档案 / 伏笔管理表与故事线】\n"
            f"{self._clip_context(plot_dossier_context, 2200, 30000)}\n"
            if plot_dossier_context
            else ""
        )
        quality_debt_part = (
            f"\n{self._clip_context(quality_debt_context, 1200, 12000)}\n"
            if quality_debt_context
            else ""
        )
        writing_brief_part = (
            f"\n{self._clip_context(writing_brief_context, 1200, 20000)}\n"
            if writing_brief_context
            else ""
        )
        # 读者承诺：必须/可以兑现两级；放在质检债务之后，正文生成指令之前
        reader_promise_part = (
            f"\n{self._clip_context(reader_promise_context, 800, 6000)}\n"
            if reader_promise_context and reader_promise_context.strip()
            else ""
        )

        # 故事线与本章特殊目标
        storyline_part = (
            f"\n当前活跃故事线：{self._clip_context(storyline_summary, 200, 8000)}"
            if storyline_summary else ""
        )
        milestone_part = f"\n本章实力里程碑：{outline_power_milestone}" if outline_power_milestone else ""
        tone_part = f"\n情感基调：{outline_emotional_tone}" if outline_emotional_tone else ""
        day_part = f"\n故事日：{story_day}" if story_day else ""

        # 第二道锁：人物清单硬约束
        # chapter_manifest 有值 = 新大纲数据，启用严格模式
        # 为空 = 旧大纲/无清单，退回兼容模式（不加约束）
        manifest_constraint = ""
        if chapter_manifest:
            manifest_str = "、".join(chapter_manifest)
            manifest_constraint = (
                f"\n\n⚠️【本章人物清单（严格限定）】\n"
                f"本章允许出场的命名角色：{manifest_str}\n"
                f"不得引入清单之外的任何命名角色。"
                f"若剧情需要路人/次要角色，用「一名弟子」「路人」等无名方式处理。"
            )

        extra = ""
        if user_prompt and user_prompt.strip():
            extra = f"\n\n【作者补充要求】\n{self._clip_context(user_prompt, 800, 4000)}"

        # 写前简报：独立 2500 字预算，优先级高于"作者补充要求"。
        # 由门控写作路径在 pre_write_warning_enabled=True 时注入；普通续写为空。
        pre_write_brief_part = ""
        if pre_write_brief and pre_write_brief.strip():
            pre_write_brief_part = (
                "\n\n===【写前简报·主编锁定（最高优先级，写正文前必须逐条对照）】===\n"
                + self._clip_context(pre_write_brief.strip(), 2500, None, field_name="pre_write_brief")
                + "\n==="
            )

        # 空间连续性约束：由 gated_draft_routes._build_location_context 生成。
        # 有内容时注入【本章大纲计划】之前，作为感官/位置漂移防护硬墙；无数据时跳过。
        location_context_part = ""
        if location_context and location_context.strip():
            location_context_part = "\n" + location_context.strip() + "\n"

        # ── 分场蓝图：有数据时以「权威结构」标签注入，并提示下方 outline 平铺字段降级为风格参考 ──
        # 当前 Bootstrap 仅为第 1 章生成 Scene 记录；其余章节 blueprint 为空，回退到 outline 平铺。
        # 通过显式 authority 声明，避免 AI 在两套结构间漂移。
        has_blueprint = bool(scene_blueprint and scene_blueprint.strip())
        if has_blueprint:
            scene_blueprint_part = (
                "\n【⚡ 本章权威结构 · 分场计划（必须按场号顺序逐场推进，每场字数预算 ±15% 内）】\n"
                f"{self._clip_context(scene_blueprint, 800, 6000)}"
            )
            outline_authority_note = "  （已提供分场计划，下列字段仅供风格/方向参考，结构请以分场计划为准）"
        else:
            scene_blueprint_part = ""
            outline_authority_note = ""

        # ── outline 四字段全空兜底：避免 AI 在「全是（未填写）」的情况下凭空发挥引入新主线 ──
        # 触发条件：hook / summary / conflict / highlight 四字段均为空串或仅空白。
        all_outline_empty = not any(
            (s or "").strip()
            for s in (outline_hook, outline_summary, outline_conflict, outline_highlight)
        )
        if all_outline_empty and not has_blueprint:
            outline_empty_fallback = (
                "\n⚠️ 本章大纲未规划：请严格基于【上章结尾】与【情节档案】自然推进，"
                "不得引入新主线冲突或新主要角色；聚焦已在场人物的状态变化与现有矛盾的延续，"
                "章末留一个与当前线索直接相关的小钩子。"
            )
        else:
            outline_empty_fallback = ""

        # 注：章节速查索引区块由复盘环节（auto_extract_debrief）统一产出，写正文阶段不再追加模板，
        # 把 token 预算和模型注意力全部留给正文质量。

        prompt = f"""【立意与类型 / PREMISE】
{premise_part}

【故事背景】
世界观：{world_part}{power_part}
本章出场人物（含境界/位置/技能）：{char_part}{mem_part}{storyline_part}
{writing_brief_part}

【上章结尾】
{prev_part}{prev_continuity_hard}{bridge_part}
{continuity_part}
{chapter_index_part}
{plot_dossier_part}
{quality_debt_part}
{reader_promise_part}
{location_context_part}【本章大纲计划】{outline_authority_note}
标题：{chapter_title}{day_part}
开篇钩子：{outline_hook or "（未填写）"}
核心事件：{outline_summary or "（未填写）"}
人物变化：{outline_conflict or "（未填写）"}
章末方向：{outline_highlight or "（未填写）"}{milestone_part}{tone_part}
{f"伏笔管理：{outline_foreshadow}" if outline_foreshadow else ""}{manifest_constraint}{outline_empty_fallback}
{scene_blueprint_part}{pre_write_brief_part}
{task_line}{extra}

{final_reminder}"""

        max_tok = max_tokens_draft_stream()
        stream_ctx: dict = {
            "operation": "draft_assist_stream",
            "chapter_title": chapter_title,
            "phase": phase_norm or None,
        }
        if stream_log_context:
            stream_ctx.update(stream_log_context)
        # 阶段→任务名映射：开局期/高潮期/至暗期分别走更激进或更克制的采样档位。
        # plain（白话直白/番茄纯爽文）优先级高于 phase：统一走低温 draft.plain 档，
        # 避免高温高 penalty 把"直白"重新搅成"绕 + 换花样说"。
        draft_task = phase_to_draft_task(phase_norm, writing_style=writing_style)
        async for chunk in self._stream_ai(
            system,
            prompt,
            max_tokens=max_tok,
            context=stream_ctx,
            task=draft_task,
        ):
            yield chunk

