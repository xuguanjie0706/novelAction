"""Bootstrap 可组合 Pipeline 框架。"""
from app.services.bootstrap.pipeline import register_nodes  # noqa: F401 — 副作用注册
from app.services.bootstrap.pipeline.builder import build_graph, get_graph_hooks
from app.services.bootstrap.pipeline.runner import resume_pipeline, run_pipeline
from app.services.bootstrap.pipeline.styles import STYLE_REGISTRY, get_style

__all__ = [
    "build_graph",
    "get_graph_hooks",
    "get_style",
    "resume_pipeline",
    "run_pipeline",
    "STYLE_REGISTRY",
]
