"""Bootstrap Pipeline 节点与风格声明类型。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class PromptHook:
    """向共享步骤的 prompt 末尾追加约束块。"""

    target_step: str
    fn: Callable[[dict], str]


@dataclass
class CtxEnricher:
    """在某步骤执行前向 ctx 注入键值（纯函数，无 LLM）。"""

    before_step: str
    fn: Callable[[dict], dict]


@dataclass
class PowerSystemProfile:
    """声明替代通用 power_systems 节点的行为配置。"""

    system_type_resolver: Callable[[dict], str]
    use_sub_levels_resolver: Callable[[dict], bool] | None = None


@dataclass
class NodeSpec:
    """全局节点目录条目。"""

    key: str
    fn: Callable
    seq: int
    label: str = ""
    graph_id: str = ""
    gate_after: bool = False
    interrupt_before: bool = False
    is_positioning: bool = False
    replaces: str | None = None
    prompt_hooks: list[PromptHook] = field(default_factory=list)
    ctx_enrichers: list[CtxEnricher] = field(default_factory=list)
    power_profile: PowerSystemProfile | None = None

    @property
    def node_id(self) -> str:
        return self.graph_id or self.key


@dataclass
class StyleConfig:
    """风格注册表条目：声明激活哪些节点及默认参数。"""

    style_id: str
    display_name: str
    nodes: list[str]
    default_writing_style: str = "standard"
    converge_fn: Callable[..., Any] | None = None
    skip_core: frozenset[str] = field(default_factory=frozenset)
