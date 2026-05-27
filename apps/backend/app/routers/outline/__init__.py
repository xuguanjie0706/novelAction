"""大纲路由包：聚合子路由并保持 ``router`` / ``ws_router`` 对外兼容。"""

from fastapi import APIRouter

from app.routers.outline.routes_ai_expand import router as ai_expand_routes
from app.routers.outline.routes_full_generate import router as full_generate_routes
from app.routers.outline.routes_quality import router as quality_routes
from app.routers.outline.routes_quality_checks import router as quality_checks_routes
from app.routers.outline.routes_power_timeline import router as power_timeline_routes
from app.routers.outline.routes_story_timeline import router as story_timeline_routes
from app.routers.outline.routes_tree import router as tree_routes
from app.routers.outline.routes_linter import router as linter_routes
from app.routers.outline.routes_vol_expand import router as vol_expand_routes
from app.routers.outline.routes_workflow_ws import ws_router

router = APIRouter(prefix="/projects/{project_id}/outline", tags=["outline"])
router.include_router(tree_routes)
router.include_router(story_timeline_routes)
router.include_router(power_timeline_routes)
router.include_router(ai_expand_routes)
router.include_router(vol_expand_routes)
router.include_router(linter_routes)
router.include_router(full_generate_routes)
router.include_router(quality_routes)
router.include_router(quality_checks_routes)

__all__ = ["router", "ws_router"]
