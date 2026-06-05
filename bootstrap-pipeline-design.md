# Bootstrap Pipeline 可组合架构设计

## 一、一个关键前提

LangGraph 的图是**编译时静态确定**的，节点和边不能运行时动态增减。  
所以「一个图」的正确理解是：

> **一个图构建框架（PipelineBuilder）**  
> 在服务启动或首次请求时，按风格配置组装出对应的 CompiledGraph

不同风格 = 不同节点集合 → 同一个 `build_graph()` 构建出不同的图实例。  
**框架只有一套，行为靠节点声明驱动，不存在 if-else。**

---

## 二、整体思路

```
┌─────────────────────────────────────────────────────┐
│  NODE_CATALOG（全局节点目录）                          │
│  每个节点声明：名称 / 函数 / 顺序号 / 挂接哪些 hook      │
├─────────────────────────────────────────────────────┤
│  STYLE_REGISTRY（风格注册表）                          │
│  每种风格声明：激活哪些节点 / 默认参数                    │
├─────────────────────────────────────────────────────┤
│  build_graph(style_id)                               │
│  → 取出节点集合 → 按顺序号排序 → 自动连边 → 编译         │
├─────────────────────────────────────────────────────┤
│  HookRegistry（prompt 注入点）                        │
│  共享节点调用 collect(step, ctx)，无 if-else            │
└─────────────────────────────────────────────────────┘
```

**增加新风格**：向 CATALOG 注册新节点 + 在 STYLE_REGISTRY 新增一行配置。  
**删除某节点**：从风格配置里去掉节点名，builder 自动跳过并重新连边。  
**不改任何已有代码。**

---

## 三、顺序号（sequence_order）：解决排序问题

用一个整数表示节点在流水线中的全局位置。  
相邻节点自动连边；同一风格的多个节点按顺序号依次串联。

```
0   ── 保留
100 ── positioning（每个风格提供自己的版本）
150 ── gate（立项确认，可选）
200 ── project

300-399 ── 前置创意设计区（pre_world）
  301  contrast_design       [番茄]
  302  golden_finger         [番茄]
  303  face_slap_map         [番茄]
  304  power_ladder          [番茄]
  305  ctx_bridge            [番茄]
  311  canon_pack            [同人]
  312  deviation_contract    [同人]
  313  entry_hook            [同人]
  320  cultivation_design    [修仙，未来]
  330  campus_setup          [校园，未来]

400 ── power_systems（通用 / 各风格可 override）
499 ── gate_power（可选）

500 ── factions
510 ── storylines
520 ── antagonist_ladder
530 ── canon_characters   [同人，插在 characters 之前]

600 ── characters
650 ── gate_characters（可选）
700 ── skills_items
710 ── settings

800 ── volumes
850 ── gate_volumes（可选）
860 ── emotion_villain
870 ── rhythm_map         [番茄/同人]

900 ── memory_relations
910 ── core_mysteries
920 ── opening_contract
940 ── consistency_scan
950 ── signal_audit       [番茄]
960 ── canon_audit        [同人]
999 ── （convergence 由 builder 隐式插入）
```

顺序号的命名段落：
- 0-199：框架必须步骤
- 300-399：pre_world 创意设计（最常扩展的区域）
- 400-799：世界构建
- 800-899：卷级结构
- 900-999：校验与收敛

---

## 四、核心数据结构

### 4.1 NodeSpec

```python
# pipeline/node_spec.py

from dataclasses import dataclass, field
from typing import Callable, Literal

@dataclass
class NodeSpec:
    name: str
    fn: Callable                          # async (state, config) -> dict
    seq: int                              # 全局顺序号，决定在流水线中的位置
    label: str = ""                       # SSE step_start 展示文案
    gate_after: bool = False              # 是否在此节点后插入 interrupt 闸门
    is_positioning: bool = False          # 是否是立项节点（影响 START → 首节点连边）
    prompt_hooks: list["PromptHook"] = field(default_factory=list)
    ctx_enrichers: list["CtxEnricher"] = field(default_factory=list)
    power_profile: "PowerSystemProfile | None" = None  # 非 None 时覆盖 power_systems 行为
```

### 4.2 PromptHook 和 CtxEnricher

```python
@dataclass
class PromptHook:
    """向某共享步骤的 prompt 末尾追加约束块。"""
    target_step: str                      # 要注入的步骤名，如 "volumes"
    fn: Callable[[dict], str]             # ctx -> 文本块（空串 = 跳过）

@dataclass
class CtxEnricher:
    """在某步骤执行前向 ctx 注入键值（纯函数，无 LLM）。"""
    before_step: str                      # 哪个步骤执行前运行
    fn: Callable[[dict], dict]            # ctx -> 增量 dict（merge 进 ctx）
```

### 4.3 StyleConfig

```python
@dataclass
class StyleConfig:
    style_id: str
    display_name: str
    nodes: list[str]                      # 激活哪些 NodeSpec.name（有序无关，builder 按 seq 排）
    default_writing_style: str = "standard"
    default_pace_type: str = "normal"
    converge_fn: Callable | None = None   # Bootstrap 最后一步后的 DB 归一化
```

---

## 五、节点目录（NODE_CATALOG）

```python
# pipeline/catalog.py

_CATALOG: dict[str, NodeSpec] = {}

def node(seq: int, label: str = "", gate_after: bool = False, **kwargs):
    """注册装饰器：把函数注册进全局目录。"""
    def decorator(fn: Callable) -> Callable:
        name = fn.__name__.removeprefix("node_")
        _CATALOG[name] = NodeSpec(
            name=name, fn=fn, seq=seq, label=label,
            gate_after=gate_after, **kwargs,
        )
        return fn
    return decorator

def get_node(name: str) -> NodeSpec:
    if name not in _CATALOG:
        raise KeyError(f"节点 '{name}' 未注册，请检查 @node 装饰器")
    return _CATALOG[name]
```

注册节点只需一行装饰器，例如：

```python
# steps/fanqie/golden_finger.py

@node(seq=302, label="设计金手指工程...",
      prompt_hooks=[PromptHook("volumes", _fanqie_volumes_block),
                    PromptHook("characters", _fanqie_char_block)])
async def node_golden_finger(state, config=None):
    ...
```

```python
# steps/power_systems/__init__.py

@node(seq=400, label="生成力量/境界体系...")
async def node_power_systems(state, config=None):
    ...

# 番茄的 power_ladder 注册时声明 power_profile，
# 由 builder 检测到后跳过通用 power_systems 节点
@node(seq=304, label="构建权力阶梯（最小化世界观）...",
      power_profile=PowerSystemProfile(
          system_type_resolver=_resolve_by_archetype,  # 动态判断 cultivation or social
          use_sub_levels_resolver=_resolve_sub_levels,
      ))
async def node_power_ladder(state, config=None):
    ...
```

---

## 六、HookRegistry：共享步骤无感注入

```python
# pipeline/hooks.py

class HookRegistry:
    _hooks: dict[str, list[PromptHook]] = {}
    _enrichers: dict[str, list[CtxEnricher]] = {}

    @classmethod
    def reset(cls):
        cls._hooks.clear()
        cls._enrichers.clear()

    @classmethod
    def register_spec(cls, spec: NodeSpec):
        for h in spec.prompt_hooks:
            cls._hooks.setdefault(h.target_step, []).append(h)
        for e in spec.ctx_enrichers:
            cls._enrichers.setdefault(e.before_step, []).append(e)

    @classmethod
    def collect(cls, step: str, ctx: dict) -> str:
        """共享步骤 prompt builder 调用此方法，返回所有活跃风格的约束块。"""
        blocks = [h.fn(ctx) for h in cls._hooks.get(step, [])]
        return "\n".join(b for b in blocks if b)

    @classmethod
    def enrich(cls, step: str, ctx: dict) -> dict:
        """节点执行前自动 merge 所有 enricher 的结果。"""
        updates = {}
        for e in cls._enrichers.get(step, []):
            updates.update(e.fn(ctx))
        return updates
```

**共享步骤 volumes.py 改造（一行替换）：**

```python
# 之前（每加一种风格就加一行）：
fanfic_block = build_fanfic_volumes_block(ctx)   # 同人
fanqie_block = build_fanqie_volumes_block(ctx)   # 番茄（待加）
school_block = build_school_volumes_block(ctx)   # 校园（待加）...

# 之后（永远只有这一行）：
style_block = HookRegistry.collect("volumes", ctx)
```

---

## 七、图构建器（PipelineBuilder）

```python
# pipeline/builder.py

# 核心节点：任何风格都必须包含
CORE_NODES = {"project", "factions", "storylines", "antagonist_ladder",
              "characters", "skills_items", "settings", "volumes",
              "emotion_villain", "memory_relations", "core_mysteries",
              "opening_contract", "consistency_scan"}


def build_graph(config: StyleConfig, checkpointer) -> CompiledGraph:
    # ── 1. 收集节点集合 ──────────────────────────────────────
    all_names = CORE_NODES | set(config.nodes)
    specs = [get_node(n) for n in all_names]
    specs.sort(key=lambda s: s.seq)          # 按顺序号排列

    # ── 2. 处理 power_systems 覆盖 ───────────────────────────
    # 若任一激活节点声明了 power_profile，则跳过通用 power_systems
    if any(s.power_profile for s in specs):
        specs = [s for s in specs if s.name != "power_systems"]

    # ── 3. 注册所有 hooks 和 enrichers ───────────────────────
    HookRegistry.reset()
    for spec in specs:
        HookRegistry.register_spec(spec)

    # ── 4. 构建 StateGraph ───────────────────────────────────
    g = StateGraph(BootstrapState)
    
    # 定位节点（positioning 由风格配置提供，否则用通用版）
    pos_name = next((s.name for s in specs if s.is_positioning), "positioning_general")
    
    wrapped = [_wrap(s) for s in specs]    # 自动 inject enrichers + step 事件
    for name, fn in wrapped:
        g.add_node(name, fn)

    # ── 5. 连边：线性串联，gate_after=True 的节点后插入闸门节点 ──
    chain = [START] + [name for name, _ in wrapped] + [END]
    gates = []
    final_chain = []
    for i, name in enumerate(chain[1:-1]):
        spec = get_node(name) if name not in (START, END) else None
        final_chain.append(name)
        if spec and spec.gate_after:
            gate_name = f"gate_{name}"
            g.add_node(gate_name, _make_gate_node(gate_name))
            final_chain.append(gate_name)
            gates.append(gate_name)

    for a, b in zip([START] + final_chain, final_chain + [END]):
        g.add_edge(a, b)

    # ── 6. 收敛节点（隐式插入，归一化 DB）────────────────────
    if config.converge_fn:
        g.add_node("__converge__", _make_converge_node(config.converge_fn))
        # 接在 consistency_scan 后、END 前

    return g.compile(checkpointer=checkpointer, interrupt_before=gates)
```

**`_wrap` 自动注入 enrichers + SSE 事件（替代三套重复的 `_run_step`）：**

```python
def _wrap(spec: NodeSpec) -> tuple[str, Callable]:
    async def wrapped_node(state, config=None):
        config = _resolve_config(config)
        db = config["configurable"]["db"]
        run_id = _state_run_id(state, config)

        # 执行前 enrichers
        ctx = dict(state.get("ctx") or {})
        ctx.update(HookRegistry.enrich(spec.name, ctx))

        # SSE + 超时 + 重试（所有节点统一逻辑）
        emit(run_id, "step_start", db, step=spec.name, label=spec.label)
        project = _get_project(state, config) if spec.requires_project else None
        try:
            result = await asyncio.wait_for(
                spec.fn(state | {"ctx": ctx}, config),
                timeout=300.0,
            )
        except Exception as exc:
            emit(run_id, "error", db, step=spec.name, message=str(exc))
            raise
        emit(run_id, "step_done", db, step=spec.name)
        return result

    return spec.name, wrapped_node
```

**这一个 `_wrap` 替代了三套图里各自的 `_run_step` / `_fanqie_step` / `_fanfic_step`。**

---

## 八、风格注册表（STYLE_REGISTRY）

```python
# pipeline/styles/__init__.py

STYLE_REGISTRY: dict[str, StyleConfig] = {

    "sequential": StyleConfig(
        style_id="sequential",
        display_name="通用",
        nodes=[
            "positioning_general",
            "power_systems",
        ],
    ),

    "fanqie": StyleConfig(
        style_id="fanqie",
        display_name="番茄",
        nodes=[
            "positioning_fanqie",       # seq=100，替换通用立项
            "contrast_design",          # seq=301
            "golden_finger",            # seq=302
            "face_slap_map",            # seq=303
            "power_ladder",             # seq=304，声明了 power_profile，自动跳过 power_systems
            "ctx_bridge",               # seq=305
            "rhythm_map",               # seq=870
            "signal_audit",             # seq=950
        ],
        default_writing_style="plain",
        converge_fn=converge_fanqie_project,
    ),

    "fanfic": StyleConfig(
        style_id="fanfic",
        display_name="同人",
        nodes=[
            "positioning_fanfic",       # seq=100
            "canon_pack",               # seq=311
            "deviation_contract",       # seq=312
            "entry_hook",               # seq=313
            "canon_power",              # seq=306（在 power_ladder 区域）
            "canon_characters",         # seq=530（characters 之前）
            "rhythm_map",               # seq=870
            "canon_audit",              # seq=960
        ],
        default_writing_style="plain",
        converge_fn=converge_fanfic_project,
    ),

    # ── 未来新增，不改上面任何一行 ────────────────────────────

    # "xianxia": StyleConfig(
    #     style_id="xianxia",
    #     nodes=["positioning_xianxia", "dao_heart_design", "sect_design",
    #            "tribulation_map", "path_design"],
    # ),

    # "school_drama": StyleConfig(
    #     style_id="school_drama",
    #     nodes=["positioning_school", "campus_setup", "rivalry_map",
    #            "romance_design"],
    # ),

    # 可组合（番茄 + 修仙能力体系）：
    # "fanqie_xianxia": StyleConfig(
    #     style_id="fanqie_xianxia",
    #     nodes=STYLE_REGISTRY["fanqie"].nodes + ["cultivation_design", "dao_heart_design"],
    # ),
}
```

---

## 九、路由层（bootstrap_graph.py）改造

```python
# 之前（每加一种风格加一段 if-else）：
if req.mode == "fanfic":
    _run_fn = run_bootstrap_fanfic
elif req.mode == "fanqie":
    _run_fn = run_bootstrap_fanqie
else:
    _run_fn = run_bootstrap

# 之后（永远只有这三行）：
config = STYLE_REGISTRY[req.mode]
graph = build_graph(config, checkpointer)
asyncio.create_task(run_pipeline(graph, run_id, ...))
```

**新增风格只需在 STYLE_REGISTRY 加一条，路由层零改动。**

---

## 十、境界体系问题的根治

`NodeSpec.power_profile` 的 `system_type_resolver` 是一个函数，**运行时**根据 ctx 动态判断：

```python
def _fanqie_power_type(ctx: dict) -> Literal["cultivation", "social"]:
    archetype = (ctx.get("fanqie_positioning") or {}).get("genre_archetype", "")
    if any(k in archetype for k in ("修仙", "古武", "系统", "末世", "星际")):
        return "cultivation"
    return "social"      # 都市/赘婿/神豪 → 社会阶梯，禁用「初期/圆满」写法

def _fanqie_sub_levels(ctx: dict) -> bool:
    return _fanqie_power_type(ctx) == "cultivation"
```

`power_systems` 通用节点改为：

```python
@node(seq=400, label="生成力量/境界体系...")
async def node_power_systems(state, config=None):
    ctx = state.get("ctx") or {}
    # 查找当前激活节点中是否有 power_profile 声明
    profile = HookRegistry.get_power_profile(ctx)
    system, prompt = profile.build_prompt(ctx)
    ...
```

不再存在 `is_fanqie_project()` 这种侦探式 if-else。

---

## 十一、迁移路径

```
阶段 0（新建基础设施，≤3天）
  pipeline/
    node_spec.py        NodeSpec / PromptHook / CtxEnricher / PowerSystemProfile
    hooks.py            HookRegistry
    builder.py          build_graph / _wrap
    styles/__init__.py  STYLE_REGISTRY（空壳，只有 "sequential"）

阶段 1（迁移通用线，≤1天）
  把 graph_nodes.py 里的通用节点加 @node 装饰器注册进 CATALOG
  把 volumes.py 里的 build_fanfic_volumes_block 改为 HookRegistry.collect("volumes", ctx)
  graph.py 改用 build_graph(STYLE_REGISTRY["sequential"], ...)

阶段 2（迁移番茄线，≤2天）
  把 graph_fanqie.py 里的节点函数加 @node 装饰器
  把 fanqie prompt hooks 注册进各节点的 NodeSpec.prompt_hooks
  STYLE_REGISTRY["fanqie"] 填好节点列表
  graph_fanqie.py 降为 2 行空壳（re-export 兼容旧 import）

阶段 3（迁移同人线 + 修复境界体系，≤2天）
  同上；同时修复 PowerSystemProfile 的 type_resolver，消除 is_fanqie_project()

阶段 4（清理，≤1天）
  删除 graph_fanqie.py / graph_fanfic.py 旧实现
  删除 context_assembler.py 里的 is_fanqie_project() if-else
  净减少约 1200 行代码
```

---

## 十二、效果验证

| 操作 | 改动范围 |
|------|---------|
| 新增「校园热血」风格 | 新建 `styles/school.py`（~150行）+ STYLE_REGISTRY 加一行 |
| 删除某风格的一个节点 | STYLE_REGISTRY 对应 nodes 列表删掉该名字 |
| 修改某节点逻辑 | 改对应的节点函数文件，其他零影响 |
| 共享步骤（volumes）加新约束 | 在对应节点的 `prompt_hooks` 里加一个 PromptHook |
| 组合两种风格 | STYLE_REGISTRY 新增一条，nodes 合并两个列表 |
| 修复番茄境界名奇怪 | 改 `power_ladder` 的 `PowerSystemProfile.type_resolver` |
