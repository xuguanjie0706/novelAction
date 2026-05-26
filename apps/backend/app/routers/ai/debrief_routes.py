"""
debrief_routes.py — 复盘端点聚合壳

拆分说明：
  chapter_debrief_route.py  → POST /ai/chapter-debrief
  auto_debrief_route.py     → POST /ai/auto-debrief
  debrief_chapter_core.py   → 业务辅助函数（人物/故事线/承诺等各处理块）

本文件仅做 router 聚合，保持对 ai/__init__.py 的向后兼容。
"""

from fastapi import APIRouter

from app.routers.ai import auto_debrief_route, chapter_debrief_route

router = APIRouter()
router.include_router(chapter_debrief_route.router)
router.include_router(auto_debrief_route.router)
