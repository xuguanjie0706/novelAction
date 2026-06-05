"""HookRegistry — 构图期烘焙的 prompt / ctx 注入点。"""
from __future__ import annotations

from app.services.bootstrap.pipeline.node_spec import CtxEnricher, NodeSpec, PowerSystemProfile, PromptHook


class HookRegistry:
    """每个 CompiledGraph 持有独立快照，避免并发竞态。"""

    def __init__(self) -> None:
        self._hooks: dict[str, list[PromptHook]] = {}
        self._enrichers: dict[str, list[CtxEnricher]] = {}
        self._power_profile: PowerSystemProfile | None = None

    @classmethod
    def from_specs(cls, specs: list[NodeSpec]) -> HookRegistry:
        reg = cls()
        for spec in specs:
            reg.register_spec(spec)
        return reg

    def register_spec(self, spec: NodeSpec) -> None:
        for hook in spec.prompt_hooks:
            self._hooks.setdefault(hook.target_step, []).append(hook)
        for enricher in spec.ctx_enrichers:
            self._enrichers.setdefault(enricher.before_step, []).append(enricher)
        if spec.power_profile is not None:
            self._power_profile = spec.power_profile

    def collect(self, step: str, ctx: dict) -> str:
        blocks = [h.fn(ctx) for h in self._hooks.get(step, [])]
        return "\n".join(b for b in blocks if b)

    def enrich(self, step: str, ctx: dict) -> dict:
        updates: dict = {}
        for enricher in self._enrichers.get(step, []):
            updates.update(enricher.fn(ctx))
        return updates

    def get_power_profile(self) -> PowerSystemProfile | None:
        return self._power_profile
