"""
ChapterDraftState — LangGraph chapter_draft_graph 的全局状态定义。

约束：
  - 所有字段值必须可被 MemorySaver pickle（纯 Python 原语：str/int/bool/dict/list）。
  - DB ORM 对象禁止进入 state；load_context_node 负责将 DB 数据转为可序列化格式。
  - 追加型字段（errors）使用 Annotated[list, add] reducer，节点只需 return 新增项。
"""
from __future__ import annotations

from operator import add
from typing import Annotated, Optional
from typing_extensions import TypedDict


class ChapterDraftState(TypedDict):
    """LangGraph 全局状态。各节点返回需要更新的字段子集（partial dict）。"""

    # ── 任务标识（启动时写入，节点只读）────────────────────────────────
    job_id: str
    project_id: str
    chapter_id: str          # 要起草的章节 UUID 字符串
    outline_node_id: str     # 对应大纲节点 UUID（无则为空串）

    # ── 配置（来自 input_payload）──────────────────────────────────────
    user_directives: str     # 用户在提交时附带的自定义指令
    llm_provider_id: Optional[str]   # 前端选择的 LLM provider（None=环境变量）
    model_profile: str       # "gemini" | "local"
    quality_threshold: int   # 质检通过分数线，默认 75
    skip_blueprint_review: bool   # True=跳过场景蓝图人工审阅直接起笔
    skip_quality_review: bool     # True=质检未达标时跳过人工审阅，直接 auto_fix
    max_iterations: int      # rewrite 最大轮数，默认 3

    # ── load_context_node 产出 ──────────────────────────────────────────
    # draft_assist_stream 所需的全部上下文字符串（可序列化）
    chapter_title: str
    phase: str               # opening | rising | turning | dark_hour | climax | ending
    positioning: Optional[dict]   # Project.extra.positioning（影响 prompt 基调）
    word_target: int         # 本章目标字数
    draft_ctx: dict          # _build_draft_context 的返回值（所有 kwargs）

    # ── scene_planning_node 产出 ────────────────────────────────────────
    scene_blueprint: list[dict]    # 场景蓝图（来自 DB Scene 记录或 AI 生成）

    # ── human_review_blueprint_node 产出 ───────────────────────────────
    blueprint_decision: str       # "approve" | "rewrite" | "skip"
    blueprint_directive: str      # rewrite 时用户附带的修改指令

    # ── draft_scenes_node 产出 ─────────────────────────────────────────
    draft_content: str
    draft_word_count: int

    # ── quality_check_node 产出 ────────────────────────────────────────
    quality_report: Optional[dict]
    quality_score: int       # 0-100；-1 表示质检未运行

    # ── human_review_quality_node 产出 ─────────────────────────────────
    quality_decision: str    # "accept" | "auto_fix" | "rewrite"
    quality_directive: str   # rewrite 时用户附带的指令

    # ── 控制流 ─────────────────────────────────────────────────────────
    iteration_count: int     # rewrite 循环次数计数器

    # ── 追加型（reducer: operator.add，节点 return 新增项即可）────────
    errors: Annotated[list[dict], add]
