"""已废弃：旧 /bootstrap/stream 端点（曾支持 single_shot / sequential 两种模式）。

single_shot 模式已移除；sequential 已迁移到 /api/v1/bootstrap/runs（bootstrap_graph.py）。
本文件保留空路由以避免其他 import 路径断裂，待统一清理时一并删除。
"""
from fastapi import APIRouter

router = APIRouter(prefix="/bootstrap", tags=["bootstrap-legacy"])
