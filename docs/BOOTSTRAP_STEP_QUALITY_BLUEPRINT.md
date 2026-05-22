# Bootstrap 逐步高质量优化蓝图（无 Token 预算版）

> **文档性质**：架构与提示词策略方案，不含代码实现。  
> **前提**：不考虑 token / 成本 / 延迟，只追求「一书一宪法、步步可校验、下游可执行」。  
> **对照基线**：当前通用 LangGraph 拓扑（`graph.py`，2026-05）与番茄专属拓扑（`graph_fanqie.py`）。  
> **读者**：产品、总编辑、后端编排、提示词工程。

---

## 0. 总编辑视角：Bootstrap 到底在解决什么

Bootstrap 不是「填表」，而是为后续 **十年连载级** 写作建立四份不可漂移的锚：

| 锚类型 | 内容 | 违反后果 |
|--------|------|----------|
| **宪法锚** | 立项定位 + PREMISE + 禁忌 | 全书 tone 漂移、平台不适配 |
| **力学锚** | 境界/势力/爽点/节奏的可计算规则 | 战力崩、打脸空、升级无感 |
| **戏剧锚** | 人物债、故事线、反派自驱、卷 phase | 剧情杀、反派工具人、卷尾无力 |
| **契约锚** | 开局承诺、核心谜题、情绪账户 | 前 10 章流失、伏笔断、虐爽失衡 |

**当前系统已做对的事**（应保留并加深，而非推倒）：

- Step 0 立项会议 + 人工闸门（`positioning` / `gate`）
- `genre_kit` 流派手册注入（多步已接入）
- 卷 `phase`、情绪节律图、反派行动线、核心谜题预分配
- Step 14 代码预检 + AI 叙事扫描双阶段
- `vol1_chapters` / `ch1_scenes` 移出 Bootstrap，改写作期按需展开（正确——Bootstrap 应止于「可执行的骨架」，而非抢跑章纲）

**无预算下的总策略**：从「单轮大 prompt → 一次 JSON」升级为 **「多角色、多轮、可证伪」流水线**。

---

## 1. 全局架构升级（适用于所有步骤）

### 1.1 一书一宪法（Book Constitution）

在 Step 0 通过后，由模型生成一份 **800～1500 字的《本书宪法》**（纯文本 + 结构化键），写入 `Project.extra.constitution`，后续每一步 prompt **首部强制引用**，且禁止与本宪法矛盾的输出。

宪法建议包含：

- **不可变承诺**（3～5 条）：例「主角永不圣母洗白」「金手指有可见代价」「第 1 卷不得出现仙帝级」
- **爽点计量表**：小爽/中爽/大爽的章节间隔、载体类型（打脸/升级/揭秘/情感）
- **信息差策略**：读者知道而主角不知道 / 反之 / 同步，各占比例
- **叙事 POV 契约**：主视角、是否允许多 POV、内心戏占比上限
- **命名与文风**：人名风格、禁用词、对话密度
- **结局倾向与收束边界**（与 premise 对齐）

> 价值：避免后续 14 步各自「理解 logline」导致隐性分叉。

### 1.2 标准三步生成模式（Generate → Critique → Repair）

每一步默认拆为 **3 次模型调用**（可用不同 task profile：生成 0.65 / 批评 0.25 / 修复 0.45）：

1. **Generate**：按 schema 产出初稿  
2. **Critique**：换「挑剔总编辑」身份，只输出 `{violations[], severity, fix_hint}`，对照宪法 + 上游锚  
3. **Repair**：只改 violations，输出终稿 JSON  

失败不进入下一步；violations 写入 `BootstrapRun.events` 供前端展示「编辑批注」。

### 1.3 富上下文，弃压缩摘要

无预算时 **禁止** 用 300 字 `settings_summary` 代替全文。改为：

- 每步注入 **上游实体的结构化快照**（完整 JSON 子集，按 relevance 裁剪字段而非砍字数）
- 对卷/章规划注入 **全书实体注册表**（人物 tier、势力 active_period、技能 level_required 等）

已有 `volume_entity_registry` 方向正确，应升级为 **全书 Entity Registry**（Bootstrap 全程维护）。

### 1.4 机器可证伪 + 总编辑可证伪

| 层级 | 手段 |
|------|------|
| L0  schema | Pydantic 校验（已有，加强必填与互斥） |
| L1  图论 | 势力父子无环、关系图连通、境界 rank 单调 |
| L2  计量 | 章节预算之和、phase 序列、情绪连续负余额 |
| L3  AI 批评 | 语义矛盾、人设 OOC、流派禁忌 |
| L4  读者模拟 | 「28 岁目标读者」对开局/卷 hook 打分 <7 则回流 |

### 1.5 拓扑微调建议（质量优先，非必须一次做完）

当前顺序里 **反派卷级行动线（9.8）在卷骨架（9）之后**，卷生成只能吃到势力上的 `villain_timeline` 短句，吃不到完整 `villain_arc`。

**建议**（二选一）：

- **A. 重排**：`factions → storylines → characters → villain_arc（提前）→ volumes`  
- **B. 双 pass 卷**：`volumes_v1`（结构）→ `villain_arc` → `volumes_v2`（仅修订 summary/conflict/phase）

无预算版推荐 **B**：保留并行度，又保证卷级与反派自驱对齐。

### 1.6 闸门从「看结果」升级为「看指标」

三道闸门（境界 / 人物 / 卷）展示：

- **硬指标仪表盘**：境界数、gatekeeper 非空率、角色 tier 分布、debt_to 覆盖率、卷 phase 单调性  
- **总编辑一句话 verdict**：AI 只输出「可签约 / 需修 / 建议重跑」+ 3 条理由  
- 用户仍一键 approve，但决策信息密度接近真实责编审稿单

---

## 2. 逐步优化方案（通用 Bootstrap 拓扑）

以下按 `graph.py` 执行顺序。每步结构：**现状瓶颈 → 优化目标 → 推荐调用设计 → Prompt/Schema 要点 → 下游契约 → 质量闸门**。

---

### Step 0 · 立项会议（`positioning`）

**现状瓶颈**  
单次 JSON；`hook_test` 自评易虚高；tropes 组合约束靠 prompt 自觉；与番茄算法立项未统一抽象。

**优化目标**  
立项 = **商业 + 文学 + 算法** 三重视角的可执行合同，而非标签堆砌。

**推荐调用设计（5 轮）**

1. **市场拆解**：平台（起点/番茄/晋江）、竞品 5 部、同质化风险、差异化钩子  
2. **读者契约**：primary/secondary 读者、弃书触发器、留存杠杆（前 3 章 / 前 30 章 / 卷末）  
3. **爽点工程**：tropes 选 3～5 + **互斥矩阵校验** + 每种 trope 的「最小可感知载体」  
4. **节奏合同**：`face_slap_pattern` 数值化（每 N 章、类型轮换表）  
5. **红线与钩子实测**：`taboo_lines` + 3 版书架文案 A/B/C + **读者模拟器**打 1～10 分（<7 必须回流改文案）

**Prompt/Schema 要点**

- 增加 `trope_evidence`：每个 trope 对应 logline 中的哪句话  
- 增加 `anti_patterns`：本书最像的 3 种扑街写法  
- 增加 `success_metrics`：可观测 KPI（例：第 3 章完读率假设、卷一订阅转化假设）  
- `differentiation_durability` 改为 **分卷表**：第几卷风险最大、预埋什么对冲钩子  

**下游契约**  
全文 `positioning` 原样注入；另生成 **constitution 摘要块**（≤200 字）供轻量步骤使用。

**质量闸门**  
schema 通过后，**总编辑批评轮**专门查 tropes 矛盾、男频/女频错位、卖点是否可复制到封面。

---

### Gate 0 · 立项确认（`gate`）

**优化**  
不只编辑 JSON：提供 **「差异对比视图」**（regenerate 前后 tropes/钩子/红线 diff）+ AI 生成的「若按现稿开写，预计第几章出现同质化风险」。

---

### Step 1 · 项目基础（`project`）

**现状瓶颈**  
`premise` 与 `world_overview` 一次生成，易与世界后续势力/境界重复或冲突；`story_core` 偏抽象。

**优化目标**  
PREMISE = 作者十年可执行的 **创作基线文档**；`world_overview` 只写「舞台规则」，不写具体宗门名（留给 Step 3）。

**推荐调用设计（4 轮）**

1. **PREMISE 长文**：按现有 markdown 结构，但每节有「可检验句」  
2. **World Rules Only**：力量来源、社会结构、禁忌、地理尺度（**禁止具名势力**）  
3. **Story Core 量化**：`conflict` 拆为 `external_goal` / `internal_wound` / `stakes_if_fail`  
4. **Title 候选 10 → 编辑决选 1**：书名需通过「书架扫读测试」（2 秒能懂类型+爽点）

**Prompt 要点**  
- 强制引用完整 `positioning` + constitution  
- `genre` 与 `genre_kit` 自动对齐；若模型输出 genre 不在 kit 库，触发映射或扩展 kit  
- `world_overview` 末尾增加 `open_questions[]`：留给后续步骤回答的世界谜题  

**下游契约**  
`ctx.story_core` 带量化字段；`open_questions` 流入 Step 8 设定卡与 Step 11.5 谜题。

---

### Step 2 · 境界体系（`power_systems`）+ Gate Power

**现状瓶颈**  
一次生成 6+ 境界；`chapter_budget` 与全书章数弱耦合；gatekeeper 易空泛。

**优化目标**  
境界 = **读者爽感节拍器**，不是名词列表。

**推荐调用设计（6 轮）**

1. **体系哲学**：修炼本质、天花板原因、主角为何能破例（与 constitution 对齐）  
2. **境界表 v1**：每境 `rank/name/abilities/chapter_budget/gatekeeper`  
3. **爽点映射**：每境对应 1 种主爽点（打脸/悟道/夺宝/破境仪式）  
4. **计量校验**（代码）：`sum(chapter_budget) ≈ 0.7 * total_chapters`；`protagonist_start/end` 合法  
5. **总编辑批评**：是否存在跳境、无 gatekeeper、与 tropes 不符（如苟道流却境界暴涨）  
6. **Repair 终稿**

**Schema 增强**

- `breakthrough_scene_template`：突破时固定三要素（代价/仪式/围观反应）  
- `power_ceiling_foreshadow`：哪一境开始触及世界天花板  
- 可选第二套 `system_type` 副体系时，要求 `interaction_rules`（两套如何互相制约）

**Gate Power 展示**  
境界阶梯可视化 + 「主角从 rank X 到 Y 的预计章节跨度」+ 批评轮 violations。

---

### Step 3 · 势力（`factions`）

**现状瓶颈**  
4～6 势力一次出齐；`villain_timeline` 与后续 `villain_arc` 可能重复或打架。

**优化目标**  
势力 = **资源与规则博弈方**；反派势力具备 **无主角时的世界线**。

**推荐调用设计（5 轮）**

1. **势力版图**：只出 name/type/alignment/active_period/与主角关系  
2. **势力深度展开**：每势力单独一轮（富上下文），避免数组里互相挤占注意力  
3. **关系矩阵**：`rivals/allies` 双向闭合校验  
4. **反派世界线**：仅 antagonist，`villain_timeline` 按 **卷号** 列出若主角不干预的阴谋链  
5. **批评 + 修复**：检查是否缺主角阵营、是否全员敌对、internal_factions 是否同质化

**Schema 增强**

- `resource_conflicts`：与哪条 storyline 绑定  
- `entry_chapter_window`：势力在叙事上的登场卷区间  
- `collapse_condition`：势力何时解体/转型  

**下游**  
`villain_timelines` 升级为结构化 `[{vol, event, if_interrupted}]`，供卷骨架与 villain_arc 共用。

---

### Step 4 · 故事线（`storylines`）

**现状瓶颈**  
3～5 条线，缺少与卷/章的进度锚点；与 core_mysteries 分工不清。

**优化目标**  
故事线 = **可追踪进度条**；主线必有「中点翻转」与「终局代价」。

**推荐调用设计（4 轮）**

1. **主线设计**：单独一轮，输出 main + `midpoint_reversal` + `climax_cost`  
2. **支线 bundle**：romance/growth/mystery/faction 各 1 条，禁止与主线抢戏  
3. **进度锚点**：每条线 `milestones[{chapter_or_vol, beat, emotional_payoff}]`  
4. **批评**：是否只有 1 条 main、支线是否可删、是否与 positioning.emotional_arc 冲突

**Schema 增强**

- `line_owner_characters[]`  
- `failure_mode`：若该线写崩，读者流失点在哪  
- `intersects_with_mysteries[]`：预留给 Step 11.5 回填

---

### Step 5 · 人物（`characters`）+ Gate Characters

**现状瓶颈**  
13 人一次数组（8 core + 5 plot）；`speech_kit` 长度过长易截断 JSON；第二 part 配角易敷衍。

**优化目标**  
人物 = **债务网络 + 语风指纹 + 戏份经济学**。

**推荐调用设计（分人群多轮）**

| 轮次 | 对象 | 说明 |
|------|------|------|
| C1 | 主角 | 单独一轮，最深：arc_stages、speech_kit 5～8 句、debt、secrets、fear 必须具象 |
| C2 | 核心反派 ×2 | 每反派一轮，强调 **与主角的镜像关系**、vol_result 预设 |
| C3 | 核心配角 ×3 | 每人一轮，绑定 storyline_id |
| C4 | 师长/势力代表 ×2 | 绑定 faction_id |
| C5 | 开局 plot 配角 ×5 | 可合并一轮，但 `vol1_function` 必须精确到章号事件 |
| C6 | 关系预演 | 只输出「尚未入库的隐含关系」供 Step 11 引用 |
| C7 | 批评 | OOC、quota 超标、debt_to 未覆盖、sample_dialogues 违反 forbidden_examples |

**Prompt 要点**

- 每人生成时注入：**完整 power levels、所属势力档案、相关故事线**  
- `speech_kit` 拆为独立子调用（降低主 JSON 截断风险）  
- 强制 `character_tier` 分布：core≤8, arc 2～4, plot 5, background 若干（可按 genre_kit 调整）

**Gate Characters**  
展示 **债务图**（谁欠谁、哪卷引爆）+ **tier 饼图** + 语风样本朗读区（前端 TTS 可选）。

---

### Step 6+7 · 技能 + 道具（`skills_items`）

**现状瓶颈**  
两步合并节点；与境界、人物掌握者、章纲出现时机易脱节。

**优化目标**  
道具/技能 = **情节扳手**，每件绑定「首次兑现章」与「误用后果」。

**推荐调用设计**

1. **技能**：按 storylines 需要生成；每件 `narrative_job`（破局/装逼/伏笔）  
2. **道具**：分 **主线神器 / 卷级消耗品 / 误导性红鲱鱼**  
3. **掌握者绑定**：`mastered_by` 必须 realm_rank 合法（代码预检）  
4. **批评**：是否过多、是否与 constitution「金手指代价」一致

**Schema 增强**

- `first_payoff_chapter` / `misuse_consequence`  
- `foreshadow_link`：对应 core_mystery 代号（可为空）

---

### Step 8 · 世界观设定卡（`settings`）

**现状瓶颈**  
`WorldSetting` 易与 PowerSystem/Faction 重复；纯叙事与结构化边界模糊。

**优化目标**  
只生成 **无专属表的纯叙事**，且每条可检索、可 RAG。

**推荐调用设计（3 轮）**

1. **分类清单**：世界背景/地理/历史/文化/规则 各需要几条  
2. **逐类展开**：每类单独生成 2～4 张卡，带 `canon_level`（immutable/flexible）  
3. **去重扫描**：AI 对比已有 Power/Faction/Character，删除重复，合并引用

**下游**  
`settings_summary` 改为 **结构化索引**（title + 50 字摘要 + tags），非截断正文。

---

### Step 9 · 卷级骨架（`volumes`）+ Gate Volumes

**现状瓶颈**  
单次数组生成 N 卷；`villain_arc` 尚未生成；卷间衔接靠 prompt 自觉。

**优化目标**  
卷 = **独立电影**：有钩子、矛盾、情绪、反派格局、实体出场预算。

**推荐调用设计（无预算推荐）**

**Pass 1 — 结构建筑师**

- 只输出：title, sort_order, planned_chapters, phase, 卷间 `handoff_question`（上卷末留给下卷的问题）

**Pass 2 — 戏剧编剧**（每卷一轮，共 N 轮）

- 输入：Pass1 该卷 + 全书 constitution + storylines + 相关人物小传 + 势力 + 情绪约束（若已有 9.5 可后置，见拓扑 B）  
- 输出：summary, hook, conflict, `key_turning_chapters[]`, `entity_budget`（本卷允许出场的人物/势力 ID 子集）

**Pass 3 — 衔接编辑**

- 专检相邻卷：时间线、境界进度、反派 win/lose 与 phase 一致

**Pass 4 — 实体注册表 lint**（代码 + AI）  
已有 `volume_entity_registry` 思路，扩展为：未注册实体名禁止进入 summary。

**Gate Volumes**  
卷序 timeline + phase 色带 + 每卷 hook 一句话测试（读者模拟 <7 标红）。

**与 9.5/9.8 的顺序**  
采用 **§1.5 双 pass**：Gate Volumes 通过的是 Pass1+2；9.8 后再跑 **volumes_patch** 只改 conflict/phase 不对齐处。

---

### Step 9.5 · 情绪节律图（`emotion_arc`）

**现状瓶颈**  
在卷骨架之后；规则靠 prompt「连续 3 卷 negative」；与 phase 可能脱节。

**优化目标**  
情绪 = **可执行的章节级预算**，而非形容词。

**推荐调用设计（3 轮）**

1. **卷级情绪分配**：现有字段 + `mandatory_cooldown_chapters`（虐后必须给出口的具体章型）  
2. **章型模板映射**：每卷绑定 2～3 个「章节节奏模板」（快打/慢热/揭秘/情感）  
3. **批评**：运行规则 1～5 的代码模拟 + AI 查「假爽」（deposit 写的是打脸但无具体事件）

**Schema 增强**

- `deposit_events[]` / `cost_events[]`：可解析的具体情节  
- 与 `phase` 冲突时，**phase 优先** 或触发 volumes_patch

---

### Step 9.8 · 反派行动线（`villain_arc`）

**现状瓶颈**  
在卷之后生成，无法反哺卷骨架初稿；`vol_goal` 易写成「阻止主角」。

**优化目标**  
反派 = **第二主角**；读者应有一半章节想「反派会赢」。

**推荐调用设计（4 轮）**

1. **反派小传**：欲望、恐惧、道德灰度、与主角镜像点（单独调用）  
2. **卷级行动线**：每卷一轮，严格四元组 goal/obstacle/choice/cost  
3. **hidden_move 审计**：每条 hidden_move 必须对应后续某 core_mystery 或 foreshadow  
4. **批评**：vol_result 与 phase 表强制一致（代码）；dark_hour 必 win，climax 必 lose

**下游**  
触发 `volumes_patch`；更新 `ctx.villain_arc_summary` 供 opening_contract / 章纲展开。

---

### Step 10 · 记忆种子（`memory`）

**现状瓶颈**  
10 条泛化记忆；embedding 价值取决于是否「可检索、不可歧义」。

**优化目标**  
记忆 = **写作时的硬约束检索单元**。

**推荐调用设计（2 轮）**

1. **分类强制 10 条**：境界锚 / 人物状态 / 故事线起点 / 规则法则 / 开放伏笔 — 每类 2 条  
2. **检索问句测试**：每条附 `retrieval_query`（写章时可能问的 natural question），不过测试则重写

**增强**  
生成后立即 `embed_chunk_async`；Bootstrap 末再跑 **检索回放测试**（用 5 个模拟写章 query 查 Top-3 是否命中正确记忆）。

---

### Step 11 · 人物关系（`relations`）

**现状瓶颈**  
依赖 `debt_to` 文本；图不闭合时静默跳过。

**优化目标**  
关系网 = **张力电网**，每条边可驱动一场戏。

**推荐调用设计（3 轮）**

1. **核心团完全图**：core 人物两两关系，禁止孤岛  
2. **张力边增强**：`unresolved_tension` + `trigger_event` + `expected_explosion_vol`  
3. **批评**：与 debt_to 不一致的边标为 violation；缺 protagonist-antagonist 高强度边则失败

**Schema**  
增加 `relation_arc`：陌生→对立→暧昧→决裂 等阶段标记。

---

### Step 11.5 · 核心谜题（`core_mysteries`）

**现状瓶颈**  
5～8 条一次生成；lay/heat/reveal 章号易与卷骨架漂移。

**优化目标**  
谜题 = **全书钢筋**；与 storylines、villain hidden_move 显式挂钩。

**推荐调用设计（5 轮）**

1. **谜题候选 12 条** → 总编辑砍到 6～8 条（保留 identity 至少 1）  
2. **每条谜题单独展开** lay/heat/reveal 手法（富上下文）  
3. **时间轴对齐**：章号映射到 `vol_index + chapter_in_vol`，与 `chapter_quota_total` 校验  
4. **Foreshadow 写入** + `dependency_graph`（谜题 A 揭晓依赖 B 已加热）  
5. **批评**：前 20 章无埋设、90% 后揭晓、与 taboo_lines 冲突

**下游**  
`ctx.core_mysteries_summary` + 写作期章纲必须引用 `mystery_id`。

---

### Step 12 · 开局追读承诺（`opening_contract`）

**现状瓶颈**  
偏前 10 章；与 `ReaderPromise` 种子的映射已有，但缺 **可测场景**。

**优化目标**  
开局 = **签约级交付合同**，编辑可逐章验收。

**推荐调用设计（4 轮）**

1. **第 1 章分场级承诺**：前 200 字三要素必须落到「地点+动作+信息」  
2. **第 1～10 章节奏表**：每章 `hook_type` + `payoff_type` + `emotion_delta`  
3. **陷阱清单**：针对本书 tropes 的 5 个具体扑街场景（非泛泛「节奏慢」）  
4. **读者模拟双评委**：男/女各一名，对 ch1/ch3/ch10 打追读分 + 一句毒舌

**ReaderPromise 种子**  
每条 promise 增加 `acceptance_criteria`（怎样算兑现，供 debrief 层③）。

---

### Step 14 · 一致性扫描（`consistency`）

**现状瓶颈**  
Bootstrap 末无 chapter_plan 时部分预检空转；AI 扫描偏摘要输入。

**优化目标**  
Bootstrap 一致性 = **骨架级全球体检**，为写作期铺路。

**推荐调用设计**

**阶段 0 — 全表代码审计（扩展）**

- 势力 active_period vs 卷 phase  
- 人物 arc_stages 与境界 rank 单调  
- 技能/道具 first_payoff 是否在总章数内  
- storylines milestones 是否落在合法卷/章  
- core_mysteries 依赖图无环  
- emotion_arc 连续 negative 规则  
- entity_registry 孤儿检测  

**阶段 1 — 跨实体 AI 叙事扫描（分专题）**

| 专题 | 检查内容 |
|------|----------|
| T1 时间线 | 卷间 handoff、反派 timeline、境界预算 |
| T2 动机链 | 反派 goal 非阻止主角、人物 motivation 与关系张力 |
| T3 爽点合同 | positioning vs 卷 phase vs emotion deposit |
| T4 伏笔网 | mysteries vs foreshadow vs opening_contract |
| T5 流派禁忌 | genre_kit forbidden_examples 全文扫描 |

**阶段 2 — 修复建议包**  
输出 `{issue_id, auto_fixable, fix_step}`；`auto_fixable=true` 的可触发 **定向重跑**（只 regen 某 step，非全量 Bootstrap）。

**持久化**  
`Project.extra.consistency_issues` + `consistency_score` + `blocking_issues[]`（有则 Bootstrap 标 `completed_with_warnings` 而非静默成功）。

---

## 3. 写作期按需步骤（已移出 Bootstrap，质量仍须拉高）

`vol1_chapter_plans` / `vol_chapter_plans` / `ch1_scenes` 不在 Bootstrap 图内，但是 **质量闭环的延伸**。无预算下建议：

### Step 12.5 · 第一卷章纲（`vol1_chapter_plans`）

- **按章生成**：每章 1 调用，注入卷 summary + emotion 该卷条 + 相关 mystery heat 点 + involved 人物小传  
- **章末钩子类型轮换**：对照 `chapter_hook_spectrum`，禁止连续 3 章同类型  
- **Linter 前置**：生成后立即跑 CH/SEQ/VL/OC/RP/CM；fail 则 Repair 轮，不写入 DB  
- **POV/戏份**：每章 `pov_character_id` + `screen_time_budget` 与 genre_kit 对齐  

### Step 13 · 第 1 章场景（`ch1_scenes`）

- 先 **场景节拍表**（goal/conflict/turn/hook）再扩写蓝图  
- 对照 `opening_contract.first_200_words_test` 做 **场景 0 专项**  
- `hook_strength` 1～5 低于 4 则回流  

---

## 4. 番茄专属 Bootstrap（`graph_fanqie.py`）增量优化

番茄拓扑已按算法逻辑拆细（落差/金手指/打脸地图/权力阶梯/开局五章/节奏图/信号审计）。无预算下每层再加：

| 阶段 | 增量 |
|------|------|
| A 算法立项 | 增加 `ctr_hypothesis`、`retention_curve_target`、`competitor_diff_3axis` |
| B 落差工程 | 分「读者视角落差」与「主角视角落差」双层，防止开篇信息过多 |
| C 金手指 | 可视化规则 + **代价场景库** 3 个（必须写进 ch1～3） |
| D 打脸地图 | 每次打脸绑 `face_slap_type` + `enemy_arc_cost` + 禁止重复对象 |
| E 权力阶梯 | 与通用 power_systems 对齐字段，避免两套力学 |
| F 开局五章 | 每章独立 3 轮（节拍→钩子→算法审计） |
| G 节奏图 | 与 emotion_arc 统一模型，避免两套情绪语言 |
| H 信号审计 | 拆「算法编辑」与「人类总编辑」双评委；任一侧 <7 则回流 F/G |

**终局**：番茄流也应产出 **constitution + entity_registry**，与通用流在写作期汇合，而非两套平行数据。

---

## 5. 采样与模型分工（仍不考虑成本时的理想配置）

| 角色 | temperature | 用途 |
|------|-------------|------|
| 建筑师 | 0.55～0.65 | 结构化骨架（卷、境界、势力） |
| 编剧 | 0.70～0.80 | 人物、故事线、反派、开局承诺 |
| 批评家 | 0.20～0.30 | Critique / consistency / signal_audit |
| 修复师 | 0.40～0.50 | Repair 轮 |
| 读者模拟 | 0.85 + 约束 JSON | hook_test / opening 打分 |

可选用 **不同模型**：批评/审计用小模型即可；编剧/建筑师用大 context 模型。同一 step 内 **生成与批评必须异 system prompt、异角色名**。

---

## 6. 实施优先级（若分阶段落地）

不考虑 token 时，建议按 **杠杆** 排序：

1. **P0** — 全书 constitution + Generate/Critique/Repair 三板斧（所有 step 复用）  
2. **P0** — 卷双 pass + villain_arc 后 volumes_patch（修复拓扑质量债）  
3. **P1** — 人物分人群多轮 + speech_kit 子调用  
4. **P1** — core_mysteries 逐条展开 + 时间轴对齐  
5. **P1** — consistency 扩展代码审计 + 分专题 AI  
6. **P2** — 闸门指标化 + 读者模拟嵌入 Step0/12/卷 gate  
7. **P2** — 记忆检索回放测试 + opening acceptance_criteria  
8. **P3** — 番茄各阶段三轮细化 + 与通用 registry 汇合  

---

## 7. 成功标准（什么叫「每一步高质量」）

Bootstrap 完成时，应满足：

- [ ] 存在可通过机器校验的 **Book Constitution**，且 14 步无 violation 残留  
- [ ] 任意卷 summary 可回答：本卷 hook、反派 vol_result、情绪 net、主推进 storylines、mystery heat 点  
- [ ] 任意核心人物可回答：债、惧、秘密、语风 3 句示范、至少 2 个 arc_stage  
- [ ] `consistency_score ≥ 85` 且无 `severity=high` 未处理项  
- [ ] 开局合同每条带 `acceptance_criteria`，且读者模拟 ch1/ch10 ≥ 7  
- [ ] 写作期展开 vol1 章纲时，linter 首次通过率 ≥ 80%（说明 Bootstrap 骨架足够细）  

---

## 8. 与现有代码的映射（便于落地时检索）

| 步骤 | 模块 |
|------|------|
| 0 | `steps/positioning.py` |
| 1 | `steps/project.py` |
| 2 | `steps/power_systems.py` |
| 3 | `steps/factions.py` |
| 4 | `steps/storylines.py` |
| 5 | `steps/characters.py` |
| 6-7 | `graph_nodes.node_skills_items` |
| 8 | `steps/settings.py` |
| 9 | `steps/volumes.py` + `volume_entity_registry.py` |
| 9.5 | `steps/emotion_arc.py` |
| 9.8 | `steps/villain_arc.py` |
| 10-11 | `steps/memory.py` / `steps/relations.py` |
| 11.5 | `steps/core_mysteries.py` |
| 12 | `steps/opening_contract.py` |
| 14 | `steps/consistency_scan.py` |
| 编排 | `graph.py` / `graph_nodes.py` / `graph_gates.py` |
| 番茄 | `graph_fanqie.py` + `steps/fanqie/*` |
| 流派 | `services/genre_kit.py` |
| 写作期章纲 | `steps/vol1_chapter_plans.py` / `vol_chapter_plans.py` |
| 写作期场景 | `steps/ch1_scenes.py` |

---

*文档版本：2026-05-22 · 对照仓库 Bootstrap 拓扑与步骤实现整理。*
