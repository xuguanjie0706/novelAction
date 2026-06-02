"""Bootstrap Step 1：项目基础信息落库。

一次 LLM 调用完成：
  - 书名海选（15~20个候选，按打分降序；首位即为正式书名）
  - 结构化 premise（10个独立字段；渲染为 markdown 存 Project.premise，向后兼容）
  - 结构化 world_overview（6块独立；渲染为纯文本存 Project.world_overview，向后兼容）
  - 结构化数据同时写入 Project.extra['premise_struct'] / ['world_overview_struct'] / ['title_candidates']

下游兼容：
  ctx['premise']           — 渲染后 markdown（旧路径 [:N] 截取仍有效）
  ctx['world_overview']    — 渲染后纯文本（旧路径 [:300] 截取 summary 块）
  ctx['premise_struct']    — 结构化 dict（新路径，精确取 .core_conflict 等字段）
  ctx['world_overview_struct'] — 结构化 dict（新路径，精确取 .power_system 等块）
  ctx['title_candidates']  — 候选列表（含策略/打分/理由）
"""

from __future__ import annotations

from typing import Any

from app.config import settings
from app.models import Project
from app.services.bootstrap.parse import parse_json
from app.services.bootstrap.prompts import book_length_constraints_for_prompt
from app.services.bootstrap.prompts.project import build_project_prompt
from app.services.genre_kit import get_genre_kit, render_kit_for_prompt


# ── 渲染层：结构化对象 → 兼容字符串 ──────────────────────────────────


def render_premise_md(p: dict) -> str:
    """将结构化 premise dict 渲染为 markdown 字符串，写入 Project.premise（向后兼容列）。

    下游若需精确字段，读 ctx['premise_struct'] 或 project.extra['premise_struct']。
    空字段自动跳过，避免生成大量空 heading。
    """
    if not isinstance(p, dict):
        return str(p)
    field_labels = [
        ("positioning",      "作品定位"),
        ("core_sentence",    "核心一句话"),
        ("theme",            "主题与命题"),
        ("core_conflict",    "核心矛盾"),
        ("protagonist",      "主角概况"),
        ("ending_tendency",  "结局倾向"),
        ("closure_boundary", "收束边界"),
        ("taboos",           "禁忌边界"),
        ("pov",              "叙事视角"),
        ("word_count_type",  "类型与篇幅"),
    ]
    parts = []
    for key, label in field_labels:
        val = (p.get(key) or "").strip()
        if val:
            parts.append(f"## {label}\n{val}")
    return "\n\n".join(parts)


def render_world_overview_text(w: dict) -> str:
    """将结构化 world_overview dict 渲染为纯文本，写入 Project.world_overview（向后兼容列）。

    summary 块置于最前，保证下游 [:200/300/400] 截取命中核心速览。
    下游若需特定块，读 ctx['world_overview_struct']['power_system'] 等。
    """
    if not isinstance(w, dict):
        return str(w)
    result_parts: list[str] = []
    summary = (w.get("summary") or "").strip()
    if summary:
        result_parts.append(summary)
    for key, label in (
        ("power_system", "力量体系"),
        ("factions",     "势力格局"),
        ("social_rules", "社会规则"),
        ("geography",    "地理格局"),
        ("history",      "历史背景"),
    ):
        val = (w.get(key) or "").strip()
        if val:
            result_parts.append(f"【{label}】\n{val}")
    return "\n\n".join(result_parts)


# ── 持久化层 ─────────────────────────────────────────────────────────


def _persist_project(svc: Any, data: dict, ctx: dict) -> Project:
    """从 LLM 输出 data 和 ctx 构造并写入 Project 行。

    副作用：commit + refresh db session。

    选名逻辑：title_candidates 已由 LLM 按 total_score 降序排列，直接取首位。
    结构化数据写入 extra，渲染后文本写入模型列（向后兼容）。
    """
    # 书名：取候选列表首位（LLM 已按打分降序排列）
    candidates: list[dict] = data.get("title_candidates") or []
    if candidates and isinstance(candidates[0], dict):
        title = (candidates[0].get("title") or "").strip() or ctx["logline"][:20]
    else:
        # 兼容 LLM 直接返回 title 字段（无候选列表时的降级）
        title = (data.get("title") or "").strip() or ctx["logline"][:20]

    genre = data.get("genre", "玄幻")

    # premise：结构化 → 渲染为 markdown 字符串
    premise_raw = data.get("premise") or {}
    premise_struct: dict = premise_raw if isinstance(premise_raw, dict) else {}
    premise_text = render_premise_md(premise_struct) if premise_struct else str(premise_raw)

    # world_overview：结构化 → 渲染为纯文本
    wo_raw = data.get("world_overview") or {}
    wo_struct: dict = wo_raw if isinstance(wo_raw, dict) else {}
    wo_text = render_world_overview_text(wo_struct) if wo_struct else str(wo_raw)

    # story_core：沿用旧结构，附加 positioning 引用
    story_core: dict = data.get("story_core") or {}
    positioning = ctx.get("positioning") or {}
    if isinstance(story_core, dict) and positioning:
        story_core["positioning"] = positioning

    # 写作风格档位（作者建书时选择，全书贯彻）：plain / standard / dense
    writing_style = str(ctx.get("writing_style") or "standard").strip().lower()
    if writing_style not in ("plain", "standard", "dense"):
        writing_style = "standard"

    # extra：聚合所有结构化产物
    extra: dict = {}
    # 写作风格落库：顶层 extra.writing_style（可发现），同时注入 positioning（下游 draft
    # 路径已统一传 Project.extra.positioning，无需额外 plumbing 即可在正文写作期读到）。
    extra["writing_style"] = writing_style
    if isinstance(positioning, dict) and (positioning or writing_style != "standard"):
        # positioning 即便为空，只要选了非默认风格档，也要落 extra.positioning，
        # 否则下游 draft 路径（统一读 extra.positioning）取不到 writing_style，plain 书会退回 standard 写法。
        positioning.setdefault("writing_style", writing_style)
        extra["positioning"] = positioning
    elif positioning:
        extra["positioning"] = positioning
    if candidates:
        extra["title_candidates"] = candidates
    if premise_struct:
        extra["premise_struct"] = premise_struct
    if wo_struct:
        extra["world_overview_struct"] = wo_struct

    project_kwargs: dict = dict(
        title=title,
        genre=genre,
        logline=ctx["logline"],
        premise=premise_text,
        world_overview=wo_text,
        story_core=story_core,
        target_words=int(ctx.get("target_words") or 1_200_000),
    )
    if extra:
        project_kwargs["extra"] = extra
    if svc.user_id is not None:
        project_kwargs["user_id"] = svc.user_id

    project = Project(**project_kwargs)
    svc.db.add(project)
    svc.db.commit()
    svc.db.refresh(project)
    return project


# ── 步骤入口 ─────────────────────────────────────────────────────────


async def gen_project(svc: Any, ctx: dict):
    """生成项目基础信息并创建 Project 行。

    一次 LLM 调用完成：书名海选（15~20个，按打分降序）+ 结构化 premise + 结构化 world_overview。

    向后兼容保证：
      ctx['premise'] / ctx['world_overview'] 仍为渲染后字符串，
      旧 step 的 [:N] 截取无需修改。
    新增精确访问路径：
      ctx['premise_struct']         — premise 结构化 dict
      ctx['world_overview_struct']  — world_overview 结构化 dict
      ctx['title_candidates']       — 全部候选（含策略/打分/理由）
    """
    system = "你是网络小说策划专家。根据创意生成项目基础信息，只返回JSON。"
    tw = int(ctx.get("target_words") or 1_200_000)
    length_block = book_length_constraints_for_prompt(tw)
    prompt = build_project_prompt(ctx, length_block)

    raw = await svc._call_with_retry(
        system,
        prompt,
        max_tokens=settings.GEMINI_SETTING_COMPLETION_MAX_TOKENS,
        task="bootstrap.project",
    )
    data = parse_json(raw)

    project = _persist_project(svc, data, ctx)

    extra = project.extra or {}
    ctx["project_title"]          = project.title
    ctx["genre"]                  = project.genre
    ctx["world_overview"]         = project.world_overview          # 渲染文本（兼容）
    ctx["world_overview_struct"]  = extra.get("world_overview_struct") or {}
    ctx["story_core"]             = project.story_core or {}
    ctx["premise"]                = project.premise or ctx.get("premise") or ""  # 渲染文本（兼容）
    ctx["premise_struct"]         = extra.get("premise_struct") or {}
    ctx["title_candidates"]       = extra.get("title_candidates") or []
    ctx["genre_kit"]              = get_genre_kit(project.genre)
    ctx["genre_kit_prompt"]       = render_kit_for_prompt(ctx["genre_kit"])

    return project, ctx
