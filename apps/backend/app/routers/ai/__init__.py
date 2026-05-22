"""
项目 AI 相关 HTTP 路由：按领域拆分为子模块，统一挂到同一前缀 `/projects/{project_id}/ai`。

- `context`：为大模型组装的各类上下文（连续性、索引、对话等）
- `quality_debt` / `foreshadow` / `debrief_assets`：与质检、伏笔、复盘写库相关的纯逻辑
- `*_routes`：FastAPI 路由声明（薄层，编排 DB 与 AIService）
- `reader_simulation_routes`：追读模拟 / 章末钩子检测 / 故事线悬空检测

对外仍导出 `router` 供 `main.include_router` 使用；并保留若干以下划线开头的别名，供测试与内部模块兼容旧 `app.routers.ai` 导入路径。
"""
from fastapi import APIRouter

router = APIRouter(prefix="/projects/{project_id}/ai", tags=["ai"])

from app.routers.ai import (  # noqa: E402
    chat_routes,
    coherence_routes,
    debrief_routes,
    draft_routes,
    gated_draft_routes,
    memory_routes,
    quality_check_micro_fix_routes,
    quality_debt_fix_routes,
    quality_routes,
    reader_simulation_routes,
    scene_routes,
    world_settings_generate_routes,
)

router.include_router(quality_routes.router)
router.include_router(coherence_routes.router)
router.include_router(chat_routes.router)
router.include_router(memory_routes.router)
router.include_router(draft_routes.router)
router.include_router(gated_draft_routes.router)
router.include_router(debrief_routes.router)
router.include_router(quality_debt_fix_routes.router)
router.include_router(quality_check_micro_fix_routes.router)
router.include_router(reader_simulation_routes.router)
router.include_router(scene_routes.router)
router.include_router(world_settings_generate_routes.router)

# --- 兼容旧单文件 `ai.py` 的导入（测试等） ---
from app.routers.ai.context import (  # noqa: E402
    build_writing_brief_context as _build_writing_brief_context,
    format_outline_chat_context as _format_outline_chat_context,
    format_writing_chat_context as _format_writing_chat_context,
)
from app.routers.ai.debrief_assets import apply_asset_updates as _apply_asset_updates  # noqa: E402
from app.routers.ai.foreshadow import (  # noqa: E402
    foreshadow_payload_from_index_item as _foreshadow_payload_from_index_item,
    sync_chapter_index_foreshadows as _sync_chapter_index_foreshadows,
)
from app.routers.ai.quality_debt import (  # noqa: E402
    build_quality_debt_context as _build_quality_debt_context,
    extract_quality_debt_items as _extract_quality_debt_items,
)
from app.routers.ai.schemas import (  # noqa: E402
    AssetUpdates,
    ChapterDebriefRequest,
    ChapterIndexPayload,
    NewItemAsset,
)
from app.routers.ai.text_utils import chapter_debrief_content_hash as _chapter_debrief_content_hash  # noqa: E402

__all__ = [
    "router",
    "AssetUpdates",
    "ChapterDebriefRequest",
    "ChapterIndexPayload",
    "NewItemAsset",
    "_chapter_debrief_content_hash",
    "_apply_asset_updates",
    "_build_quality_debt_context",
    "_build_writing_brief_context",
    "_extract_quality_debt_items",
    "_foreshadow_payload_from_index_item",
    "_format_outline_chat_context",
    "_format_writing_chat_context",
    "_sync_chapter_index_foreshadows",
]
