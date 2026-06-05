"""PipelineBuilder — 按风格配置组装 CompiledGraph。"""
from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from app.services.bootstrap.pipeline.catalog import get_node
from app.services.bootstrap.pipeline.hooks import HookRegistry
from app.services.bootstrap.pipeline.node_spec import NodeSpec, StyleConfig

# 任何风格默认并入的核心步骤（不含 positioning / 风格专属 / 闸门）
CORE_NODES: frozenset[str] = frozenset({
    "project",
    "factions",
    "storylines",
    "antagonist_ladder",
    "characters",
    "skills_items",
    "settings",
    "volumes",
    "emotion_villain",
    "memory_relations",
    "core_mysteries",
    "opening_contract",
    "consistency",
})


def _resolve_active_keys(config: StyleConfig) -> list[str]:
    """合并 CORE + 风格节点，处理 replaces / power_profile 覆盖。"""
    names = set(CORE_NODES) | set(config.nodes)
    names -= set(config.skip_core)

    specs = [get_node(k) for k in names]
    for spec in specs:
        if spec.replaces:
            names.discard(spec.replaces)

    if any(s.power_profile for s in specs):
        names.discard("power_systems")

    return sorted(names, key=lambda k: get_node(k).seq)


def _wrap_node(spec: NodeSpec, hooks: HookRegistry):
    """执行前 merge ctx enrichers（节点函数本身负责 SSE / 重试）。"""
    async def wrapped(state, config=None):
        ctx = dict(state.get("ctx") or {})
        patch = hooks.enrich(spec.key, ctx)
        if patch:
            merged = {**state, "ctx": {**ctx, **patch}}
            return await spec.fn(merged, config)
        return await spec.fn(state, config)

    return wrapped


def build_graph(
    config: StyleConfig,
    checkpointer: Any,
    *,
    state_type: Any,
) -> Any:
    """按 StyleConfig 构建并编译 LangGraph。"""
    active_keys = _resolve_active_keys(config)
    specs = [get_node(k) for k in active_keys]
    hooks = HookRegistry.from_specs(specs)

    g = StateGraph(state_type)
    chain_ids: list[str] = []
    interrupt_before: list[str] = []

    for spec in specs:
        node_id = spec.node_id
        g.add_node(node_id, _wrap_node(spec, hooks))
        chain_ids.append(node_id)
        if spec.interrupt_before:
            interrupt_before.append(node_id)

    # 线性连边
    flow = [START, *chain_ids, END]
    for a, b in zip(flow, flow[1:]):
        g.add_edge(a, b)

    compiled = g.compile(
        checkpointer=checkpointer,
        interrupt_before=interrupt_before or None,
    )
    # 烘焙 hooks 供共享步骤 prompt 读取（同进程单图安全）
    compiled._pipeline_hooks = hooks  # type: ignore[attr-defined]
    compiled._style_config = config  # type: ignore[attr-defined]
    return compiled


def get_graph_hooks(graph: Any) -> HookRegistry | None:
    return getattr(graph, "_pipeline_hooks", None)
