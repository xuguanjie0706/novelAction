# Bootstrap 可组合风格包架构设计

> 目标：彻底消除三套平行 graph + 共享步骤里的 if-else 分支，  
> 让任何新题材只需新建一个 StylePack 文件即可接入，无需改动现有代码。

---

## 一、现状问题诊断

### 1.1 重复的图骨架

三套图（`graph.py` / `graph_fanqie.py` / `graph_fanfic.py`）本质上是**同一个步骤序列的三个拷贝**，
差异只在「哪几步被替换 / 哪几步被插入」：

```
通用线:   positioning → gate → project → power_systems → factions → ... → volumes → ...
番茄线:   fanqie_pos  → gate → project → [contrast+gf+fsm+ladder+bridge] → factions → ... → [rhythm] → ...
同人线:   fanfic_pos  → gate → project → [canon_pack+...+canon_power+canon_chars] → volumes → [rhythm+audit] → ...
```

三套图还各自复制了 `_run_step` / `_fanqie_step` / `_fanfic_step`——100 行几乎一模一样的步骤运行器。

### 1.2 共享步骤里的风格 if-else

`volumes.py` 里已经有 `build_fanfic_volumes_block(ctx)`，
`fanqie_realm_policy.py` 里 `is_fanqie_project()` 在写章注入处也是 if-else。
每新增一种风格，就在这些地方插一段新的 if-else——这是最终腐化成上帝文件的路径。

### 1.3 境界体系的硬编码

番茄书的境界体系取决于 `genre_archetype`，但这个判断现在散落在多处：
`fanqie_normalize.py` / `fanqie_realm_policy.py` / `context_assembler.py`，
靠 `is_fanqie_project()` 的 if-else 把社会阶梯和修炼体系区分开来。

---

## 二、新架构：StylePack + 钩子注册表

### 2.1 核心思想

```
每种「风格」= 一个 StylePack 文件
每次生成   = graph_builder.build(active_packs) 动态组装一张图
共享步骤   = 查询 HookRegistry，收集所有活跃 Pack 贡献的 prompt 块
```

**不存在风格间的 if-else，只有「当前 ctx 中哪些 Pack 被激活」。**

### 2.2 目录结构

```
services/bootstrap/
  style_pack.py            # StylePack dataclass + HookRegistry（新建，≤150行）
  graph_builder.py         # 从 Pack 列表构建 LangGraph（新建，≤200行）
  styles/
    __init__.py            # STYLE_REGISTRY: dict[str, list[StylePack]]
    general.py             # 通用风格包（现有通用线提炼）
    fanqie.py              # 番茄风格包（现有番茄线提炼）
    fanfic.py              # 同人风格包（现有同人线提炼）
    # 未来扩展：xianxia.py / urban.py / system_upgrade.py ...
  graph.py                 # 只保留 State 定义 + checkpointer + graph 全局变量
  graph_nodes.py           # 通用步骤节点（改为查 HookRegistry，消除 if-else）
  graph_builder.py         # 新增
  style_pack.py            # 新增
```

旧的 `graph_fanqie.py` / `graph_fanfic.py` 降级为「过渡期薄壳」，
最终可安全删除。

---

## 三、StylePack 接口定义

```python
# style_pack.py

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable, Literal

# ── 步骤注入 ──────────────────────────────────────────────────────
@dataclass
class InjectedStep:
    """声明一个额外步骤以及它在标准流水线中的位置。"""
    name: str
    node_fn: Callable                      # async node function
    after: str | None = None               # 插在哪个标准步骤之后
    before: str | None = None              # 插在哪个标准步骤之前（与 after 二选一）
    replaces: str | None = None            # 完全替换某个标准步骤

# ── Prompt 钩子 ────────────────────────────────────────────────────
@dataclass
class PromptHook:
    """向某个共享步骤的 prompt 末尾追加一个约束块。"""
    step: str                              # 目标步骤名，如 "volumes" / "factions"
    fn: Callable[[dict], str]              # ctx -> 文本块（空串 = 不追加）
    slot: Literal["constraint", "end"] = "end"

# ── Ctx 预处理器 ───────────────────────────────────────────────────
@dataclass
class CtxEnricher:
    """在某步骤执行前向 ctx 注入额外键值（纯函数，无 LLM 调用）。"""
    before_step: str
    fn: Callable[[dict], dict]             # ctx -> 增量 dict（merge 进 ctx）

# ── 境界体系声明 ───────────────────────────────────────────────────
@dataclass
class PowerSystemProfile:
    """声明本风格的境界/力量体系行为，代替 is_fanqie_project() 的 if-else。"""
    system_type: Literal["cultivation", "social", "ability", "mixed", "auto"]
    # auto = 由 gen_power_systems 通用逻辑自行判断（通用线默认）
    use_sub_levels: bool = True            # 是否允许「初期/中期/后期/圆满」小境写法
    # 自定义 prompt builder（None = 走通用 build_legacy/xianxia_power_prompt）
    prompt_builder: Callable[[dict], tuple[str, str]] | None = None
    # 写章/复盘注入的境界铁律块生成器（None = 走通用逻辑）
    realm_block_builder: Callable[[list[str]], str] | None = None

# ── 风格包主体 ─────────────────────────────────────────────────────
@dataclass
class StylePack:
    style_id: str
    display_name: str

    # 1. 自定义立项节点（替换通用 node_positioning）
    positioning_node: Callable | None = None
    positioning_gate_node: Callable | None = None

    # 2. 额外步骤
    injected_steps: list[InjectedStep] = field(default_factory=list)

    # 3. Prompt 钩子（多 Pack 可同时注册同一步骤，按注册顺序拼接）
    prompt_hooks: list[PromptHook] = field(default_factory=list)

    # 4. Ctx 预处理器
    ctx_enrichers: list[CtxEnricher] = field(default_factory=list)

    # 5. 境界/力量体系声明
    power_profile: PowerSystemProfile = field(
        default_factory=lambda: PowerSystemProfile(system_type="auto")
    )

    # 6. 收敛函数（Bootstrap 最后一步后调用，归一化 DB 数据）
    converge_fn: Callable | None = None

    # 7. 写作期钩子（写章注入、复盘约束，供 context_assembler 查询）
    writing_hooks: dict[str, Callable[[dict], str]] = field(default_factory=dict)
    # 键名示例: "realm_discipline" / "draft_constraint" / "debrief_constraint"

    # 8. 默认值
    default_writing_style: str = "standard"
    default_pace_type: str = "normal"

    # 9. 激活检测（判断当前 ctx 是否属于本风格；graph_builder 用此跳过无关 Pack）
    def is_active(self, ctx: dict) -> bool:
        """默认：ctx 中存在 f'{style_id}_positioning' 键即视为激活。"""
        return bool(ctx.get(f"{self.style_id}_positioning"))
```

---

## 四、HookRegistry：共享步骤的插件接入点

```python
# style_pack.py（续）

class HookRegistry:
    """
    全局钩子注册表。
    
    共享步骤 prompt builder 调用 HookRegistry.collect(step, ctx) 获取
    所有活跃 Pack 贡献的约束块，拼接后追加到 prompt 末尾。
    不再需要 if-else。
    """
    _hooks: dict[str, list[PromptHook]] = {}

    @classmethod
    def register(cls, pack: StylePack) -> None:
        for hook in pack.prompt_hooks:
            cls._hooks.setdefault(hook.step, []).append(hook)

    @classmethod
    def collect(cls, step: str, ctx: dict) -> str:
        """收集所有对 step 注册的钩子，返回拼接后的约束文本（空串 = 无贡献）。"""
        blocks = [h.fn(ctx) for h in cls._hooks.get(step, [])]
        return "\n".join(b for b in blocks if b)

    @classmethod
    def collect_enrichers(cls, step: str, ctx: dict) -> dict:
        """收集所有 before_step=step 的 CtxEnricher 合并结果。"""
        ...
```

---

## 五、通用步骤如何改造（以 volumes.py 为例）

**改造前（if-else）：**
```python
def build_volumes_prompt(project, ctx):
    fanfic_block = build_fanfic_volumes_block(ctx)   # 硬编码 fanfic 检测
    # 未来再加番茄专属块就要再加一行
    ...
    prompt = f"...{fanfic_block}..."
```

**改造后（查 HookRegistry）：**
```python
def build_volumes_prompt(project, ctx):
    style_block = HookRegistry.collect("volumes", ctx)  # 所有活跃 Pack 贡献
    ...
    prompt = f"...{style_block}..."
```

fanfic 的 `build_fanfic_volumes_block` 变成 fanfic Pack 的一个 `PromptHook`：
```python
# styles/fanfic.py
PromptHook(
    step="volumes",
    fn=lambda ctx: build_fanfic_volumes_block(ctx),  # 函数体不变，只是移位置
)
```

番茄 Pack 也注册一个：
```python
# styles/fanqie.py
PromptHook(
    step="volumes",
    fn=lambda ctx: build_fanqie_volumes_block(ctx),  # 新增；含金手指阶段/打脸节奏块
)
```

**写章注入（context_assembler.py）同理：**

```python
# 改造前
if is_fanqie_project(project):
    realm_block = build_fanqie_realm_discipline_block(names)

# 改造后
realm_block = HookRegistry.collect_writing("realm_discipline", ctx)
# fanqie Pack 的 writing_hooks["realm_discipline"] 注册了 build_fanqie_realm_discipline_block
# 通用 Pack 注册了通用版本；两者同时存在时后者兜底
```

---

## 六、GraphBuilder：从 Pack 列表动态组装图

```python
# graph_builder.py

BASE_CHAIN = [
    "project", "power_systems",
    "factions", "storylines", "antagonist_ladder",
    "characters", "gate_characters",
    "skills_items", "settings",
    "volumes", "gate_volumes",
    "emotion_villain",
    "memory_relations", "core_mysteries", "opening_contract",
    "consistency_scan",
]

def build_graph(packs: list[StylePack], checkpointer) -> CompiledGraph:
    # 1. 确定 positioning 节点
    pos_pack = next((p for p in packs if p.positioning_node), None)

    # 2. 把所有 InjectedStep 按 after/before/replaces 插入 BASE_CHAIN
    full_chain = _resolve_chain(BASE_CHAIN, packs)

    # 3. 注册所有 HookRegistry（prompt hooks + ctx enrichers）
    HookRegistry.reset()
    for pack in packs:
        HookRegistry.register(pack)

    # 4. 构建 StateGraph
    g = StateGraph(BootstrapState)
    for name, fn in _resolve_nodes(full_chain, pos_pack, packs):
        g.add_node(name, _wrap_with_enrichers(name, fn, packs))
    for a, b in zip([START] + full_chain, full_chain + [END]):
        g.add_edge(a, b)

    # 5. 确定 interrupt_before
    gates = _collect_gates(packs)

    return g.compile(checkpointer=checkpointer, interrupt_before=gates)
```

**`_wrap_with_enrichers`** 在每个节点执行前自动运行对应 Pack 的 `CtxEnricher`：

```python
def _wrap_with_enrichers(step: str, fn: Callable, packs: list[StylePack]) -> Callable:
    enrichers = [e for p in packs for e in p.ctx_enrichers if e.before_step == step]
    if not enrichers:
        return fn
    async def wrapped(state, config=None):
        ctx = dict(state.get("ctx") or {})
        for e in enrichers:
            ctx.update(e.fn(ctx))
        return await fn({**state, "ctx": ctx}, config)
    return wrapped
```

---

## 七、写完后的 API 路由（消除 if-else）

```python
# bootstrap_graph.py（路由层）

# 注册表：mode -> Pack 列表（可组合）
STYLE_REGISTRY: dict[str, list[StylePack]] = {
    "sequential":    [GENERAL_PACK],
    "fanqie":        [FANQIE_PACK],
    "fanfic":        [FANFIC_PACK],
    # 未来：只加一行，不改已有代码
    "xianxia":       [XIANXIA_PACK],
    "urban":         [URBAN_PACK],
    "school_drama":  [SCHOOL_DRAMA_PACK],
    # 可组合：番茄 + 修仙能力体系
    "fanqie_xianxia": [FANQIE_PACK, XIANXIA_POWER_PACK],
}

@router.post("/runs")
async def start_bootstrap(req: BootstrapStartRequest):
    packs = STYLE_REGISTRY.get(req.mode, [GENERAL_PACK])
    graph = build_graph(packs, checkpointer)   # 动态组装
    ...
```

---

## 八、境界体系问题的彻底修复

番茄书的「境界奇怪」根因：`PowerSystemProfile` 是隐式的（靠 `is_fanqie_project()` 推断）。
改造后，每个 Pack 显式声明：

```python
# styles/fanqie.py（番茄包内）
def _fanqie_power_profile(ctx: dict) -> PowerSystemProfile:
    """根据 genre_archetype 动态返回正确的境界类型。"""
    archetype = (ctx.get("fanqie_positioning") or {}).get("genre_archetype", "")
    needs_cultivation = any(
        k in archetype
        for k in ("修仙", "古武", "系统升级", "末世", "星际")
    )
    if needs_cultivation:
        return PowerSystemProfile(
            system_type="cultivation",
            use_sub_levels=True,
            prompt_builder=build_fanqie_cultivation_prompt,   # 新建：境界名与金手指阶段对齐
            realm_block_builder=build_fanqie_realm_discipline_block,
        )
    else:
        # 都市/赘婿/神豪 → 社会阶梯，禁止「初期/圆满」写法
        return PowerSystemProfile(
            system_type="social",
            use_sub_levels=False,
            prompt_builder=build_fanqie_social_prompt,        # 用 social_ladder 直接生成
            realm_block_builder=None,                         # 写章不注入境界铁律
        )
```

`power_systems` 通用节点改为：

```python
# steps/power_systems/__init__.py
async def gen_power_systems(svc, project, ctx):
    profile = HookRegistry.get_power_profile(ctx)  # 查注册表，得到 PowerSystemProfile
    system, prompt = (
        profile.prompt_builder(ctx)
        if profile.prompt_builder
        else _default_prompt_builder(ctx)           # 通用线回退
    )
    ...
```

---

## 九、迁移路径（不破坏现有功能）

```
阶段 1（新建基础设施，不动已有代码）
  ├── 新建 style_pack.py（StylePack 定义 + HookRegistry）
  ├── 新建 graph_builder.py（_resolve_chain + build_graph）
  └── 新建 styles/__init__.py + styles/general.py（通用 Pack，无 positioning_node）

阶段 2（迁移番茄线）
  ├── 新建 styles/fanqie.py，把 graph_fanqie.py 里的步骤函数迁移进来
  ├── 把 build_fanqie_volumes_block 等移为 PromptHook 注册
  ├── 在 graph.py 的 init_bootstrap_graph 里改用 build_graph([FANQIE_PACK])
  └── graph_fanqie.py 降为空壳（re-export），之后删除

阶段 3（迁移同人线，修复境界体系）
  ├── 新建 styles/fanfic.py
  ├── 修复 PowerSystemProfile 声明（消除 is_fanqie_project() if-else）
  └── 消除 context_assembler.py 里的 is_fanqie_project() 分支

阶段 4（持续扩展）
  └── 新增任何风格：新建 styles/xxx.py，在 STYLE_REGISTRY 加一行
```

---

## 十、新增一种风格的标准工作量

未来增加「校园热血」风格，只需：

```
styles/school_drama.py          ~150 行
  ├── node_school_positioning   校园题材立项节点
  ├── node_campus_design        校园设定设计步骤
  ├── node_rivalry_map          竞争/热血对手地图（类似 face_slap_map）
  └── SCHOOL_DRAMA_PACK         声明以上步骤 + PromptHook（注入校园约束到 volumes/characters）

styles/__init__.py              +1 行注册
bootstrap_graph.py（路由）      +1 行注册 STYLE_REGISTRY["school_drama"]
```

**不需要改动**：`graph.py` / `graph_nodes.py` / `volumes.py` / `characters.py` / 任何共享步骤。

---

## 十一、关键代码规模控制

| 文件 | 预估行数 | 说明 |
|------|---------|------|
| `style_pack.py` | ≤ 150 | dataclass 定义 + HookRegistry |
| `graph_builder.py` | ≤ 200 | 图组装逻辑 |
| `styles/general.py` | ≤ 100 | 通用包（无额外步骤，只有通用 positioning） |
| `styles/fanqie.py` | ≤ 250 | 现有番茄步骤的搬运 + PowerSystemProfile |
| `styles/fanfic.py` | ≤ 200 | 现有同人步骤的搬运 |
| 每个新风格包 | ≤ 200 | 新建步骤函数 + Pack 声明 |

迁移完成后可删除：`graph_fanqie.py`（582行）/ `graph_fanfic.py`（403行），净减少约 1000 行。
