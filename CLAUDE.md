# Novel System — 项目记忆 (CLAUDE.md)

> 这个文件是给 AI 助手（Claude）读的上下文锚点。  
> 每次重要决策、架构变更、未完成事项都记录在这里，避免重复推导。

---

## 项目概述

**目标**：一个以 AI 生成为核心的网络小说创作系统。人工不负责填写设定，所有世界观、势力、境界、人物、大纲均由 AI 从一句话创意全量生成。  
**核心特性**：输入一句话创意，AI 全量生成结构化设定（境界体系、势力档案、故事线、人物、技能、道具）并存入对应数据表；后续章节写作、质检、记忆管理也全部由 AI 驱动，人工只做审阅和微调。

> ⚠️ **设计原则**：系统是 AI 生成系统，不是辅助填写工具。所有新功能的出发点是"AI 能生成/校验/推进什么"，而非"给用户提供什么表单"。

> ⚠️ **持久化优先（硬规则）**：所有业务内容（状态、产物、流程中间结果、AI 结构化输出）默认必须做数据库持久化（PostgreSQL）；禁止仅停留在前端内存或进程内变量。仅当有明确性能/安全原因且已文档化时允许例外。

**技术栈**：
- 后端：FastAPI + SQLAlchemy + PostgreSQL（含 pgvector）
- 创作端（client）：React + TypeScript + Vite + TailwindCSS + Zustand + TipTap
- 管理后台（frontend）：React + TypeScript + Vite（与 API 同域代理 `/api`）
- AI：统一走 OpenAI 兼容协议（`AsyncOpenAI(base_url=..., api_key=...)`）

---

## 仓库结构（monorepo）

根目录下 **`apps/`** 三个子项目，勿与旧路径 `backend/`、`frontend/`（根级）混淆：

| 路径 | 说明 |
|------|------|
| `pnpm-workspace.yaml` + 根 `package.json` | pnpm 工作区，统一安装/脚本（如 `pnpm dev:admin`） |
| `.github/workflows/js-apps.yml` | CI：创作端 + 管理后台 `pnpm build` |
| `apps/backend/` | FastAPI；环境变量读 `apps/backend/.env`（由 `.env.example` 复制） |
| `apps/client/` | 小说创作 SPA（原「前端」主产品） |
| `apps/frontend/` | 管理后台 SPA（占位壳，端口默认 3174） |

本地一键：`./restart.sh` 启后端 + **client**；管理后台需另开终端 `cd apps/frontend && npm run dev`。Docker：`docker-compose.yml` 中服务名为 `backend`、`client`、`frontend`（对应上表）。

---

## AI 模型策略

### 当前模型（创作端用户选择）

| 前端「模型 / 线路」 | 模型与连接来源 |
|---------------------|----------------|
| 远程 · 某条提供者 | 管理后台 `llm_providers` 表（`base_url` / `model_name` / `api_key`），请求带 `llm_provider_id` |
| 远程 · 环境变量（无 DB 行） | `GEMINI_BASE_URL` + `GEMINI_MODEL`（兼容旧部署） |
| 本地 | 仅 `apps/backend/.env` 的 `LLM_BASE_URL` + `LLM_API_KEY` + **`AI_MODEL`（必填）** |

> **当前部署策略：仅使用远程线路，不配置本地线路。**

### 关键决策：统一用 OpenAI 兼容协议

不绑定任何 SDK；远程改管理后台或 `.env` 的 `GEMINI_*`；本地改 `.env` 的 `LLM_*` + `AI_MODEL`。

### Embedding 配置（pgvector 语义检索）

当前使用 **BAAI/bge-m3（1024 维）**，通过 SiliconFlow 等远程服务托管：

```env
EMBEDDING_BASE_URL=https://api.siliconflow.cn/v1
EMBEDDING_API_KEY=你的_key
EMBEDDING_MODEL=BAAI/bge-m3
EMBEDDING_DIM=1024
```

- embedding 列维度由 migration `b3c4d5e6f7a8`（768→1024）完成升级
- 新记忆复盘后自动触发 embedding；存量补跑：`python verify_pgvector.py --reembed`
- pgvector 不可用 / embedding 服务不通时，自动降级为 `importance_score DESC + chapter_number DESC` 时序兜底（`status=fallback_recency`）；可查 `rag_retrieval_log` 表 `status` 字段确认是否在走真实语义检索

### Gemini 迁移时的变化

- Gemini 支持 100 万 token context，可切换到**方案 B（单次全量生成）**
- `bootstrap/service.py` 里 `mode="single_shot"` 已预留，切换只需改前端请求参数

### 任务级采样配置（v3，2026-05）

> 设计动机：质检（要稳定 JSON）和写正文（要文采变化）必须用不同温度，否则是 AI 味的系统性根因。

- 配置文件：`apps/backend/app/services/llm_task_profiles.py`
- 调用方约定：每次 `_call_ai` / `_stream_ai` 传 `task="<域>.<动作>"`（如 `quality.check`、`draft.opening`）；未识别走网关默认。

| 任务域 | temperature | 说明 |
|---|---|---|
| `quality.*` / `debrief.*` | 0.2-0.3 | 稳定 JSON 与可比较打分 |
| `bootstrap.*` / `outline.*` | 0.55-0.75 | 半结构化生成 |
| `draft.chapter` | 0.9 | 章节正文，加 frequency/presence_penalty 抑制重复 |
| `draft.opening` / `draft.climax` | 0.95 | 开局期 / 高潮期允许更跳脱 |
| `draft.dark_hour` | 0.75 | 至暗期需克制 |

- 自定义覆写：调用方传 `sampling={"temperature": 0.85}` 临时覆盖（A/B 测试用）。
- 阶段→任务名映射：`phase_to_draft_task(phase)` 在 `draft_assist_stream` 内部按 `OutlineNode.phase` 自动选档。

---

## 数据模型速查

```
Project
  ├── WorldSetting（设定卡，有 category）
  ├── Character + CharacterRelationship（人物 + 关系）
  ├── OutlineNode（树形：volume → arc → chapter_plan）
  ├── Chapter + ChapterVersion
  ├── MemoryChunk（长篇记忆，embedding 列已启用，走 pgvector 语义检索）
  ├── StoryLine（故事线：主线/支线/感情线/成长线/势力线...）
  ├── PowerSystem（境界/力量体系，含结构化 levels 数组）
  ├── Skill（功法/技能，关联 PowerSystem，记录掌握者）
  ├── Item（道具/法宝，含稀有度、持有历史）
  ├── Faction（势力/宗门/国家，支持父子层级）
  ├── Foreshadow（伏笔台账）
  ├── QualityDebt（质检欠债记录）
  ├── Scene（章节分场，三层调度核心；`scenes` CRUD + `ai/scene_routes` 三层写作 API）
  ├── ReaderPromise（读者承诺台账；模型 + router 已就位，写章/复盘深度闭环待完善）
  └── RagRetrievalLog（每次 RAG 检索落库，含命中条目、status、duration_ms）
```

所有 UUID 主键，`project_id` 外键贯穿所有表。

### Character 增强字段（v2）
新增：`alias`别名、`appearance`外貌、`clothing_style`服装、`current_realm`当前境界、
`realm_rank`境界数字排序、`speech_style`说话风格、`values`价值观、`secrets`秘密、
`trauma`心理创伤、`fear`恐惧、`arc_stages`结构化成长阶段、`known_skills`/`owned_items`
快速引用、`current_status`当前状态（alive/dead...）、`current_location`位置、
`author_notes`作者备注、`faction_id`/`faction_rank`关联势力表。

### OutlineNode 增强字段（v2）
新增：`storyline_ids`关联故事线、`involved_character_ids`出场人物、`key_item_ids`关键道具、
`key_skill_ids`关键技能、`emotional_tone`情感基调、`pacing`节奏标记、
`power_milestone`实力里程碑、`foreshadows_laid`/`foreshadows_resolved`伏笔管理。

### OutlineNode.phase（v3，2026-05）
卷阶段标记，章节起草 prompt 按此切模板与采样档位：

| 取值 | 含义 | 节奏要求 |
|---|---|---|
| `opening` | 开局期 / 新手村 | 钩子密度高、爽点 3 章一次、字数偏短（~2200） |
| `rising` | 起飞期 / 扩张期 | 势力扩张、感情线接入 |
| `turning` | 转折期 | 矛盾升级、代价兑现 |
| `dark_hour` | 至暗期 | 允许「虐」、节奏放缓、字数 ~2800 |
| `climax` | 高潮期 | 伏笔回收、爆点拉满、字数 3000-3300 |
| `ending` | 收束期 | 留下一卷悬念种子 |

由 Bootstrap Step 9 (`_gen_volumes`) 在卷级填入，写章节时回溯卷阶段。

### Scene 模型（v3，2026-05）

章节分场，三层调度（章纲 → 分场 → 逐场正文）的核心数据单元。
- 关联：`Project` / `Chapter`（写完后绑定）/ `OutlineNode`
- 关键字段：`order`、`pov_character_id`、`characters_on_stage`、`goal`、`conflict`、`turn`、`hook`、`hook_strength`、`word_budget`、`pacing`、`sensory_focus`、`status`（planned/written/reviewed）、`content`
- `location_id`（ForeignKey `locations.id`）已**注释预留**，待 Location 模型实现后启用；当前用 `location_name` 文本字段
- **当前状态**：模型 + migration + `routers/scenes.py` + `routers/ai/scene_routes.py`（plan-save / draft/stream / stitch）；创作端 `ScenePipelinePanel`（ChapterEditor「分场」Tab）。整章 `gated-draft` 仍为备选写作路径。

### ReaderPromise 模型（v3，2026-05）

读者承诺台账，记录章末/卷末预告、名字暗示、章评共识等对读者的显式或隐式承诺。
- 关键字段：`promise_type`（chapter_ending / volume_ending / name_implication / ...）、`expected_chapter_window`、`status`（open / fulfilled / broken）、`priority`（1-5）、`audience_aware`（0-5）
- 写章时 prompt 注入"本章必须/可以兑现的承诺"；复盘自动检测新承诺并标记回收
- **当前状态**：模型 + migration + router 已就位；写章注入 open 承诺 + auto-debrief 自动回收的**深度闭环**见「待完成功能」

### Project.extra（v3，2026-05）
JSON 杂物字段，当前已知键：
- `extra.positioning`：Step 0 立项会议产物（`target_audience` / `tropes` / `reference_works` / `selling_point` / `face_slap_pattern` / `emotional_arc` / `pace_type` / `taboo_lines`）。写章节路径优先读 `Project.extra.positioning`，回退 `Project.story_core.positioning`。
- `extra.emotion_arc`：Step 9.5 产物，每卷情绪收支（存入/消耗/净余额/主色调）
- `extra.villain_arc`：Step 9.8 产物，主要反派卷级行动计划
- `extra.core_mysteries`：Step 11.5 产物，跨卷核心谜题预分配
- `extra.opening_contract`：Step 12 产物，开局追读承诺清单
- `extra.consistency_issues`：Step 14 产物，一致性矛盾列表

---

## API 路由约定

| 前缀 | 说明 |
|------|------|
| `GET/POST /api/v1/projects/` | 项目 CRUD |
| `/api/v1/projects/{pid}/settings/` | 世界观设定 |
| `/api/v1/projects/{pid}/characters/` | 人物 |
| `/api/v1/projects/{pid}/outline/` | 大纲树 |
| `/api/v1/projects/{pid}/chapters/` | 章节 |
| `/api/v1/projects/{pid}/ai/` | 质检/建议/记忆提取/写章/复盘 |
| `/api/v1/projects/{pid}/storylines/` | 故事线 CRUD |
| `/api/v1/projects/{pid}/power-systems/` | 境界体系 CRUD |
| `/api/v1/projects/{pid}/skills/` | 功法技能 CRUD |
| `/api/v1/projects/{pid}/items/` | 道具法宝 CRUD |
| `/api/v1/projects/{pid}/factions/` | 势力组织 CRUD |
| `/api/v1/projects/{pid}/scenes/` | 分场 CRUD |
| `/api/v1/projects/{pid}/reader-promises/` | 读者承诺 CRUD |
| `POST /api/v1/bootstrap/stream` | **一句话→全量生成（SSE）** |

---

## 一句话生成（Bootstrap）双方案

### 方案 A：串行步进（Sequential）— 默认

实际执行拓扑（graph.py 定义，非简单串行）：

```
logline
  → [Step 0  立项会议]       positioning        _gen_positioning
  → [Step 1  项目]           project            _gen_project
  → [Step 2  境界体系]       power_systems      _gen_power_systems
  → [Step 3  势力]           factions           _gen_factions
  → [Step 4  故事线]         storylines         _gen_storylines
  → [Step 5  人物]           characters         _gen_characters
  → [Step 6  技能]           skills             _gen_key_skills
  → [Step 7  道具]           items              _gen_key_items
  → [Step 8  设定卡]         settings           _gen_settings
  → [Step 9  卷骨架+phase]   volumes            _gen_volumes
  → [gate_vol 卷质量门控]
  → [Step 9.5 情绪节律图]   emotion_arc        _gen_emotion_arc
  → [Step 9.8 反派行动线]   villain_arc        _gen_villain_arc
  → [Step 10 记忆]           memory             _gen_memory
  → [Step 11 关系]           relations          _gen_relations
  → [Step 11.5 核心谜题]    core_mysteries     _gen_core_mysteries
  → [Step 12 开局承诺]       opening_contract   _gen_opening_contract
  → [Step 12.5 第一卷章纲]  vol1_chapters      _gen_vol1_chapter_plans
  → [Step 13 第1章场景]      ch1_scenes         _gen_ch1_scenes
  → [Step 14 一致性扫描]     consistency        _gen_consistency_scan
```

- 每步独立 prompt，上下文逐步累积（压缩摘要 + 立项定位传入）
- 单步失败重试 1 次，不影响其他步骤
- SSE 每步推送 `step_start` / `step_done` / `error` / `linter_blocked`
- **Step 0 立项会议**：从一句话推导目标读者画像、爽点类型、打脸频率、情感线占比、节奏类型，作为后续各步的全局约束。这是网文系统区别于"AI 自由发挥"的关键防线。
- **Step 12.5 + Step 13**：设定落成可执行写作计划，先生成第一卷章节级 `chapter_plan`，再生成第1章场景级 `Scene` 蓝图。
- **Step 14**：交叉核验所有生成物，矛盾列表写入 `Project.extra.consistency_issues`。

### 方案 B：单次全量（Single-shot）— 适合大 context 模型

```
logline → 1次 AI 调用 → 完整 JSON（含项目+设定+人物+大纲+记忆）
```

- 速度快，前后一致性最佳；要求模型 context ≥ 32k，输出 token ≥ 4096

### 切换方式

```json
{ "logline": "...", "mode": "sequential" }
{ "logline": "...", "mode": "single_shot" }
```

---

## 前端状态管理约定

创作端全局用 **Zustand**（`apps/client/src/store/index.ts`），规则：
- 列表数据（`chapters[]`、`characters[]`等）存 store
- 组件内临时 UI 状态（loading、modal open）用 `useState`
- API 调用后用 `upsert*` 系列方法更新 store，不要重新 fetch 整个列表

---

## 设定生成架构原则

**本系统核心是 AI 生成，不是人工填写。** 所有设定在 Bootstrap 时由 AI 生成结构化数据，直接写入对应表：

| 设定类型 | 存储位置 | Bootstrap 步骤 |
|---|---|---|
| **题材定位** | `Project.extra.positioning` | Step 0 `_gen_positioning` |
| 境界体系 | `PowerSystem` + `levels[]` | Step 2 `_gen_power_systems` |
| 势力组织 | `Faction`（含 `extra.active_period`） | Step 3 `_gen_factions` |
| 故事线 | `StoryLine` | Step 4 `_gen_storylines` |
| 人物 | `Character` | Step 5 `_gen_characters` |
| 核心技能/功法 | `Skill` | Step 6 `_gen_key_skills` |
| 关键道具/法宝 | `Item` | Step 7 `_gen_key_items` |
| 纯叙事设定 | `WorldSetting`（分类存 `extra.category`） | Step 8 `_gen_settings` |
| 卷级大纲 + phase | `OutlineNode`（volume） + `phase` | Step 9 `_gen_volumes` |
| 情绪节律图 | `Project.extra.emotion_arc` | Step 9.5 `_gen_emotion_arc` |
| 反派行动线 | `Project.extra.villain_arc` | Step 9.8 `_gen_villain_arc` |
| 记忆种子 | `MemoryChunk` | Step 10 `_gen_memory` |
| 人物关系 | `CharacterRelationship` | Step 11 `_gen_relations` |
| 核心谜题 | `Foreshadow` + `Project.extra.core_mysteries` | Step 11.5 `_gen_core_mysteries` |
| 开局追读承诺 | `Project.extra.opening_contract` + `ReaderPromise` | Step 12 `_gen_opening_contract` |
| 第一卷章节蓝图 | `OutlineNode`（chapter_plan） | Step 12.5 `_gen_vol1_chapter_plans` |
| 第1章场景蓝图 | `Scene` | Step 13 `_gen_ch1_scenes` |
| 一致性矛盾列表 | `Project.extra.consistency_issues` | Step 14 `_gen_consistency_scan` |

`WorldSetting` 只存**无专属结构化表的纯叙事内容**：作品立意、世界底层规则、历史谜团、地理格局、文化风俗。不再用文字卡存境界体系或势力描述。

---

## 已完成功能

- [x] 项目 CRUD
- [x] 世界观设定 CRUD（分类体系：世界背景/地理场景/历史传说/文化风俗/规则法则）
- [x] 人物 + 关系 CRUD
- [x] 大纲树（层级编辑）
- [x] 章节写作（TipTap + 自动保存 + 版本快照）
- [x] AI 质检（JSON 评分报告，含故事线进度 + 境界体系一致性检查）
- [x] AI 流式建议（SSE）
- [x] 记忆提取 + **pgvector 语义检索**（embedding_service.py 完整实现；BAAI/bge-m3 1024维；复盘后自动触发 embed_chunk_async；写章路径：语义 Top-K + 时效衰减 + 最近 6 条时序锚定）
- [x] 一句话生成（方案A串行 + 方案B单次）
- [x] 故事线/境界体系/技能/道具/势力前端 UI（WorldBuildingPage 五标签页）
- [x] Bootstrap 全量步骤（Step 0-14，含 9.5 情绪节律图 / 9.8 反派行动线 / 11.5 核心谜题）
- [x] 伏笔台账双向关联（`foreshadow_sync.py`，幂等写入）
- [x] 大纲生成防漂移（字数预算约束 + 卷间衔接强制承接）
- [x] 章纲 linter v1.2（CH/SEQ/VL/OC/RP/CM；GEN-02 阻断；`VolumeLinterPanel`）
- [x] Scene 三层调度全链路（plan-save / draft/stream / stitch）+ 前端 `ScenePipelinePanel`
- [x] 势力境界进阶关系图（React Flow，FactionRealmFlow）
- [x] 任务级采样配置（`llm_task_profiles.py`）
- [x] Bootstrap 流派分流增强（`_get_genre_kit_block`；speech_kit；POV + 戏份预算）
- [x] ReaderPromise 写章注入 + 读者模拟反馈闭环（基础链路）
- [x] RagRetrievalLog 落库（每次检索可查 source / status / hits）

## 待完成功能

- [x] **ReaderPromise 深度闭环**（2026-05-21，三层兑现机制已落地）：
  - `services/ai/promise_debrief.py`（新建）：`enrich_with_promise_ids` / `apply_fulfilled_by_ids` / `apply_plan_promise_fulfillment`
  - `auto_debrief` 服务端将 `fulfilled_promise_texts` 解析为精确 ID 列表写入缓存（层①）
  - `chapter_debrief` 按 `fulfilled_promise_ids` 直接按主键标记已兑现（层②）
  - `chapter_debrief` 读取 `OutlineNode.extra.promise_fulfilled` 对 open 承诺做模糊匹配兜底（层③，连通 Bootstrap Step 12.5 规划信号）
  - 剩余：队列自动复盘同步提交（`apply_source=queue_auto` 尚未完整触发 auto-debrief → chapter-debrief 链路）
- [ ] **Location 模型**（当前 Scene.location_name 文本字段，location_id 已注释预留）
- [ ] **人物关系图可视化**（ReactFlow）
- [ ] **导出 TXT / EPUB**
- [ ] **登录鉴权**（目前无 auth）
- [ ] **读者模拟器与主写章流程打通**（低分项自动转 next_chapter_directives）
- [ ] **伏笔台账升级**：type / min_max_distance / paid_off_quality / volume_budget + audit 接口

---

## 代码结构红线（架构级硬约束）

> 设计动机：本仓库已出现「上帝文件」，它们不是被一次写出来的，而是**没有显式上限**导致的路径依赖膨胀。本节给出硬性红线——触线时**必须先拆分再加新功能**，禁止「再加一段就好」式增量恶化。

### 规模上限（硬指标）

| 对象 | 软警戒线 | 硬上限（PR 不予合入） |
|------|---------:|----------------------:|
| 单文件 LOC（含注释；`.py` / `.ts` / `.tsx`） | 400 | **600** |
| 单函数 / 单 React 组件 LOC | 80 | **150** |
| 单类公共方法数 | 10 | **15** |
| 单文件 `useState` / `useEffect` 总数（前端） | 20 | **40** |
| 单 Prompt 字符串字面量行数 | 30 | **60**（超出抽到 `prompts/*.py`） |

**触线处置**：超软警戒线必须在 PR 描述里说明计划；**超硬上限**的文件，PR 必须**同步包含拆分提交**（「治旧」与「加新」同一 PR），否则评审一律退回。例外只允许两类：自动生成代码（schema、migration）、第三方供应文件。

### 反 God-Object 原则

- **Service 类按业务能力切包**。新 AI 能力走 `services/ai/<capability>.py` 的 mixin / 自由函数路径；禁止往 `AIService` 直接堆方法。
- **路由文件按资源动词切包**。新端点放 `routers/outline/routes_*.py` 子模块，禁止往 `helpers_core.py` 新增。
- **React 组件 ≤ 400 行**；超过 1500 行的 `*Page.tsx` 必须先拆 `hooks/` + 子组件再迭代。

### 编排薄壳模式（Orchestration Shell）

对**多步骤流程类**（Bootstrap、章节起草、复盘、读者模拟），强制采用「**编排薄壳 + 步骤独立模块 + Prompt/Parse/Save 分层**」：

- **薄壳层**：`service.py` 只负责 SSE 事件循环、步骤分发、整体 try/except。不写业务 prompt、不写 DB 落库。
- **步骤层**：每个步骤一个文件（如 `steps/positioning.py`），导出 `async def gen_xxx(ai, db, project, ctx) -> ...`。文件内拆 `_build_prompt` / `_persist` 两个私有函数。
- **Prompt 层**：长 prompt（≥ 30 行字面量）抽到 `prompts/*.py`；带 ctx 插值的用 f-string 函数封装。
- **Parse 层**：JSON 解析统一走 `parse.py`（`_parse_json` / `_coerce_*` / `_safe_int`），禁止在 step 文件内现写 try/except。

新增步骤 = 新增一个 step 文件 + 薄壳里加一段 yield，**结构上不可能让薄壳回到 3000 行**。

---

## 上帝文件登记册（治理基线，2026-05-21 更新）

| 文件 | 实测行数 | 状态 |
|---|---:|---|
| `apps/client/src/components/Writing/ChapterEditor/index.tsx` | 2146 | 🚫 严重违规（≥3x 硬上限）；冻结新增 props/`useState`；新功能走 `hooks/` 子 hook；JSX 待拆 TopToolBar/WarnPanel/ContextSidePanel |
| ~~`apps/client/src/pages/OutlinePage.tsx`~~ | — | ✅ 已迁 `pages/Outline/`（2 行 re-export；子模块均 <600） |
| `apps/backend/app/routers/outline/helpers_core.py` | 180 | ✅ 已大幅瘦身；新路由仍进 `routers/outline/routes_*.py` |
| ~~`apps/client/src/components/Layout/GenerationQueuePanel.tsx`~~ | ~~1890~~ | ✅ 已拆至 `Layout/GenerationQueue/`（壳 2 行；最大 runner 297 行） |
| `apps/frontend/src/pages/ReadingReviewPage.tsx` | 1538 | ⚠️ 超硬上限；待拆 ReviewList / SnapshotDiff / useReviewSubmit |
| ~~`apps/client/src/pages/WorldBuildingPage.tsx`~~ | ~~1547~~ | ✅ 已拆至 `pages/WorldBuilding/`（壳 2 行；最大 Tab 321 行） |
| ~~`apps/client/src/pages/CharactersPage.tsx`~~ | ~~1280~~ | ✅ 已拆至 `pages/Characters/`（壳 2 行；最大 CharacterEditor 551 行） |
| `apps/backend/app/routers/outline/qa_internal.py` | 878 | 🚫 超硬上限（600）；新逻辑放 `routers/outline/routes_*.py`，禁止在此文件新增 |
| `apps/backend/app/services/ai/context_builder.py` | 794 | 🚫 超硬上限；新功能禁止增入；待按职责拆分子模块 |
| `apps/backend/app/services/ai/outline_ai.py` | 735 | 🚫 超硬上限；新功能禁止增入；待拆分 |
| `apps/backend/app/services/ai/debrief.py` | 638 | 🚫 超硬上限；新功能禁止增入；待拆分 |
| `apps/backend/app/routers/ai/debrief_routes.py` | 864 | 🚫 超硬上限；新功能禁止增入；待拆分为 chapter_debrief_route.py + auto_debrief_route.py |
| `apps/backend/app/services/bootstrap/context_vol_expand.py` | 634 | 🚫 超硬上限；新功能禁止增入；待拆分 |
| ~~`apps/client/src/components/Writing/ChapterEditor/DebriefPanel.tsx`~~ | ~~707~~ | ✅ 已拆至 `DebriefPanel/`（壳 2 行；编排 index 282 行） |

> 任何一次让上表文件**增加 ≥ 50 行**的 PR 都必须同时包含等量或更多的「治旧」删除量；否则视为破坏红线。

### 已退役（拆分完成）

| 旧上帝文件 | 拆分去向 |
|---|---|
| `apps/backend/app/routers/outline.py`（3825行） | `routers/outline/`（routes_tree / routes_ai_expand / routes_quality / routes_full_generate / routes_workflow_ws / helpers_core / qa_internal / schemas）；原文件已删除 |
| `apps/backend/app/services/generation_service.py`（3149行） | `services/bootstrap/`（steps/* + context / sse / parse / retry / save_all / completion）；残留 500 行编排壳 |
| `apps/backend/app/services/ai_service.py`（2895行） | `services/ai/`（chat / quality / debrief / draft_stream / outline_ai / memory_ai / coherence / guardrails / sampling / writing_tools / client / service）；残留 10 行 re-export |
| `apps/client/src/components/Writing/ChapterEditor.tsx`（3168行） | `Writing/ChapterEditor/` 包（index.tsx + types/utils/constants + PlanCard/CharacterMiniCard/DebriefPanel + hooks/）；残留 4 行壳 |
| `apps/backend/app/routers/ai/gated_draft_routes.py` | gated_draft_helpers.py（461行）+ gated_draft_quality.py（367行）+ 编排壳（358行） |
| `apps/backend/app/routers/ai/reader_simulation_routes.py` | reader_simulation_schemas.py（136行）+ reader_simulation_helpers.py（324行）+ 编排壳（534行） |

---

## 前端组件拆分蓝图（待落地）

| 当前文件 | 实测行数 | 目标结构 |
|---|---:|---|
| ~~`apps/client/src/pages/OutlinePage.tsx`~~ | — | ✅ `pages/Outline/`：`index` / `OutlineTreeSidebar` / `NodeDetailPanel` / `tabs/*` / `diffUtils` / modals |
| ~~`apps/client/src/components/Layout/GenerationQueuePanel.tsx`~~ | — | ✅ 已落地 `Layout/GenerationQueue/` |
| ~~`apps/client/src/pages/WorldBuildingPage.tsx`~~ | — | ✅ 已落地 `pages/WorldBuilding/`（见下方蓝图） |
| `apps/frontend/src/pages/ReadingReviewPage.tsx` | 1538 | 拆 `ReviewList` / `SnapshotDiff` / `useReviewSubmit` |
| ~~`apps/client/src/pages/CharactersPage.tsx`~~ | — | ✅ 已落地 `pages/Characters/` |
| `apps/client/src/components/Writing/ChapterEditor/index.tsx` | 2146 | 继续拆 `TopToolBar` / `WarnPanel` / `ContextSidePanel` JSX 块 |

**约束**：上述文件**冻结新增功能**；新需求必须先开拆分 PR。

### WorldBuildingPage 拆分蓝图（✅ 2026-05-21 已落地）

```
pages/WorldBuilding/
├── index.tsx                     # Tab 切换壳（53 行）
├── config.ts                     # SUB_TABS 配置
├── shared/components.tsx         # 共享表单组件（146 行）
└── tabs/
    ├── StoryLinesTab.tsx         # 164 行
    ├── PowerSystemTab.tsx        # 271 行
    ├── SkillsTab.tsx             # 241 行
    ├── ItemsTab.tsx              # 255 行
    ├── FactionsTab.tsx           # 321 行（含关系图 lazy）
    └── LocationsTab.tsx          # 128 行
```

`WorldBuildingPage.tsx` 保留 2 行 re-export，兼容 `ProjectCachedViews` 懒加载路径。

### GenerationQueuePanel 拆分蓝图（✅ 2026-05-21 已落地）

```
Layout/GenerationQueue/
├── index.tsx              # 悬浮壳 + 展开切换（69 行）
├── QueueList.tsx          # 展开态列表（59 行）
├── TaskCard.tsx           # 单任务卡片（175 行）
├── useGenerationQueue.ts  # 调度 / executeTask / cancel（169 行）
├── utils/sseHelpers.ts
└── runners/               # 按任务类型拆分（最大 gatedRewrite 297 行）
```

`GenerationQueuePanel.tsx` 保留 2 行 re-export，`AppLayout` 懒加载路径不变。

### CharactersPage 拆分蓝图（✅ 2026-05-21 已落地）

```
pages/Characters/
├── index.tsx                 # 列表 + 详情 + 关系图切换（107 行）
├── useCharactersPage.ts      # 筛选 / 分组 / CRUD（130 行）
├── CharacterList.tsx         # 左侧列表栏（243 行）
├── CharacterEditor.tsx       # 详情多 Tab 编辑（551 行）
├── ChangelogTab.tsx          # 变更记录 Tab（228 行）
└── shared/constants.ts + components.tsx
```

`CharactersPage.tsx` 保留 2 行 re-export。

### DebriefPanel 拆分蓝图（✅ 2026-05-21 已落地）

```
ChapterEditor/DebriefPanel/
├── index.tsx              # 编排壳（282 行）
├── HistorySection.tsx     # 落库历史审计（87）
├── CharUpdateSection.tsx  # 人物状态（132）
├── StorylineSection.tsx   # 故事线推进（97）
├── AssetUpdatesSection.tsx
├── ReaderPromisesSection.tsx
├── useDebriefAssets.ts
└── constants.ts
```

`DebriefPanel.tsx` 保留 2 行 re-export。

---

## 代码文档与注释契约（架构级）

本节约束 **人机协作与长期演进**：注释不是为了「行数好看」，而是让 **公共 API、业务不变量、失败形态与边界** 在一屏内可被读懂。

### 原则

- **公共表面优先**：凡 `export` 的函数、类、hook、跨模块复用的类型辅助，必须具备可被 IDE 悬停展示的说明。
- **意图优于复述**：不写「把 x 赋给 y」式废话；写 **为什么这样做**、**与哪条产品/架构决策对齐**、**违反时会怎样**。
- **类型与文档分工**：TypeScript 类型表达「是什么」；JSDoc 补充 **业务语义、前置条件、副作用、与后端契约**。
- **语言**：面向维护者与 AI 的注释以 **简体中文** 为主；已与对外 API/协议锁定的英文专有名词保持原文。

### TypeScript / JavaScript（`apps/client`、`apps/frontend`）

| 对象 | 最低要求 |
|------|----------|
| 模块 | 文件职责复杂或入口非自解释时，使用 `@file` / 顶部块说明 **职责与禁止事项**。 |
| `export function` / `export const` 工厂 | 完整 JSDoc：`@param`、`@returns`；异步函数说明 rejection 场景或统一错误形态。 |
| React 组件（命名导出） | 说明 **数据来源**（store / props / URL）、**关键副作用**（订阅、阻塞导航）。 |
| 自定义 Hook | 说明 **依赖**（哪些参数变化会触发重新请求）、**返回值契约**。 |

**推荐标签集合**：`@param`、`@returns`、`@throws`、`@deprecated`、`@internal`、`@example`、`@see`。

**反面模式**：整文件无注释但大量魔法字符串；仅英文拼音缩写无释义；注释与实现漂移（改代码必改注释）。

### Python（`apps/backend`）

- **路由 handler、service 公共方法、复杂纯函数**：使用 **Google 风格 docstring**（`Args` / `Returns` / `Raises`）。
- **AI 路由**：实现位于 `apps/backend/app/routers/ai/` 包；新端点在同一子模块内保持 **模块顶注释说明资源边界**。

---

## 开发建议（给未来的 Claude）

0. **动手前先读「代码结构红线」与「上帝文件登记册」**：若改动文件已在登记册，**禁止**直接在原文件里加新功能；先按「拆分蓝图」落新代码，再考虑老文件的迁移节奏。

1. **加新 AI 能力**：新能力走 `services/ai/<capability>.py` 的自由函数 + mixin，禁止往 `AIService`（现为 10 行 re-export 壳）直接堆方法；router 层永远不直连 OpenAI。

2. **加新 Bootstrap Step**：新建 `services/bootstrap/steps/<step_name>.py`，在 `graph.py` 薄壳里加一个节点 + yield；禁止把逻辑写进编排壳。

3. **加新数据表**：`models/` 新建文件 → `models/__init__.py` 导出 → `schemas/` 对应 → `routers/` 路由 → `main.py` 注册 → 写 Alembic migration。

4. **Prompt 优化**：prompt 字符串统一放在 service 层；超 30 行抽到 `*/prompts/*.py`；需要 JSON 时在提示词末尾强调「只返回 JSON」。

5. **JSON 解析**：所有 `_call_ai` 的 JSON 解析用 `_parse_json()` 统一处理，禁止 try/except 分散在各处。

6. **Embedding**：写入记忆后调用 `embed_chunk_async(chunk_id, text, SessionLocal)` 触发异步向量化；写章 RAG 检索走 `retrieve_and_log_draft_context()`，结果自动落 `rag_retrieval_log`；换 embedding 模型时需同步改 `EMBEDDING_DIM` 并执行对应 migration。

7. **改创作端 UI**：主要改 `apps/client/`；**管理后台**改 `apps/frontend/`（与 client 独立依赖与构建）。

8. **PR 自检**：提交前对触线文件执行 `wc -l <file>`，超硬上限必须**先拆再合**；新建 step / capability / sub-router 必须落到蓝图指定路径。

---

## 本地启动命令

```bash
# 环境与依赖（根目录）
bash bootstrap.sh

# Docker 一键启动（含 backend + client + frontend 管理端）
docker-compose up -d

# 本地裸跑：后端 + 创作端（pnpm；端口见 env.local.ports.example）
./restart.sh

# 管理后台（另开终端，默认 http://localhost:3174）
cd apps/frontend && pnpm run dev

# 仅手动启后端
cd apps/backend && source .venv/bin/activate && uvicorn app.main:app --reload --port 9000

# 仅手动启创作端
cd apps/client && pnpm run dev

# embedding 存量补跑（换模型 / 新部署后执行）
cd apps/backend && python verify_pgvector.py --reembed
```
