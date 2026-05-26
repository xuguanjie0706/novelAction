"""
scene_routes.py — 三层调度 AI 端点（聚合壳）

拆分说明：
  scene_plan_routes.py   → /ai/scene-plan-save + /ai/scene-plan
  scene_draft_routes.py  → /ai/scene-draft/stream
  scene_stitch_routes.py → /ai/scene-stitch

本文件仅做 router 聚合，保持对 ai/__init__.py 的向后兼容。
"""

from fastapi import APIRouter

from app.routers.ai import scene_draft_routes, scene_plan_routes, scene_stitch_routes

router = APIRouter()
router.include_router(scene_plan_routes.router)
router.include_router(scene_draft_routes.router)
router.include_router(scene_stitch_routes.router)
