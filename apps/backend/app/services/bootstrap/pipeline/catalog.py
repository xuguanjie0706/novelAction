"""全局节点目录 NODE_CATALOG。"""
from __future__ import annotations

from typing import Callable

from app.services.bootstrap.pipeline.node_spec import NodeSpec

_CATALOG: dict[str, NodeSpec] = {}


def register_node(spec: NodeSpec) -> NodeSpec:
    """注册节点；重复 key 时覆盖（测试场景）。"""
    _CATALOG[spec.key] = spec
    return spec


def node(
    key: str,
    seq: int,
    fn: Callable,
    *,
    label: str = "",
    graph_id: str = "",
    **kwargs,
) -> Callable:
    """装饰器：把函数注册进全局目录。"""

    register_node(
        NodeSpec(
            key=key,
            fn=fn,
            seq=seq,
            label=label,
            graph_id=graph_id,
            **kwargs,
        )
    )
    return fn


def get_node(key: str) -> NodeSpec:
    if key not in _CATALOG:
        raise KeyError(f"节点 '{key}' 未注册，请检查 pipeline/register_nodes.py")
    return _CATALOG[key]


def all_nodes() -> dict[str, NodeSpec]:
    return dict(_CATALOG)


def clear_catalog() -> None:
    """仅测试用：清空目录。"""
    _CATALOG.clear()
