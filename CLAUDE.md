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

- Gemini 支持 100 万 token context，长 context 优势已体现在各 step 可获得更完整的上下文摘要注入，而非切换为单次全量模式。

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
  ├── OutlineIssueLog（大纲质检问题台账；linter 落库 → 下卷生成期回灌）
  └── RagRetrievalLog（每次 RAG 检索落库，含命中条目、status、duration_ms）
```

所有 UUID 主键，`project_id` 外键贯穿所有表。

### Character 增强字段（v2）
新增：`alias`别名、`appearance`外貌、`clothing_style`服装、`current_realm`当前境界、
`realm_rank`境界数字排序、`speech_style`说话风格、`values`价值观、`secrets`秘密、
`trauma`心理创伤、`fear`恐惧、`arc_stages`结构化成长阶段、`known_skills`/`owned_items`
快速引用、`current_status`当前状态（alive/dead...）、`current_location`位置、
`author_notes`作者备注、`faction_id`/`faction_rank`关联势力表。

### Character.extra.location_milestones（v3，2026-06，防空间漂移）
地点逐章台账，与 `extra.debrief_realm_milestones`（境界轨迹）同模式：复盘时若角色位置发生变化，
向数组 append 一条 `{chapter_number, chapter_id, chapter_title, location, from_location, reason, source}`
（`current_location` 仍单值覆盖最新位置，台账保留完整轨迹）。
- **写入**：`routers/ai/debrief_char_updater.py` 处理 `current_location` 时，仅在位置真正变化时落账，同章重复复盘按 `chapter_number` 去重。
- **移动原因**：`reason` 来自复盘 AI 新增字段 `location_change_reason`（`debrief_extract.py` prompt + `routers/ai/schemas.py:CharacterUpdate`），手动 Tab/队列自动复盘双路径透传（`utils/generatedChapterDebrief.ts` / `hooks/useDebriefRun.ts`）；复盘面板 `CharUpdateSection.tsx` 提供可编辑「移动原因」框（填了新位置才出现）。
- **写章注入**：`services/ai/context_builder_continuity.py` 在人物状态行追加「近期行踪[第N章→地点（原因）]」（末2条），并在「禁止事项」加空间连续性硬约束：位置变化必须在正文交代移动过程与原因、合时间线与常理，禁止无交代瞬移。

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
- `extra.consistency_issues`：Step 13 产物，一致性矛盾列表
- `extra.power_timeline_table_v1`：卷级结构化战力时间轴快照（主角起止境界、Boss 境界与趋势）
- `extra.enable_issue_feedback`：章纲展开是否注入历史高频 linter 问题回灌（默认 `true`；A/B 可关）

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
| `/api/v1/projects/{pid}/outline/volumes/{vid}/expand-chapters` | **按卷懒展开章纲**（SSE，Bootstrap 之后） |
| `/api/v1/projects/{pid}/consistency/fix` | 一致性问题 AI/规则修复 |
| `/api/v1/projects/{pid}/consistency/rescan` | 一致性重扫 |
| `/api/v1/projects/{pid}/reader-promises/` | 读者承诺 CRUD |
| `POST /api/v1/bootstrap/runs` | **一句话→全量生成（Bootstrap，LangGraph）** |

---

## 写作风格档位（writing_style，2026-06）

> 设计动机：番茄纯爽文要求正文「一看就懂」，与系统默认的「文笔老练/让事件自己说话」取向冲突。
> 故引入全书级写作风格档，**贯穿立项→采样→正文→质检→复盘→上游章纲/卷骨架**一条同向链路，
> 消除「正文写直白、质检按文笔扣分、复盘又把文风拉回」的跨环拉锯。

三档：`plain`（白话直白/小白友好）/ `standard`（默认）/ `dense`（老白文）。

- **落库**：`Project.extra.writing_style` + `Project.extra.positioning.writing_style`（双写，下游统一读 positioning）；建书时由 `GenerateWizard` 选择，bootstrap `steps/project.py` 落库。
- **番茄线默认 plain**：`graph_fanqie.py` 入口默认 `plain`；`routers/bootstrap_graph.py` 在 `mode=fanqie` 时把未改动的 `standard` 提升为 `plain`（显式选 `dense` 仍尊重）。
- **统一读取**：`app/utils/writing_style.py`（`resolve_project_writing_style` / `writing_style_from_extra`）——顶层 + positioning 双兜底，禁止各处现读。
- **链路落点**：
  - 正文：`draft_stream.py` plain 时整段分叉 system 核心原则 / 严禁清单 / 截图时刻为番茄版（非「先禁后松绑」）。
  - 采样：`llm_task_profiles.draft.plain`（低温 0.7 / 近零 penalty，允许金手指/境界/数值反复砸）；`phase_to_draft_task(phase, writing_style)` plain 时优先返回 `draft.plain`。
  - 质检：`quality.py` plain 新增 `readability` 维度，直白/口语/解释清楚不扣分，禁止「增强文采」类 suggestions。
  - 复盘：`debrief_extract.py` plain 时 `next_chapter_directives` 禁止「增强文采/留白」类指令（directives 是写章最高优先级注入）。
  - 上游：`steps/vol_chapter_plans.py`（章纲，prompt 见 `prompts/vol_chapter_plans_prompt.plain_chapter_plan_addendum`）+ `steps/volumes.py`（卷骨架燃点/高潮）+ `writing_scene_plan.py`（分场，从 positioning 识别）均加 plain 约束，从源头让蓝图稀疏直白。

## 番茄专线（graph_fanqie，diverge upstream / converge downstream）

番茄书走独立 LangGraph（`graph_fanqie.py`），但**产物归一化进通用线**，不维护平行栈：

```
START → fanqie_positioning → gate → project
  → contrast_design → golden_finger → face_slap_map
  → power_ladder → characters
  → volumes        # 复用通用 Step 9 gen_volumes 出卷骨架（不再走 opening_5chapters）
  → rhythm_map → signal_audit → END
```

- **收敛**：`signal_audit` 末调 `fanqie_normalize.converge_fanqie_project`，把番茄规划产物写成与通用线相同的 `OutlineNode/PowerSystem` 列与 extra 契约；规划层保留 `Project.extra['fanqie_*']`。
- **章纲展开**：`routes_vol_expand` 升级为「未满卷增量补全 / 满卷 force 重做」，`fanqie_volume_expand.prepare_volume_chapter_expand` 解析补全区间 + seed_nodes，`gen_vol_chapter_plans` 新增 `chapter_from/chapter_to/seed_nodes`。
- **已弃用**：`steps/fanqie/opening_5chapters.py` 移出 graph chain，仅存量 `extra.opening_5chapters` 物化 1–5 章时兼容（文件头已标注）。

## 一句话生成（Bootstrap）

唯一流程：**串行步进（Sequential）**，LangGraph 编排，入口 `POST /api/v1/bootstrap/runs`。

> 方案 B（单次全量 single_shot）已于 2026-05 移除：`save_all.py` / `completion.py` / `prompts/single_shot.py` 已清空为废弃存根，`routers/generate.py` 已清空，`generation_service.bootstrap()` / `_sequential()` / `_single_shot()` 已删除。

实际执行拓扑（graph.py 定义，非简单串行）：

```
logline
  → [Step 0  立项会议]       positioning        _gen_positioning
  → [gate 立项确认]
  → [Step 1  项目]           project            _gen_project
  → [Step 2  境界体系]       power_systems      _gen_power_systems
  → [gate_power 境界确认]
  → [Step 3  势力]           factions           _gen_factions
  → [Step 4  故事线]         storylines         _gen_storylines
  → [Step 4.5 卷级对立面]    antagonist_ladder  _gen_antagonist_ladder  （每卷 Boss 名+境界 roster → Project.extra）
  → [Step 5  人物]           characters         _gen_characters         （必须为 roster 各 Boss 建档）
  → [gate_characters 人物确认]
  → [Step 6+7 技能+道具]     skills_items       _gen_key_skills ∥ _gen_key_items
  → [Step 8  设定卡]         settings           _gen_settings
  → [Step 9  卷骨架+phase]   volumes            _gen_volumes
  → [gate_volumes 卷质量门控]
  → [Step 9.5+9.8 并行]      emotion_villain    _gen_emotion_arc ∥ _gen_villain_arc
  → [Step 10+11 并行]        memory_relations   _gen_memory ∥ _gen_relations
  → [Step 11.5 核心谜题]    core_mysteries     _gen_core_mysteries
  → [Step 12 开局承诺]       opening_contract   _gen_opening_contract
  → [Step 13 一致性扫描]     consistency        _gen_consistency_scan
  → END
```

**Bootstrap 止于卷骨架 + 设定闭环，不生成章纲/场景。** 章级 `chapter_plan` 与 `Scene` 在写作期按需展开（见下节）。

- 每步独立 prompt，上下文逐步累积（压缩摘要 + 立项定位传入）
- 单步失败重试 1 次，不影响其他步骤
- SSE 每步推送 `step_start` / `step_done` / `error` / `linter_blocked`
- **Step 1 项目**：书名海选 15~20 个候选（6种策略，一次 LLM 调用内打分排序）；premise / world_overview 均为结构化对象，按字段精确存 `extra`，渲染为字符串写模型列（向后兼容）
- **Step 0 立项会议**：从一句话推导目标读者画像、爽点类型、打脸频率、情感线占比、节奏类型，作为后续各步的全局约束。这是网文系统区别于"AI 自由发挥"的关键防线。
- **Step 9**：只落库 `OutlineNode`（volume）；每卷含 **导演单节拍**（`extra.beat_highlights` 燃点 2～4 条、`volume_climax` 卷末高潮、`pacing_skeleton` 等，`highlight` 列存高潮摘要）；落库后跑 `lint_volume_entity_issues`，战力曲线 high 级问题写入 `ctx.volume_entity_lint`，**不自动重试 LLM**；闸门「重新生成」或单步重跑时 `inject_realm_fix_hint=True` 注入修正提示后再调一次。章纲展开/写正文注入节拍；章纲 linter 规则 VB-* 校验燃点/高潮呼应。
- **Step 13**：交叉核验所有生成物，矛盾列表写入 `Project.extra.consistency_issues`。
- **已移出 Bootstrap（2026-05）**：原 Step 12.5 `vol1_chapters`、原「第1章场景」`ch1_scenes`（旧拓扑中的独立步，非现 Step 13）不再挂入 `graph.py`；实现仍保留于 `steps/vol1_chapter_plans.py` / `ch1_scenes.py`，**单步 regen 不支持**；现 Step 13 仅指 `consistency`。

### 写作期：按卷懒展开章纲（Bootstrap 之后）

| 入口 | API | 实现 |
|------|-----|------|
| 大纲页「展开章纲」 | `POST /api/v1/projects/{pid}/outline/volumes/{volume_id}/expand-chapters`（SSE） | `build_vol_expand_ctx` + `gen_vol_chapter_plans` |
| 章纲 → 分场 | `POST .../ai/scene_routes` plan-save / draft / stitch | 写作页 `ScenePipelinePanel` |

- **每次只展开一卷**；第一卷与后续卷同路径（无 Bootstrap 特例）。
- 上下文含 Tier1–5 editorial 块 + 已写章节摘要 / 记忆 / 读者承诺 + **历史高频问题回灌**（`outline_issue_logs` → `build_issue_feedback_block`）；分批 1–30 / 31–60 章生成，落库后过章纲 linter（GEN-02）并写入问题台账。
- 旧路径 `POST /outline/ai-expand`（arc 预览→commit）、`ai-full-generate` 仍保留，volume 主路径以 `expand-chapters` 为准。

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
| 卷级对立面 roster | `Project.extra.antagonist_ladder` | Step 4.5 `_gen_antagonist_ladder` |
| 人物 | `Character` | Step 5 `_gen_characters`（arc Boss 须对齐 roster） |
| 核心技能/功法 | `Skill` | Step 6 `_gen_key_skills` |
| 关键道具/法宝 | `Item` | Step 7 `_gen_key_items` |
| 纯叙事设定 | `WorldSetting`（分类存 `extra.category`） | Step 8 `_gen_settings` |
| 卷级大纲 + phase + 节拍 | `OutlineNode`（volume）+ `phase` + `extra.beat_highlights` / `volume_climax` / `highlight` | Step 9 `_gen_volumes` |
| 情绪节律图 | `Project.extra.emotion_arc` | Step 9.5 `_gen_emotion_arc` |
| 反派行动线 | `Project.extra.villain_arc` | Step 9.8 `_gen_villain_arc` |
| 记忆种子 | `MemoryChunk` | Step 10 `_gen_memory` |
| 人物关系 | `CharacterRelationship` | Step 11 `_gen_relations` |
| 核心谜题 | `Foreshadow` + `Project.extra.core_mysteries` | Step 11.5 `_gen_core_mysteries` |
| 开局追读承诺 | `Project.extra.opening_contract` + `ReaderPromise` | Step 12 `_gen_opening_contract` |
| 一致性矛盾列表 | `Project.extra.consistency_issues` | Step 13 `_gen_consistency_scan` |
| 卷下章节蓝图 | `OutlineNode`（chapter_plan） | **写作期** `expand-chapters` → `gen_vol_chapter_plans`（非 Bootstrap） |
| 章节分场蓝图 | `Scene` | **写作期** Scene 三层调度 / `scene_routes`（非 Bootstrap） |

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
- [x] 一句话生成（串行步进，LangGraph；方案B单次全量已移除）
- [x] 故事线/境界体系/技能/道具/势力前端 UI（WorldBuildingPage 五标签页）
- [x] Bootstrap 全量步骤（Step 0–13，含 9.5 情绪节律图 / 9.8 反派行动线 / 11.5 核心谜题；**不含**章纲/场景）
- [x] 按卷懒展开章纲（`expand-chapters` + `gen_vol_chapter_plans` + 章纲 linter）
- [x] 伏笔台账双向关联（`foreshadow_sync.py`，幂等写入）
- [x] 大纲生成防漂移（字数预算约束 + 卷间衔接强制承接）
- [x] 章纲 linter v1.2（CH/SEQ/VL/OC/RP/CM；GEN-02 阻断；`VolumeLinterPanel`）
- [x] **大纲问题台账 + 生成期回灌（支柱一）**（2026-05-29）：`OutlineIssueLog` + `services/outline_quality/`（`contract` / `issue_log` / `feedback_block`）；`gate.py` linter 后 `record_issue_set`；`context_vol_expand` 跨卷 `top_frequent_issues` 注入 prompt；SEQ-01 prompt 拆至 `prompts/vol_chapter_plans_prompt.py`；前端无改动
- [x] Scene 三层调度全链路（plan-save / draft/stream / stitch）+ 前端 `ScenePipelinePanel`
- [x] 势力境界进阶关系图（React Flow，FactionRealmFlow）
- [x] 任务级采样配置（`llm_task_profiles.py`）
- [x] Bootstrap 流派分流增强（`_get_genre_kit_block`；speech_kit；POV + 戏份预算）
- [x] ReaderPromise 写章注入 + 读者模拟反馈闭环（基础链路）
- [x] RagRetrievalLog 落库（每次检索可查 source / status / hits）
- [x] 卷级结构化战力时间轴（`/outline/power-timeline` + 创作端「战力轴」页）
- [x] **地点逐章台账 + 空间防漂移**（2026-06）：`Character.extra.location_milestones` 逐章记录位置变化与移动原因（`location_change_reason`）；复盘双路径透传 + 可编辑「移动原因」框；写章注入「近期行踪」与空间连续性硬约束。地点入库仍走复盘期 `location_debrief.enrich_new_locations`（queue_auto 经 `chapter-debrief` 已触发，非 Bootstrap/势力生成期）

### 大白文实验前端（dabai API，2026-06-10）

- **书架**：`/dabai` → `pages/Dabai/`（网格同「我的书架」，数据走 `/api/v1/dabai`）
- **写作**：`/dabai/:id/write-dabailab` → `pages/Dabai/write-dabailab/`（章纲侧栏 + 五拍要素 + 流式正文；无 DabaiResult / TipTap）
- Bootstrap **dabaiwen** 仍走 `/project/:id/dabai-write`，与实验书架分离

### 实验书架写作期产物链路（预警/质检/记忆/线索，2026-06-10 二批）

lab 侧（dabai_* 表）补齐写作期四件套，与精品文链路隔离、全部落库（持久化优先）：

- **新表**（`models/dabai_lab.py` + migration `f3a4b5c6d7e9`，FK 均 ondelete=CASCADE）：
  `dabai_pre_warn_records`（导演单，每章最新一条）/ `dabai_quality_reports`（质检报告，每章最新一条）/
  `dabai_memories`（复盘记忆，章级幂等）/ `dabai_clues`（线索台账 open/resolved/dropped）。
- **预警**：`lab_pre_warn.resolve_lab_pre_warn` 增 `db` 参数落库（`persist_lab_pre_warn`）；
  前端 `DabaiDraftEvent` 增 `pre_warn_running/done`，写作区右侧栏「预警」面板实时 + 落库回看。
- **质检**：`services/dabai/lab_quality.py`（规则层 DLB-01 字数偏离 / DLB-02 见证者缺席 + LLM 层复用
  `quality_check._merge_report`，DBQ-* 口径一致；task=`dabai.quality`）。⚠️ `quality_check` 必须函数内
  延迟导入（经 draft_stream→AIService→routers.ai 有循环 import 链）。
- **复盘**：`services/dabai/lab_debrief.py`（task=`dabai.debrief`，提取记忆 3-8 条 + 线索埋设/回收；
  同章重跑先删旧记忆；新线索按标题去重、回收按 id 精确匹配；mock 项目走章纲启发式降级）。
- **端点**：`routers/dabai_lab_ai.py`（prefix `/dabai`）：POST `chapters/{cid}/quality-check`（mode=rules|full）、
  POST `chapters/{cid}/debrief`、GET `quality-report` / `pre-warn` / `memory?chapter_id=` / `clues?status=`、
  PATCH `clues/{id}`（手动纠偏）。
- **前端**：`api/dabaiLab.ts` + `types/dabaiLab.ts`；写作区右侧折叠栏 `write-dabailab/side/`
  （WorkspaceSidePanel：预警/质检/记忆三 Tab，随章刷新）；顶层 tab 增 `memory`（记忆库，按章分组+类型筛选+搜索）
  与 `clues`（线索台账，状态筛选+手动回收/弃用），`workspaceTab.ts` 为唯一 tab 定义源。
- **写章流自动闭环**：写前预警（mock 跳过）→ 正文 → 正文落库后同流自动质检+复盘
  （`routers/dabai.py:_auto_qc_debrief`，SSE `quality_running/done`、`debrief_running/done`；
  单步失败 yield 带 error 的 done 事件不中断流；mock 项目质检只跑规则层、复盘走启发式）。
  侧栏「质检/记忆」面板经 refreshKey 自动重拉；手动按钮保留（可重跑）。

### 实验书架双台账：资产 + 人物关系（2026-06-11 三批）

> 设计决策：**不照搬**主链路 Skill/Item/CharacterRelationship 三表（避免平行栈），
> 用两张轻量台账表治三类漂移：能力漂移、资产漂移、关系漂移（敌对→臣服→效忠即爽点曲线）。

- **新表**（migration `a4b5c6d7e8f1`）：`dabai_assets`（kind=skill/item/golden_finger，owner 人名字符串，
  status=active/consumed/lost + status_chapter）/ `dabai_relations`（from/to 人名、attitude 最新态度、
  `history` JSON 保留完整轨迹 `{chapter, attitude, reason}`，chapter=null 表示手动改）。
- **服务**：`services/dabai/lab_ledger.py` 三职责——
  ① `seed_ledgers`：开局派生（金手指→资产；人物 role→初始态度：打脸对象=敌对/女主=暧昧/导师=扶持），
  幂等（有 seed 行即跳过），写章流/复盘/GET 端点均惰性触发；
  ② `build_ledger_block`：注入块（主角 active 资产 + 在场人物关系 + 硬约束「禁用台账外能力/已消耗不得再用/态度变化须交代」），
  注入正文 prompt（`dabai_write.build_prose_prompt` 增 `ledger_block` 参数）+ 导演单 prompt + 复盘 prompt；
  ③ `apply_ledger_changes`：复盘新增 `asset_changes`（gain/consume/lose/upgrade，gain 按 name+owner 去重、
  失而复得自动复活）与 `relation_changes`（同章重跑替换该章轨迹，幂等）。
- **端点**：`dabai_lab_ai.py` 增 GET/PATCH `assets`、GET/PATCH `relations`（手动纠偏）。
- **前端**：顶层 tab `ledger`（台账，`LedgerPanel` 资产/关系双子页：状态标记、态度下拉改、轨迹展开）；
  复盘结果卡片显示资产/关系变更摘要。

### 实验书架 P0 优化：记忆/线索回灌 + 写后抗断流（2026-06-11 四批）

- **回灌（修「只写不读」缺口）**：`lab_draft_context.py` 增 `memory_block`
  （重要度 desc + 时效 Top-8，跨越近3章窗口之前的事实对模型可见）与 `clue_block`
  （open 线索按埋设章号升序——埋越久越优先提醒回收）；注入正文 prompt
  （`build_prose_prompt` 增 `memory_block`/`clue_block` 参数）+ 导演单 prompt（经 ctx 透传）。
- **写后抗断流**：质检+复盘从 SSE 生成器内移至 `services/dabai/lab_post_write.py`
  `spawn_post_write_pipeline`——独立 SessionLocal 的 asyncio task，经 Queue 向 SSE 转发进度；
  客户端关页只丢展示，落库照常完成。`_POST_WRITE_TASKS` 强引用集合防 GC。
  `debrief_done` 事件增 `asset_changes`/`relation_changes`。
- **已识别未做**（P1/P2 备忘）：质检+复盘合并单次调用省成本；同章重跑复盘清理本章旧
  debrief 线索；重写复用本章最新导演单。（境界倒退阻断 / suggestions 回灌 /
  DLB-02 误报软化已于「正文质检闭环批」完成，见下节 2026-06-12 三批）

### 实验书架正文质检闭环 + 误报治理（2026-06-12 三批）

> 修两类结构性问题：①质检报告「只写不读」（suggestions 无消费方、无书级聚合）；
> ②规则层与 LLM 层裁决双轨打架（DLB-03 事后压分 vs prompt 教 LLM 别扣分）。

- **裁决权单轨**：DLB-03 规则降级为「证据收集」——证据注入 LLM 质检 prompt
  （`_build_lab_qc_prompt` 增 `bridge_evidence`），LLM 按正文裁决；规则 warning 标
  `llm_overridable`，LLM 正常返回时在 `_merge_report` 丢弃（降级时保留兜底）；
  `_cap_continuity_for_location_gap` 事后压分已删除。
- **规则分计权**：`_merge_report` 综合分在 40/40/20 加权后扣规则层 warning（每条 -5
  封顶 -15；`score_exempt` 标记除外，DBC-03 自述可忽略不扣）。此前规则 warning 对
  综合分零影响。
- **五拍缺字段不再默认满分**：`_beat_summary` LLM 漏返回的拍按 partial(60) 计并标注。
- **DLB-02 去硬编码**：`lab_quality._WITNESS_ALIASES`（含样书专名）删除，改为规则派生
  （全称/去括号/「的」分段/前缀 + `_WITNESS_GROUP_SETS` 同义词组）；
  `first_chapter_opening.witness_stems` 同步清除人名 dict。
- **境界倒退**：主线 DBC-01 与新增 lab **DLB-04（阻断）** 共用
  `consistency_check.realm_regression_hit`——回忆/对比/突破自述语境豁免
  （`_RETRO_BEFORE/_RETRO_AFTER` 窗口）；DLB-04 双重收窄：仅查主角名 ±24 字窗口
  （他人低境界是正常剧情），DBC-02 误报前车之鉴。
- **质检读端**（新 `services/dabai/lab_qc_feedback.py`）：
  ① 章级 `build_chapter_qc_feedback_block`——重写时注入上一版报告 blockers/suggestions/
  未落实拍（`build_prose_prompt` 增 `qc_feedback_block`，仅 replace_existing 注入）；
  ② 书级 `build_project_qc_issue_block`——各章**最新**报告聚合高频 rule_id（≥2 次才注入），
  经 `volume_expand` ctx[`qc_feedback`] 回灌章纲展开 prompt（对齐精品线支柱一）。
- **质量欠债（派生视图，无新表）**：`lab_quality_query.list_dabai_quality_debts`
  （各章最新报告 <70 分或 blocked）+ GET `/dabai/projects/{id}/quality-debts?threshold=`。
- **其他**：QC prompt 长章（>6500 字）补中段 800 字抽样（重复铺陈多发于中段，主线/lab 同步）；
  `_build_continuity_snapshot` 增 `ctx` 参数复用调用方 LabDraftContext 不重复查库。
- 注意：沙箱无 3.12 venv，仅过纯函数冒烟；合入前跑
  `pytest tests/test_dabai_lab_continuity.py tests/test_lab_ledger_p0.py tests/test_dabai_first_chapter_opening.py`。

### 实验书架 Bootstrap 新步骤：剧情资产+初始关系（story_assets，2026-06-11 五批）

> 设计决策：台账种子从「规则启发式」升级为「建书期 LLM 生成」，且**开局既有 vs 剧情规划必须分流**——
> 未获得的东西进「当前台账」注入会让模型提前用（能力漂移），故规划类落线索台账，获得后复盘自然转资产。

- **链路位置**：`storylines → story_assets → volumes`（`dabai/config.py` PIPELINE_STEPS，温度 0.65）。
- **产出契约**（`dabai/schemas.py`）：`{plot_assets: [{kind, name, plot_role(争夺点/底牌/成长线/身世信物),
  owner, debut: start|later, planned_volume, description}], initial_relations: [{from, to, attitude, tension}]}`；
  金手指不重复列入（已单独建账）。
- **落库分流**（`dabai_persist._save_story_assets`）：debut=start → `dabai_assets`(source=seed, active)；
  debut=later → `dabai_clues`(foreshadow, chapter_planted=0, source=bootstrap)；
  initial_relations → `dabai_relations`(source=seed, history 锚定第0章, note=张力)。
  bootstrap 已写 seed 行 → `lab_ledger.seed_ledgers` 启发式自动跳过（幂等兼容存量书）。
- **下游一致性**：`prompts._ctx_brief` 注入「剧情资产（卷/章纲须围绕这批东西做文章，禁止另造同位宝物）」，
  volumes 与 chapter_outlines prompt 自动携带。
- **mock**：`mock_responses._STORY_ASSETS`（林凡宇宙样本）；前端 `DABAI_STEP_LABELS` 增「剧情资产·关系」。
- 注意：本仓 pytest 强制 3.12 venv；沙箱验证走 mock pipeline 冒烟（collect_bootstrap 全步通过）。
- **修复（同批）**：① `persist_bootstrap_result`（非流式口）步骤清单漏 `story_assets` 已补；
  ② `build_ledger_block` 资产按持有者归属（此前全标成主角的；他人资产现单列「其他人物持有（不归主角使用）」）；
  ③ 人物面板伴随台账：`CharactersPanel` 拉 assets/relations，按人名匹配显示每人持有功法/道具
  + 对主角态度徽章 + 张力。存量书（建于该步骤之前）只有惰性种子，需重新生成才有完整剧情资产；
  台账表未 migrate 时接口 500、前端静默为空——先 `alembic upgrade`。

### 实验书架按次计费合并：设定链 9→6 次 + 章纲单次整卷（2026-06-12 五批）

> 计费按调用次数，合并调用是主收益；且同次推理产出的同域设定彼此对齐更好。
> 质量红线：title_blurb 不并入 volumes（0.85 vs 0.6 温度冲突），repair 闭环保留（lint 干净=0 次调用）。

- **设定链 9→6 次**（`pipeline._MERGE_CARRIERS` 扩展）：
  `golden_finger` 一次产出 金手指+境界阶梯+**反派阶梯**（Boss 档与境界档同次推理）；
  `storylines` 一次产出 叙事规划三块（故事线+剧情资产/关系+谜题排程，prompt 末尾强调「三块是一盘棋」）；
  `title_blurb` 后移到 volumes 之后（书名/简介可引用卷 Boss/大爆点，`_volumes_digest` 注入），独立保 0.85 高温档。
- **章纲单次整卷（主路径）**：`volume_chapters` 一次返回 `{beat_sequence, chapter_outlines}`
  （`prompts_chapter.volume_chapters`，system 加「先排完整表再展开」addendum）；
  窗口 ≤ `single_call_max_chapters`（默认 40）才走单次；`cfg.max_tokens` 8192→**30000**；
  失败/超大卷自动降级两段式（beat_sequence + 分批），再失败降级直接分批——三级兜底。
  repair 闭环保留（单次路径同样过 `repair_batch`）。
- **调用次数**：30 章/卷 bootstrap = 6 设定 + 1 章纲 + 0~1 修复 = **7~8 次**（此前 13~16）。
- **web 路径接线**：`routers/dabai.py` `_build_call` 对 heavy steps（volume_chapters/章纲/修复）
  传 `max_tokens=cfg.max_tokens`，其余设定步走网关默认（防小上限模型报错）；
  `llm_task_profiles.py` 新增 `dabai.benchmark/golden_finger/factions/storylines/volumes/`
  `title_blurb/volume_chapters/beat_sequence/chapter_outlines/chapter_repair` 采样档
  （此前 dabai bootstrap 任务全走网关默认温度，CLI 的 STEP_TEMPERATURE 不生效于 web 路径）。
- 验证：mock 全链 8 次调用通过；volume_chapters 失败降级两段式通过；60 章超大卷自动分批通过。

### 实验书架 Bootstrap 全面升级：三新步骤 + 富上下文 + 章纲两段式 + 修复闭环（2026-06-12 四批）

> 一次性落地「创建过程 prompt 优化 + 额外设定」全清单。不计 token 取向：
> 下游步骤改注全量结构化档案，章纲全局规划与局部展开分离。

- **三个新 Bootstrap 步骤**（`dabai/prompts_extra.py`，PIPELINE_STEPS 现 13 步）：
  ① `antagonist_ladder`（金手指后）——每卷 Boss roster（名/势力/境界档/仇怨/压迫方式/下场），
  Boss 档略高于卷主角区间、仇恨链逐卷升级；factions/characters 步必须为前 2-3 卷 Boss 建档；
  ② `mystery_schedule`（story_assets 后）——2-4 个跨卷谜题揭示排程（每卷透一块、揭底卷前禁说破），
  落 `extra.mystery_schedule` + `dabai_clues` 种子（标题去重）；
  ③ `title_blurb`——书名 12-16 候选（6 策略+打分）+ 上架简介，chosen_title 回填 `dabai_projects.title`。
- **prompt 模块重组**：`prompt_base.py`（SYS_BASE/ctx_brief/benchmark/ladder 块，防 import 环）+
  `ctx_rich.py`（人物档案含 desire/wound/speech_kit、开局关系、资产台账、势力+场景池、
  反派阶梯、谜题排程、故事线节点——全量注入 volumes/章纲，替代「只给人名」的 _ctx_brief）+
  `prompts_chapter.py`（章纲两段式+修复）。
- **既有步骤强化**：benchmark 加 confidence + 题材代称防幻觉；golden_finger 加
  `first_10_shuang`（前10章爽点弹药库）+ `realm_milestones`（境界×金手指里程碑表，防脱钩）；
  factions 加每势力 `locations` 场景池 + 工具人配角池 8-12 人 + 人物 `speech_kit`；
  storylines 加 `nodes`（卷绑定关键节点）+ `bound_characters`；volumes 接住 Boss/资产/谜题/节点
  （输出 `boss`/`storyline_moves`/`mystery_moves` → `dabai_volumes.extra`）；
  字数分档（普通 2000-2200/大爆点 2400-2600）；emotion_turn 增普通章扳机示例（防全书濒死腔）。
- **章纲两段式**（`steps.aiter_chapter_batches` 重构，bootstrap 与卷展开共用）：
  阶段一 `beat_sequence`——一次（>60 章分段）排整卷节拍行（章号/标题/爽点/场景/靶子/境界/一句话），
  全局协调轮换与爬升，失败降级直出；阶段二按 `chapter_batch_size`（默认 30→**10**）小批展开五拍，
  prompt 锁定本批节拍行。节拍快照落 `dabai_projects.extra.beat_sequence_vol{N}`。
- **修复闭环**（`dabai/repair.py`）：每批生成后 lint（REALM 由 `_enforce_realm` 硬保证不进修复；
  DB-02 仅全书开局批、DB-08 小尾批跳过）→ 问题章+issues+相邻章回灌 `chapter_repair`（温度 0.4）
  定向重写 → 按章号合并，修复章 realm_rank 强制还原；失败/空返回保留原批（增益不阻断）。
- **migration `e8f9a0b1c2d3`**：`dabai_projects.extra` / `dabai_factions.locations` /
  `dabai_storylines.nodes`+`bound_characters` / `dabai_volumes.extra`；
  卷展开 `build_expand_ctx` 从 extra 回读反派阶梯/谜题排程（卷2+ 与 bootstrap 同富上下文）。
- 前端：`DABAI_STEP_LABELS` 增 反派阶梯/谜题排程/书名·简介；detail 透出 extra/locations/nodes。
- 验证：沙箱 mock 全链 13 步通过（beat 30 行+章纲 30 章+linter）；repair 闭环冒烟通过；
  `test_dabai_linter` 4 用例通过。合入前请用 3.12 venv 跑 `pytest tests/`（沙箱无 venv）。

### 实验书架卷纲质检闭环（2026-06-12）

> 修复「质检 Tab 只读 bootstrap 快照、卷展开不更新」的架构断层。

- **单一 linter 服务**：`services/dabai/lab_outline_lint.py`（`run_dabai_project_linter`）从 `dabai_volumes` + `dabai_chapter_outlines` 读库全书章纲，跑 `dabai/linter.py`，补检按卷 `REALM-03`，写回 `DabaiProject.linter_report`（含 `linted_at` / `chapter_count`）。
- **触发点**：bootstrap 收尾（流式/非流式）、`volume_expand` 展开完成（SSE `linter_done`）、手动 `POST /dabai/projects/{id}/relint-outline`。
- **前端**：顶栏 Tab 改名「卷纲质检」；写作侧栏「正文质检」消歧；`LinterPanel` 空报告显示「尚未检测」+ 重新检测按钮（不再伪装 100 分通过）；卷展开 done 后 toast 带分数。

### 实验书架非系统文（法器流 / 魔道，2026-06-12）

> logline 含「不要系统」「魔门」「魂幡」等时，Bootstrap 自动走法器金手指口径。

- **检测**：`dabai/non_system.py`（`prefers_non_system`）读 logline + positioning.taboo_lines。
- **prompt 分支**：`golden_finger` 步输出 `manifestation_style`/`blood_price` 替代 `signature_lines`；章纲/正文禁止叮、面板、任务栏。
- **样章章纲**：`dabai/examples/ch01_momen_wan_hun_fan.json`（《魔门无情》第1章五拍，可对照写作页字段）。

### 实验书架分场层 + 章纲反同质化（2026-06-12 二批）

> 修「第一章质量差」的两个结构性根因：①章纲五拍一句话直接糊 2000 字正文（缺场面调度层）；
> ②30 章一批生成无场景/标题轮换约束 → 全书「演武场被辱→觉醒→打脸」一个模子。

- **分场层**（章纲→分场→正文，对齐精品文 Scene 三层调度但轻量化）：
  新表 `dabai_scene_plans`（migration `c6d7e8f9a0b3`，每章最新一条，先删后插幂等）；
  `services/dabai/lab_scene_plan.py`：写前导演单之后、正文之前一次 LLM 调用（task=`dabai.sceneplan` 0.55），
  五拍拆 2-4 场，每场锁定 地点/在场/动作链/**台词弹药 2-3 句原话**/感官锚点/场末转折/word_budget，
  另出 `opening_line`（黄金第一章前 3 行进冲突，禁环境/回忆开篇）。复用写章同一份 LabDraftContext 不重复查库；
  失败降级为五拍直写不阻塞。`build_prose_prompt` 增 `scene_block` 参数，有分场时 task 切「按场施工」模式
  （台词弹药须用上、感官锚点落正文、场间用场末转折过渡）。SSE 增 `scene_plan_running/done`；
  GET `chapters/{cid}/scene-plan` 可回看。重写时分场升温 0.7 换戏。
- **章纲反同质化**：`dabai_chapter_outlines` 新增 `location` 列（场景载体，同 migration）；
  `dabai/prompts.chapter_outlines` 加【反同质化】硬约束（场景载体轮换池/标题 5 策略轮换禁相邻同开头/
  打脸对象与憋屈手法轮换）；`dabai/linter.py` 增 `_lint_sameness`：DB-11（location 缺失/相邻雷同，
  存量书全空时跳过防误报）+ DB-12（相邻标题前 2 字相同=句式坍缩）。location 贯穿
  schemas→persist→`_detail`→前端 `DabaiBeatDisplay.locationName`（节拍卡已有槽位，直接接上）。

### 实验书架情节档案 + 双路检索（2026-06-14）

> 解决两件事：①写章/回看时没有一个地方「完整展示这一章实际写了什么」（核心事件散落在记忆/线索/台账各 tab）；
> ②dabai 检索只有 近期窗口 + 重要度兜底，**无语义/实体召回**——老的低重要度事实掉出窗口后，
> 旧角色再登场时其身份/恩怨无法被召回，长篇衔接断层主因之一。

- **情节档案（聚合视图，无新表）**：`services/dabai/lab_chapter_archive.py`
  （`build_project_archive` 全书 / `build_chapter_archive` 单章）按章组合
  计划五拍(`dabai_chapter_outlines`) + 复盘实际(核心事件/摘要 `dabai_memories`)
  + 线索埋设·回收(`dabai_clues`) + 资产获得·消耗(`dabai_assets`) + 关系态度变更(`dabai_relations`)
  + 首次出场(扫 involved/witnesses)。端点 `routers/dabai_lab_archive.py`（独立文件防 dabai_lab_ai.py 膨胀）：
  GET `/dabai/projects/{id}/archive`（全量）+ `chapters/{cid}/archive`（单章）。
  前端：共享 `ArchiveSections.tsx`；**右侧栏新增「档案」tab**（`side/ArchiveCard.tsx`，随章刷新，
  refreshKey=质检+复盘）；**左侧栏新增「档案」tab**（`panels/ArchivePanel.tsx`，全书可展开列表 + 已写/已复盘筛选）。
- **检索·实体召回（无新表）**：`lab_draft_context._build_entity_recall_block`——按本章
  `involved_characters + witnesses` 的人名 tags，捞回**窗口外**历史关键事实（不受重要度限制），
  注入 `memory_block`。`build_lab_draft_context`（同步）默认启用。
- **检索·pgvector 语义召回**：`dabai_memories` 加 `embedding` 列（migration `f9a0b1c2d3e4`，
  仅当 pgvector 扩展存在；维度=`EMBEDDING_DIM`）；复盘落库后 `lab_embedding.embed_dabai_memories_async`
  异步向量化（summary 跳过）；`semantic_search_dabai` 余弦召回。
  新增 `build_lab_draft_context_async`（异步壳）= 同步块 + 语义召回块；写作三路（draft / 导演单 / 分场，
  均 async）改用之。pgvector 不可用 / 向量化失败时返回空块，自动降级到实体召回 + 时序兜底。
  存量补跑：`python verify_pgvector.py --reembed-dabai`。
- 注意：沙箱无 3.12 venv，仅过 py_compile + 前端 tsc（新增文件零类型错误）；合入前请用 venv 跑后端测试 + `alembic upgrade head`。

### 大白文（dabaiwen）写章上下文链路（2026-06-10 重修）

> 背景：dabai 正文衔接差的三个根因均为**静默失效 bug**，已修复：
> ① `debrief_apply.py` 调用不存在的 `chapter.chapter_number` → 复盘一直 AttributeError 被路由层吞掉，图谱/向量记忆从未写入；
> ② `build_graph_context_block` 用字面量「主角」做 Neo4j key → 图上下文恒空，且 Cypher 未按 chapter 取最新事实；
> ③ `neo4j_client` 只读 `os.getenv`，而 pydantic-settings 的 .env 不注入 os.environ → 裸跑时图谱恒关闭（`NEO4J_*` 已声明进 `config.py` Settings）。

- **写章上下文**：`services/dabai/draft_context.py`（新）统一组装四块注入：图谱主角状态（最新境界/位置/近3次行踪/敌对）→ 前情提要（近3章一句话摘要+上章末钩子）→ pgvector 语义记忆（五拍要素做 query，落 `RagRetrievalLog` source=draft_context）→ 出场人物（witnesses）状态（图谱优先、Character 表兜底）。任一源失败只降级该块，不阻塞写章。
- **复盘幂等**：dabai 复盘记忆带 tag `dabai_debrief`，重跑先删同章同 tag 旧记忆；graph_facts 缺 chapter 字段自动补章号；提取 prompt 注入标准人名清单（禁「主角」代称，保证图谱 key 一致）。
- **prompt 顺序**：全局状态→前情→记忆→人物→上章结尾(600字)→五拍→任务；system 增加衔接硬约束（承接末钩子、位置变化须交代移动、以「当前状态」块为准）。
- **质检 v2**（`services/dabai/quality_check.py`）：规则层（DBC-01 境界倒退仍是唯一阻断）+ LLM 层（task=`dabai.quality` 低温 JSON：衔接 continuity / 五拍逐项 pass·partial·miss / 钩子强度，只出 DBQ-01~04 warning 与 ≤3 条可执行建议，禁文采类）；综合分=衔接40%+五拍40%+钩子20%；LLM 失败降级规则报告（`llm_status`）。gated 写章流与 `/ai/dabai-consistency-check`（升级支持 mode=rules|full + 模型线路）均走此入口。
- **复盘端点**：`POST /ai/dabai-debrief`（独立于主链路 chapter-debrief 两步流，单步提取+落库，幂等可重跑）；`GET /ai/memory` 支持 `chapter_id` 过滤。采样档：`dabai.quality` 0.2 / `dabai.debrief` 0.25。
- **写前导演单**（2026-06-10 三批，`services/dabai/pre_warn.py`）：写前一次低温 LLM 调用（task=`dabai.prewarn` 0.25）做「事实裁决 + 写法指导」，解决章纲五拍与实际剧情漂移时写章模型自行裁决出错的问题。输出 `fact_lock`（开笔境界/位置/在场/禁止出现）/ `conflict_notes`（章纲 vs 事实冲突弥合）/ `opening_directive` / `beat_execution`（五拍逐拍落法）/ `bridge_directives`（仅确实需要时给位置/境界交代写法，LLM 确认规避规则误报——**显式决策：不做纯规则预警**，DBC-02 误报停用是前车之鉴）。注入位置：上章结尾之后、五拍块之前，块内指令优先级高于章纲字面。复用 `prepare_dabai_draft_inputs`（draft_stream 新增）与正文共享同一份上下文，不重复查库。落 `PreWriteWarningRecord`（`result.version=dabai-prewarn-v1`）；重写/门控重跑复用本章最新记录；LLM 失败静默降级回无简报路径。SSE：两入口均发 `pre_warn_running` / `pre_warn_done`（`dabai_mode: true`）。写后 DBC-01 阻断保留兜底。
- **DabaiWrite UI**（2026-06-10 二批）：侧栏分卷折叠（卷头已写/总数、待写/已写筛选、自动展开+滚动定位当前章）；`DabaiInlineProgress` 编辑器内联生成进度（读全局 genQueue 当前章任务 progress，不另起 SSE）；`DabaiDebriefPanel` 复盘/记忆侧栏（一键复盘、图谱同步状态徽章、本章记忆列表）；`DabaiConsistencyBanner` v2 渲染衔接/五拍/钩子分数与修改建议（兼容旧报告）。

## 待完成功能

- [x] **ReaderPromise 深度闭环**（2026-05-21，三层兑现机制已落地）：
  - `services/ai/promise_debrief.py`（新建）：`enrich_with_promise_ids` / `apply_fulfilled_by_ids` / `apply_plan_promise_fulfillment`
  - `auto_debrief` 服务端将 `fulfilled_promise_texts` 解析为精确 ID 列表写入缓存（层①）
  - `chapter_debrief` 按 `fulfilled_promise_ids` 直接按主键标记已兑现（层②）
  - `chapter_debrief` 读取 `OutlineNode.extra.promise_fulfilled` 对 open 承诺做模糊匹配兜底（层③，连通章纲展开时写入的规划信号）
  - 剩余：队列自动复盘同步提交（`apply_source=queue_auto` 尚未完整触发 auto-debrief → chapter-debrief 链路）
- [x] **Location 模型**（已实现：model + schema + router + `location_debrief` 入库复盘服务）
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

## 上帝文件登记册（治理基线，2026-05-27 更新）

| 文件 | 实测行数 | 状态 |
|---|---:|---|
| `apps/client/src/components/Writing/ChapterEditor/index.tsx` | 322 | ✅ 编排壳（≤600）；禁止新增 useState/业务逻辑；见 `.cursor/rules/god-files-chapter-editor.mdc` |
| ~~`apps/frontend/src/pages/ReadingReviewPage.tsx`~~ | ~~1538~~ | ✅ 已拆至 `pages/ReadingReview/`（壳 2 行；最大 useReadingReviewPage 453 行） |
| ~~`apps/client/src/pages/ProjectDetailPage.tsx`~~ | ~~1188~~ | ✅ 已拆至 `pages/ProjectDetail/`（壳 354 行；最大 CoverModal 365 行） |
| ~~`apps/client/src/pages/CluesPage.tsx`~~ | ~~1007~~ | ✅ 已拆至 `pages/Clues/`（壳 443 行；最大 QualityDebtCard 173 行） |
| ~~`apps/backend/app/routers/cover.py`~~ | ~~908~~ | ✅ 已拆为 cover_b64_decode.py（367）+ cover_gateway.py（289）+ 薄壳（284） |
| `apps/backend/app/services/ai/chapter_ingredients.py` | 552 | ⚠️ 软警戒线上方；已拆出 ingredient_types.py（104）+ ingredient_prompt.py（108） |
| `apps/backend/app/services/dabai/lab_ledger.py` | 579 | ⚠️ 软警戒线上方（v2 加入品阶/面板快照逻辑）；禁止继续内联新能力；待拆 panel_snapshot_service.py |
| `apps/backend/app/routers/outline/qa_internal.py` | 878 | 🚫 超硬上限（600）；新逻辑放 `routers/outline/routes_*.py`，禁止在此文件新增 |
| ~~`apps/backend/app/routers/outline/helpers/realm_timeline.py`~~ | ~~728~~ | ✅ 已拆为 realm_whitelist.py（204）+ realm_attribution.py（115）+ 薄壳（369） |
| ~~`apps/backend/app/routers/ai/draft_context.py`~~ | ~~678~~ | ✅ 已拆为 draft_ctx_reader.py（116）+ draft_ctx_promise.py（139）+ 薄壳（363） |
| ~~`apps/backend/app/services/bootstrap/graph.py`~~ | ~~649~~ | ✅ 已拆为 graph_sse.py（79）+ graph_runner.py（160）+ 薄壳（368） |
| `apps/backend/app/services/bootstrap/context_vol_expand.py` | 128 | ✅ 已拆分（context_vol_tier12.py / context_vol_tier345.py）；现壳 128 行 |
| `apps/backend/app/routers/chapters.py` | 157 | ✅ 已拆分（chapter_helpers.py / chapter_version_routes.py）；现 157 行 |
| `apps/backend/app/services/ai/writing_tools.py` | 17 | ✅ 已拆分（writing_pre_warn.py / writing_scene_plan.py / writing_reader_sim.py）；现壳 17 行 |
| `apps/backend/app/services/bootstrap/volume_entity_registry.py` | 740 | 🚫 超硬上限（600）；禁止继续增入；待拆分 |
| `apps/backend/app/services/bootstrap/steps/vol_chapter_plans.py` | 643 | 🚫 超硬上限（600）；禁止继续增入；待拆分 |
| `apps/backend/app/services/ai/context_assembler.py` | 565 | ✅ 已拆 `draft_ctx_bridge.py` + `context_assembler_helpers.py`；禁止再内联 bridge/style 逻辑 |
| `apps/client/src/components/Bootstrap/hooks/useBootstrapStream.ts` | 840 | 🚫 超硬上限（600）；禁止继续增入；优先待拆 |
| `apps/client/src/pages/SettingsPage.tsx` | 710 | 🚫 超硬上限（600）；禁止继续增入；待拆分 |
| `apps/client/src/pages/Outline/NodeDetailPanel.tsx` | 684 | 🚫 超硬上限（600）；禁止继续增入；待拆分 |
| `apps/client/src/pages/RhythmMapPage.tsx` | 678 | 🚫 超硬上限（600）；禁止继续增入；待拆分 |
| `apps/client/src/components/AI/AIPanel.tsx` | 665 | 🚫 超硬上限（600）；禁止继续增入；待拆分 |
| `apps/client/src/components/Outline/OutlineAIPanel.tsx` | 650 | 🚫 超硬上限（600）；禁止继续增入；待拆分 |
| `apps/client/src/components/BookshelfDetail/SectionContent.tsx` | 647 | 🚫 超硬上限（600）；禁止继续增入；待拆分 |
| `apps/client/src/components/Bootstrap/BootstrapTimelineDetail.tsx` | 632 | 🚫 超硬上限（600）；禁止继续增入；待拆分 |
| ~~`apps/client/src/pages/OutlinePage.tsx`~~ | — | ✅ 已迁 `pages/Outline/`（2 行 re-export；子模块均 <600） |
| `apps/backend/app/routers/outline/helpers_core.py` | 180 | ✅ 已大幅瘦身；新路由仍进 `routers/outline/routes_*.py` |
| ~~`apps/client/src/components/Layout/GenerationQueuePanel.tsx`~~ | ~~1890~~ | ✅ 已拆至 `Layout/GenerationQueue/`（壳 2 行；最大 runner 297 行） |
| ~~`apps/client/src/pages/WorldBuildingPage.tsx`~~ | ~~1547~~ | ✅ 已拆至 `pages/WorldBuilding/`（壳 2 行；最大 Tab 321 行） |
| ~~`apps/client/src/pages/CharactersPage.tsx`~~ | ~~1280~~ | ✅ 已拆至 `pages/Characters/`（壳 2 行；最大 CharacterEditor 551 行） |
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
| `apps/backend/app/services/ai/context_builder.py`（794行） | context_builder_continuity.py（266行）+ context_builder_brief.py（313行）+ context_builder_chat.py（236行）；壳 35 行 re-export |
| `apps/backend/app/services/ai/outline_ai.py`（735行） | outline_ai_expand.py（299行）+ outline_ai_quality.py（432行）；壳 18 行组合继承 |
| `apps/backend/app/services/ai/debrief.py`（662行） | debrief_helpers.py（140行）+ debrief_extract.py（505行）；壳 18 行 re-export |
| `apps/backend/app/routers/ai/debrief_routes.py`（864行） | chapter_debrief_route.py（383行）+ auto_debrief_route.py（188行）+ debrief_char_updater.py（321行）+ debrief_chapter_core.py（360行）；壳 18 行聚合 |
| `apps/backend/app/routers/ai/scene_routes.py`（730行） | scene_plan_routes.py（404行）+ scene_draft_routes.py（210行）+ scene_stitch_routes.py（137行）；壳 19 行聚合 |
| `apps/backend/app/routers/cover.py`（908行） | cover_b64_decode.py（367行）+ cover_gateway.py（289行）；壳 284 行 |
| `apps/backend/app/services/ai/chapter_ingredients.py`（895行） | ingredient_types.py（104行）+ ingredient_prompt.py（108行）；壳 552 行 |
| `apps/backend/app/routers/outline/helpers/realm_timeline.py`（728行） | realm_whitelist.py（204行）+ realm_attribution.py（115行）；壳 369 行 re-export |
| `apps/backend/app/routers/ai/draft_context.py`（678行） | draft_ctx_reader.py（116行）+ draft_ctx_promise.py（139行）；壳 363 行 re-export |
| `apps/backend/app/services/bootstrap/graph.py`（649行） | graph_sse.py（79行）+ graph_runner.py（160行）；壳 368 行 re-export |
| `apps/client/src/pages/ProjectDetailPage.tsx`（1188行） | `pages/ProjectDetail/`：CoverSvgUtils（83行）+ CoverModal（365行）+ GenerateJourneyPanel（227行）+ WritingConfigPanel（198行）；壳 354 行 |
| `apps/client/src/pages/CluesPage.tsx`（1007行） | `pages/Clues/`：constants（69行）+ ForeshadowForm（132行）+ ForeshadowCard（123行）+ ChapterIndexCard（116行）+ QualityDebtCard（173行）；壳 443 行 |
| `apps/frontend/src/pages/ReadingReviewPage.tsx`（1538行） | `pages/ReadingReview/`：index 165 + useReadingReviewPage 453 + HistoryReportList 197 + RevisionDrawer 236 + tabs/* + hooks；壳 2 行 re-export |

---

## 前端组件拆分蓝图（待落地）

| 当前文件 | 实测行数 | 目标结构 |
|---|---:|---|
| ~~`apps/client/src/pages/OutlinePage.tsx`~~ | — | ✅ `pages/Outline/`：`index` / `OutlineTreeSidebar` / `NodeDetailPanel` / `tabs/*` / `diffUtils` / modals |
| ~~`apps/client/src/components/Layout/GenerationQueuePanel.tsx`~~ | — | ✅ 已落地 `Layout/GenerationQueue/` |
| ~~`apps/client/src/pages/WorldBuildingPage.tsx`~~ | — | ✅ 已落地 `pages/WorldBuilding/`（见下方蓝图） |
| ~~`apps/frontend/src/pages/ReadingReviewPage.tsx`~~ | — | ✅ 已落地 `pages/ReadingReview/`（HistoryReportList / SnapshotDiffModal / useCoherenceRevision） |
| ~~`apps/client/src/pages/CharactersPage.tsx`~~ | — | ✅ 已落地 `pages/Characters/` |
| ~~`apps/client/src/components/Writing/ChapterEditor/index.tsx`~~ | — | ✅ 已拆：编排壳 322 行 + `hooks/*` + `TopToolbar` / `EditorMainArea` / `ContextSidePanel` 等 |

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

8. **PR 自检 / Agent 生成**：**任意**新建或交付的 `.py`/`.ts`/`.tsx` 业务文件必须 **≤600 行**（目标 ≤400）；提交前 `wc -l <file>`；超硬上限**先拆再合**。Cursor 全局规则：`.cursor/rules/file-size-600-global.mdc`（`alwaysApply`）。新建 step / capability / sub-router 必须落到蓝图指定路径，禁止写进登记册中的上帝文件。

---

## 本地启动命令

```bash
# 环境与依赖（根目录）
bash bootstrap.sh

# Docker 一键启动（含 backend + client + frontend 管理端）
docker-compose up -d

# 本地裸跑：后端 + 创作端（pnpm；端口见 env.local.ports.example）
# ./restart.sh 会在启 uvicorn 前自动执行 create_all + alembic upgrade head（同步 alembic_version）
./restart.sh

# 仅同步数据库（不启服务）
# cd apps/backend && python -m app.cli.db_upgrade

# 管理后台（另开终端，默认 http://localhost:3174）
cd apps/frontend && pnpm run dev

# 仅手动启后端
cd apps/backend && source .venv/bin/activate && uvicorn app.main:app --reload --port 9000

# 仅手动启创作端
cd apps/client && pnpm run dev

# embedding 存量补跑（换模型 / 新部署后执行）
cd apps/backend && python verify_pgvector.py --reembed
```
