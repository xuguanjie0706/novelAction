# Novel System — 项目记忆 (CLAUDE.md)

> 这个文件是给 AI 助手（Claude）读的上下文锚点。  
> 每次重要决策、架构变更、未完成事项都记录在这里，避免重复推导。

---

## 项目概述

**目标**：一个以 AI 生成为核心的网络小说创作系统。人工不负责填写设定，所有世界观、势力、境界、人物、大纲均由 AI 从一句话创意全量生成。  
**核心特性**：输入一句话创意，AI 全量生成结构化设定（境界体系、势力档案、故事线、人物、技能、道具）并存入对应数据表；后续章节写作、质检、记忆管理也全部由 AI 驱动，人工只做审阅和微调。

> ⚠️ **设计原则**：系统是 AI 生成系统，不是辅助填写工具。所有新功能的出发点是"AI 能生成/校验/推进什么"，而非"给用户提供什么表单"。

> ⚠️ **持久化优先（新增硬规则）**：从本条起，后续新增的业务内容（状态、产物、流程中间结果、AI 结构化输出）默认必须优先做数据库持久化存储（PostgreSQL）；禁止仅停留在前端内存、进程内变量或临时缓存。仅当存在明确性能或安全原因且已在文档中记录权衡时，才允许非持久化方案作为例外。

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

### 关键决策：统一用 OpenAI 兼容协议

**原因**：不绑定任何 SDK；远程改管理后台或 `.env` 的 `GEMINI_*`；本地改 `.env` 的 `LLM_*` + `AI_MODEL`。

```env
# 仅在使用「本地」线路时需要配置 AI_MODEL
LLM_BASE_URL=http://localhost:11434/v1
LLM_API_KEY=ollama
# AI_MODEL=你的本地模型 id

# 可选：无 DB 时的远程兜底（OpenAI 兼容层）
# GEMINI_BASE_URL=https://...
# GEMINI_API_KEY=...
# GEMINI_MODEL=...
```

### 本地线路与短上下文（`model_profile=local`）

- 小上下文时单次 prompt 需控制长度；`_parse_json()` 做容错（去 markdown fence、strip、部分网关夹带的 think 标签）
- 若某兼容网关对 `thinking` 类参数报错，可在调用层按需加 `extra_body` 关闭（视网关文档）

### Gemini 迁移时的变化

- Gemini 支持 100 万 token context，可以切换到**方案 B（单次全量生成）**
- `generation_service.py` 里 `mode="single_shot"` 已预留，切换只需改前端请求参数

### 任务级采样配置（v3，2026-05）

> 设计动机：此前 `_call_ai` / `_stream_ai` 全程不传 `temperature`，质检（要稳定 JSON）和写正文（要文采变化）共用一个默认温度，是 AI 味的系统性根因。

- 配置文件：`apps/backend/app/services/llm_task_profiles.py`
- 调用方约定：每次 `_call_ai` / `_stream_ai` 传 `task="<域>.<动作>"`（如 `quality.check`、`draft.opening`）；未识别走网关默认（向后兼容）。
- 关键档位：

| 任务域 | temperature | 说明 |
|---|---|---|
| `quality.*` / `debrief.*` | 0.2-0.3 | 要稳定 JSON 与可比较打分 |
| `bootstrap.*` / `outline.*` | 0.55-0.75 | 半结构化生成 |
| `draft.chapter` | 0.9 | 章节正文，加 frequency/presence_penalty 抑制重复 |
| `draft.opening` / `draft.climax` | 0.95 | 开局期 / 高潮期允许更跳脱 |
| `draft.dark_hour` | 0.75 | 至暗期需克制 |

- 自定义覆写：调用方可传 `sampling={"temperature": 0.85}` 临时覆盖（A/B 测试用）。
- 阶段→任务名映射：`phase_to_draft_task(phase)` 在 `draft_assist_stream` 内部按 `OutlineNode.phase` 自动选档。

---

## 数据模型速查

```
Project
  ├── WorldSetting（设定卡，有 category）
  ├── Character + CharacterRelationship（人物 + 关系）
  ├── OutlineNode（树形：volume → arc → chapter_plan）
  ├── Chapter + ChapterVersion
  ├── MemoryChunk（长篇记忆，后续接 pgvector embedding）
  ├── StoryLine（故事线：主线/支线/感情线/成长线/势力线...）
  ├── PowerSystem（境界/力量体系，含结构化 levels 数组）
  ├── Skill（功法/技能，关联 PowerSystem，记录掌握者）
  ├── Item（道具/法宝，含稀有度、持有历史）
  ├── Faction（势力/宗门/国家，支持父子层级）
  ├── Foreshadow（伏笔台账）
  ├── QualityDebt（质检欠债记录）
  ├── Scene（章节分场，三层调度核心；表已建，router 待实现）
  └── ReaderPromise（读者承诺台账；表已建，router 待实现）
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
- `location_id`（ForeignKey `locations.id`）已**注释预留**，待 Location 模型（P2-W7）实现后启用；当前用 `location_name` 文本字段
- **当前状态**：模型 + migration 已就位，router 待实现

### ReaderPromise 模型（v3，2026-05）

读者承诺台账，记录章末/卷末预告、名字暗示、章评共识等对读者的显式或隐式承诺。
- 关键字段：`promise_type`（chapter_ending / volume_ending / name_implication / ...）、`expected_chapter_window`、`status`（open / fulfilled / broken）、`priority`（1-5）、`audience_aware`（0-5）
- 写章时 prompt 注入"本章必须/可以兑现的承诺"；复盘自动检测新承诺并标记回收
- **当前状态**：模型 + migration 已就位，router 待实现

### Project.extra（v3，2026-05）
JSON 杂物字段，当前已知键：
- `extra.positioning`：Step 0 立项会议产物（`target_audience` / `tropes` / `reference_works` /
  `selling_point` / `face_slap_pattern` / `emotional_arc` / `pace_type` / `taboo_lines`）。
  写章节路径优先读 `Project.extra.positioning`，回退 `Project.story_core.positioning`。

---

## API 路由约定

| 前缀 | 说明 |
|------|------|
| `GET/POST /api/v1/projects/` | 项目 CRUD |
| `/api/v1/projects/{pid}/settings/` | 世界观设定 |
| `/api/v1/projects/{pid}/characters/` | 人物 |
| `/api/v1/projects/{pid}/outline/` | 大纲树 |
| `/api/v1/projects/{pid}/chapters/` | 章节 |
| `/api/v1/projects/{pid}/ai/` | 质检/建议/记忆提取 |
| `/api/v1/projects/{pid}/storylines/` | 故事线 CRUD |
| `/api/v1/projects/{pid}/power-systems/` | 境界体系 CRUD |
| `/api/v1/projects/{pid}/skills/` | 功法技能 CRUD |
| `/api/v1/projects/{pid}/items/` | 道具法宝 CRUD |
| `/api/v1/projects/{pid}/factions/` | 势力组织 CRUD |
| `POST /api/v1/bootstrap/stream` | **一句话→全量生成（SSE）** |

---

## 一句话生成（Bootstrap）双方案

### 方案 A：串行步进（Sequential）— 默认

```
logline
  → [Step0  立项会议]          # _gen_positioning：受众/爽点/打脸节奏/卖点
  → [Step1  项目]              # _gen_project，把定位写进 Project.extra.positioning
  → [Step2  境界体系]
  → [Step3  势力]
  → [Step4  故事线]
  → [Step5  人物]
  → [Step6  技能]
  → [Step7  道具]
  → [Step8  设定卡]
  → [Step9  卷骨架]            # _gen_volumes 同时填 phase
  → [Step10 记忆]
  → [Step11 关系]
  → [Step12 开局追读承诺清单]  # _gen_opening_contract：写 Project.extra + ReaderPromise 种子
  → [Step12.5 第一卷章级大纲] # _gen_vol1_chapter_plans：生成 chapter_plan OutlineNode
  → [Step13 第1章场景蓝图]    # _gen_ch1_scenes：生成 Scene records
  → [Step14 全局一致性扫描]   # _gen_consistency_scan，结果写 Project.extra.consistency_issues
```

- 每步独立 prompt，上下文逐步累积（压缩摘要 + 立项定位传入）
- 单步失败重试 1 次，不影响其他步骤
- SSE 每步推送 `step_start` / `step_done` / `error`
- **Step 0 是新增的"立项会议"**：从一句话推导目标读者画像、爽点类型、打脸频率、情感线占比、节奏类型，作为后续各步的全局约束注入到所有 prompt。这是网文系统区别于"AI 自由发挥"的关键防线。
- **Step 12** 为开局前十章生成追读承诺：保留 `Project.extra.opening_contract`，并写入 `ReaderPromise` 种子供写章查询。
- **Step 12.5 + Step 13** 把设定落成可执行写作计划：先生成第一卷章节级 `chapter_plan`，再生成第1章场景级 `Scene` 蓝图。
- **Step 14** 交叉核验所有生成物的关键字段，矛盾列表写入 `Project.extra.consistency_issues`，供前端展示"X 处需确认项"。

### 方案 B：单次全量（Single-shot）— 适合大 context 模型（Gemini）

```
logline → 1次 AI 调用 → 完整 JSON（含项目+设定+人物+大纲+记忆）
```

- 速度快，前后一致性最佳
- 要求模型 context ≥ 32k，输出 token ≥ 4096

### 切换方式

前端请求 `POST /api/v1/bootstrap/stream` 时传 `mode` 参数：
```json
{ "logline": "...", "mode": "sequential" }   // 串行，适合生成更多的内容
{ "logline": "...", "mode": "single_shot" }  // 单次全量，适合大上下文远程模型
```

### Bootstrap 步骤映射表（防漂移）

| 文档步骤 | SSE `step` | 后端函数 |
|---|---|---|
| Step 0 立项会议 | `positioning` | `_gen_positioning` |
| Step 1 项目 | `project` | `_gen_project` |
| Step 2 境界体系 | `power_systems` | `_gen_power_systems` |
| Step 3 势力 | `factions` | `_gen_factions` |
| Step 4 故事线 | `storylines` | `_gen_storylines` |
| Step 5 人物 | `characters` | `_gen_characters` |
| Step 6 技能 | `skills` | `_gen_key_skills` |
| Step 7 道具 | `items` | `_gen_key_items` |
| Step 8 设定卡 | `settings` | `_gen_settings` |
| Step 9 卷骨架 | `volumes` | `_gen_volumes` |
| Step 10 记忆 | `memory` | `_gen_memory` |
| Step 11 关系 | `relations` | `_gen_relations` |
| Step 12 开局承诺 | `opening_contract` | `_gen_opening_contract` |
| Step 12.5 第一卷章纲 | `vol1_chapters` | `_gen_vol1_chapter_plans` |
| Step 13 第1章场景 | `ch1_scenes` | `_gen_ch1_scenes` |
| Step 14 一致性扫描 | `consistency` | `_gen_consistency_scan` |

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
| **题材定位** | `Project.extra.positioning` | **Step 0 `_gen_positioning`（v3）** |
| 境界体系 | `PowerSystem` + `levels[]` | Step 2 `_gen_power_systems` |
| 势力组织 | `Faction`（含 `extra.active_period`） | Step 3 `_gen_factions` |
| 故事线 | `StoryLine` | Step 4 `_gen_storylines` |
| 人物 | `Character` | Step 5 `_gen_characters` |
| 核心技能/功法 | `Skill` | Step 6 `_gen_key_skills` |
| 关键道具/法宝 | `Item` | Step 7 `_gen_key_items` |
| 纯叙事设定 | `WorldSetting`（分类存 `extra.category`） | Step 8 `_gen_settings` |
| 卷级大纲 + phase | `OutlineNode`（volume） + `phase` | Step 9 `_gen_volumes` |
| 记忆种子 | `MemoryChunk` | Step 10 `_gen_memory` |
| 人物关系 | `CharacterRelationship` | Step 11 `_gen_relations` |
| 开局追读承诺 | `Project.extra.opening_contract` + `ReaderPromise` | Step 12 `_gen_opening_contract` |
| 第一卷章节蓝图 | `OutlineNode`（chapter_plan） | Step 12.5 `_gen_vol1_chapter_plans` |
| 第1章场景蓝图 | `Scene` | Step 13 `_gen_ch1_scenes` |
| 一致性矛盾列表 | `Project.extra.consistency_issues` | Step 14 `_gen_consistency_scan` |

`WorldSetting` 只存**无专属结构化表的纯叙事内容**：作品立意、世界底层规则、历史谜团、地理格局、文化风俗。不再用文字卡存境界体系或势力描述（这些有专属表）。

## 已完成功能

- [x] 项目 CRUD
- [x] 世界观设定 CRUD（分类体系：世界背景/地理场景/历史传说/文化风俗/规则法则）
- [x] 人物 + 关系 CRUD
- [x] 大纲树（层级编辑）
- [x] 章节写作（TipTap + 自动保存 + 版本快照）
- [x] AI 质检（JSON 评分报告）
- [x] AI 流式建议（SSE）
- [x] 记忆提取
- [x] 一句话生成（方案A串行 + 方案B单次）
- [x] 故事线/境界体系/技能/道具/势力前端 UI（WorldBuildingPage 五标签页）
- [x] Bootstrap 生成时结构化生成势力（Faction）、核心技能（Skill）、关键道具（Item）
- [x] Bootstrap Step 12：开局追读承诺清单（`_gen_opening_contract`，写 `Project.extra` + `ReaderPromise` 种子）
- [x] Bootstrap Step 12.5：第一卷章级大纲（`_gen_vol1_chapter_plans`，生成 `chapter_plan`）
- [x] Bootstrap Step 13：第1章场景蓝图（`_gen_ch1_scenes`，生成 `Scene` records）
- [x] Bootstrap Step 14：全局一致性扫描（`_gen_consistency_scan`，结果存 `Project.extra.consistency_issues`）
- [x] 伏笔台账（`Foreshadow` 模型 + router）
- [x] 质检欠债记录（`QualityDebt` 模型 + router）
- [x] 封面图生成日志（`CoverImageCallLog` 模型 + router）
- [x] Scene / ReaderPromise 模型 + router + Alembic migration
- [x] 任务级采样配置（`llm_task_profiles.py`，quality/draft/bootstrap 分档温度）
- [x] **Bootstrap 流派分流增强（2026-05-06）**：`_get_genre_kit_block` 注入 `_gen_characters`、` _gen_settings`、` _gen_storylines`、` _gen_power_systems`、` _gen_factions`、` _gen_key_skills`、` _gen_key_items` 七个步骤；前端角色页支持 `speech_kit` 结构化展示（标志性词语、样本台词、内心独白等）；大纲章节节点支持 POV + 戏份预算（`character_screen_time`、`pov_character_id`）展示与编辑。

## 待完成功能

- [ ] Scene 三层调度全链路（章纲 → 分场 → 逐场正文 → stitch）
- [ ] ReaderPromise 深度闭环（写章时承诺注入 + 复盘自动检测回收）
- [ ] Location 模型（当前 Scene.location_name 文本字段，location_id 已注释预留，P2-W7）
- [ ] 人物关系图可视化（ReactFlow）
- [ ] pgvector 语义记忆检索（`MemoryChunk.embedding` 字段已预留）
- [ ] 导出 TXT / EPUB
- [ ] 登录鉴权（目前无 auth）
- [ ] AI 质检时结合故事线进度与境界体系做一致性检查
- [ ] Bootstrap 生成的技能/道具 mastered_by 字段关联真实 character UUID（目前只存名字）
- [ ] 读者模拟器与主写章流程打通（低分项自动转 next_chapter_directives）
- [ ] 伏笔台账升级：type / min_max_distance / paid_off_quality / volume_budget + audit 接口

---

## 代码结构红线（架构级硬约束，2026-05 新增）

> 设计动机：本仓库已经出现「上帝文件」（`generation_service.py` 3149 行 / `ai_service.py` 2895 行 / `routers/outline.py` 3825 行 / `ChapterEditor.tsx` 2960 行）。它们不是被一次写出来的，而是**没有显式上限**导致的路径依赖膨胀。本节给出硬性红线 —— 触线时**必须先拆分再加新功能**，禁止「再加一段就好」式增量恶化。

### 规模上限（硬指标）

| 对象 | 软警戒线 | 硬上限（PR 不予合入） |
|------|---------:|----------------------:|
| 单文件 LOC（含注释；`.py` / `.ts` / `.tsx`） | 400 | **600** |
| 单函数 / 单 React 组件 LOC | 80 | **150** |
| 单类公共方法数 | 10 | **15** |
| 单文件 `useState` / `useEffect` 总数（前端） | 20 | **40** |
| 单 Prompt 字符串字面量行数 | 30 | **60**（超出抽到 `prompts/*.py`） |

**触线处置**：超软警戒线必须在 PR 描述里说明计划；**超硬上限**的文件，PR 必须**同步包含拆分提交**（即「治旧」与「加新」同一 PR），否则评审一律退回。例外只允许两类：自动生成代码（schema、migration）、第三方供应文件。

### 反 God-Object 原则

- **Service 类按业务能力切包**，不按横切关注点切包。`AIService` 那种「只要共用 `_call_ai` 就什么都塞」的写法**禁止再新增方法**，新方法走 `services/ai/<capability>.py` 的 mixin / 自由函数路径（见下「拆分蓝图」）。
- **路由文件按资源动词切包**，不按「同一前缀」无限堆。`routers/outline.py` 已达 3825 行，禁止新增 endpoint；新功能放 `routers/outline/<sub_resource>.py` 子模块。
- **React 组件 ≤ 400 行**；超过 1500 行的 `*Page.tsx` 必须先拆 `hooks/` + 子组件再迭代。

### 编排薄壳模式（Orchestration Shell）

对**多步骤流程类**（Bootstrap、章节起草、复盘、读者模拟），强制采用「**编排薄壳 + 步骤独立模块 + Prompt/Parse/Save 分层**」：

- **薄壳层**：`service.py` 只负责 SSE 事件循环、步骤分发、整体 try/except。不写业务 prompt、不写 DB 落库。
- **步骤层**：每个步骤一个文件（如 `steps/positioning.py`），导出 `async def gen_xxx(ai, db, project, ctx) -> ...`。文件内拆 `_build_prompt` / `_persist` 两个私有函数。
- **Prompt 层**：长 prompt（≥ 30 行字面量）抽到 `prompts/*.py`；带 ctx 插值的用 f-string 函数封装。
- **Parse 层**：JSON 解析统一走 `parse.py`（如 `_parse_json` / `_coerce_*` / `_safe_int`），禁止在 step 文件内现写 try/except。

新增步骤 = 新增一个 step 文件 + 薄壳里加一段 yield，**结构上不可能让薄壳回到 3000 行**。

---

## Service / Router 拆分蓝图（落地清单）

> 以下是目前已规划但**尚未落地**的拆分。新写代码前先看这里：若新功能属于以下任一模块，请直接放到拆分后的目标位置，**不要往旧的上帝文件里塞**。

### `services/generation_service.py` → `services/bootstrap/` 包

```
services/bootstrap/
├── __init__.py          # re-export GenerationService（保持外部 import 兼容）
├── service.py           # class GenerationService：仅 __init__ / bootstrap / _sequential / _single_shot
├── context.py           # hydrate_ctx_from_project / _get_genre_kit_block
├── sse.py               # _sse / step_start / step_done helpers
├── parse.py             # _parse_json / _safe_int / _coerce_power_system_rank
├── retry.py             # _call_with_retry
├── prompts/
│   ├── single_shot.py   # _single_shot_prompt
│   ├── blueprints.py    # _setting_blueprints_for_prompt + _setting_extra_with_defaults
│   └── word_budget.py   # _book_length_constraints_for_prompt
├── steps/               # 每个 Bootstrap step 一个文件（≤ 300 行）
│   ├── positioning.py            # Step 0
│   ├── project.py                # Step 1
│   ├── power_systems.py          # Step 2
│   ├── factions.py               # Step 3
│   ├── storylines.py             # Step 4
│   ├── characters.py             # Step 5
│   ├── skills.py                 # Step 6
│   ├── items.py                  # Step 7
│   ├── settings.py               # Step 8（含 _gen_settings_append）
│   ├── volumes.py                # Step 9
│   ├── memory.py                 # Step 10
│   ├── relations.py              # Step 11
│   ├── opening_contract.py       # Step 12
│   ├── vol1_chapter_plans.py     # Step 12.5
│   ├── ch1_scenes.py             # Step 13
│   └── consistency_scan.py       # Step 14
├── save_all.py          # _save_all（single_shot 大写库）
└── completion.py        # _complete_single_shot_data / _complete_missing_*
```

**约束**：拆分完成前，**禁止**在 `generation_service.py` 新增 `_gen_*` 方法或新 Step；新需求直接落到目标 `steps/*.py`，并以 thin re-export 的方式被旧文件引用。

### `services/ai_service.py` → `services/ai/` 包

按业务能力切，`class AIService` 用 mixin 拼装：

```
services/ai/
├── __init__.py          # re-export AIService
├── client.py            # _get_client / _clip_context / _large_context_enabled / _plain_text
├── sampling.py          # _is_retryable_llm_error / _build_sampling_kwargs / _call_ai / _stream_ai
├── quality.py           # quality_check / quality_debt_micro_patch
├── coherence.py         # chapter_coherence_check / apply_coherence_revisions
├── drafting.py          # draft_assist_stream / pre_write_warning / scene_plan
├── chat.py              # suggest_stream / chat_stream
├── outline.py           # expand_outline / outline_quality_check / outline_repair_plan / plan_full_structure
├── debrief.py           # auto_extract_debrief
├── reader_sim.py        # reader_psychology_sim
├── memory.py            # extract_memory
└── service.py           # class AIService(ClientMixin, SamplingMixin, QualityMixin, ...)
```

**约束**：拆分完成前，**禁止**在 `AIService` 新增公共方法；新 AI 能力走 `services/ai/<capability>.py` 的自由函数 + 同名 mixin。

### `routers/outline.py` → `routers/outline/` 包

按子资源切，主 `__init__.py` 聚合 `router`：

```
routers/outline/
├── __init__.py          # APIRouter 聚合 + include_router 各子模块
├── tree.py              # GET/POST/PATCH/DELETE 大纲树基本 CRUD
├── quality.py           # outline_quality_check / outline_repair_plan
├── embedding_dup.py     # compute_outline_chapter_vectors / analyze_outline_embedding_duplicates
├── power_curve.py       # _detect_outline_power_curve_issues + 路由
├── death_continuity.py  # _detect_outline_character_death_continuity + 路由
├── theme_align.py       # _detect_outline_theme_alignment_issues + 路由
├── foreshadow.py        # _detect_outline_foreshadow_issues + 路由
├── revision.py          # _create_outline_revision / _create_quality_revision
├── ai_expand.py         # POST /ai-expand 及 commit
└── ws.py                # outline_workflow_websocket
```

**约束**：拆分完成前，禁止在 `routers/outline.py` 新增 endpoint。

### 前端组件拆分蓝图

| 当前文件 | 行数 | 目标结构 |
|---|---:|---|
| `apps/client/src/components/Writing/ChapterEditor.tsx` | 2960 | `Writing/ChapterEditor/` 包：`index.tsx` 主壳 + `TopToolBar.tsx` + `DebriefPanel.tsx` + `PlanCard.tsx` + `CharacterMiniCard.tsx` + `hooks/{useChapterAutosave,usePreWriteWarning,useDebriefRun}.ts` + `utils.ts` |
| `apps/client/src/pages/OutlinePage.tsx` | 2099 | `pages/Outline/` 包：树视图 / AI 扩展面板 / 质检面板 / Diff 视图分文件 |
| `apps/client/src/components/Layout/GenerationQueuePanel.tsx` | 1789 | 拆 `QueueList` / `QueueItemDetail` / `useGenerationQueue` |
| `apps/frontend/src/pages/ReadingReviewPage.tsx` | 1538 | 拆 `ReviewList` / `SnapshotDiff` / `useReviewSubmit` |

**约束**：上述四个文件**冻结新增功能**；新需求必须先开拆分 PR。

---

## 上帝文件登记册（治理基线，2026-05-12 更新）

| 文件 | 当前行数 | 状态 |
|---|---:|---|
| `apps/backend/app/routers/outline/helpers_core.py` | 2166 | 🚫 冻结新增 endpoint；新路由进 `routers/outline/routes_*.py`，helpers_core 仅作为待继续瘦身的过渡集合 |
| `apps/client/src/components/Writing/ChapterEditor.tsx` | 2960 | 🚫 冻结新增 props/`useState`，新功能走 hooks + 子组件 |
| `apps/client/src/pages/OutlinePage.tsx` | 2099 | 🚫 冻结新增功能 |
| `apps/client/src/components/Layout/GenerationQueuePanel.tsx` | 1789 | ⚠️ 警告区，下一次重大改动同步拆分 |
| `apps/frontend/src/pages/ReadingReviewPage.tsx` | 1538 | ⚠️ 警告区 |

### 已退役（2026-05-12 拆分完成）

| 旧上帝文件 | 拆分去向 | 当前残留 |
|---|---|---:|
| `apps/backend/app/routers/outline.py` | `apps/backend/app/routers/outline/`（`routes_tree` / `routes_ai_expand` / `routes_quality` / `routes_full_generate` / `routes_workflow_ws` / `helpers_core` / `qa_internal` / `schemas`） | 已删除 |
| `apps/backend/app/services/generation_service.py` | `apps/backend/app/services/bootstrap/`（`steps/*` + `context` / `retry` / `save_all` / `completion`） | 500 行（瘦身后的编排壳，允许继续存在） |
| `apps/backend/app/services/ai_service.py` | `apps/backend/app/services/ai/`（`chat` / `quality` / `debrief` / `draft_stream` / `outline_ai` / `memory_ai` / `coherence` / `guardrails` / `sampling` / `writing_tools` / `client` / `service`） | 10 行（仅作兼容 re-export） |

> 任何一次让上表文件**增加 ≥ 50 行**的 PR 都必须同时包含等量或更多的「治旧」删除量；否则视为破坏红线。

---

## 代码文档与注释契约（架构级）

本节约束 **人机协作与长期演进**：注释不是为了「行数好看」，而是为了让 **公共 API、业务不变量、失败形态与边界** 在一屏内可被读懂；后续在本仓库改 **TypeScript/JavaScript** 时，以 **严格 JSDoc** 为默认交付标准。

### 原则

- **公共表面优先**：凡 `export` 的函数、类、hook、跨模块复用的类型辅助，必须具备可被 IDE 悬停展示的说明；私有实现若含非显而易见的算法或协议约束，在关键分支处补 **局部块注释**。
- **意图优于复述**：不写「把 x 赋给 y」式废话；写 **为什么这样做**、**与哪条产品/架构决策对齐**、**违反时会怎样**。
- **类型与文档分工**：TypeScript 类型表达「是什么」；JSDoc 补充 **业务语义、前置条件、副作用、与后端契约**（字段含义若与名称不完全一致，必须在 `@param` / 字段旁说明）。
- **中英**：面向维护者与 AI 的注释以 **简体中文** 为主；已与对外 API/协议锁定的英文专有名词保持原文。

### TypeScript / JavaScript（`apps/client`、`apps/frontend`）

| 对象 | 最低要求 |
|------|----------|
| 模块 | 文件职责复杂或入口非自解释时，使用 `@file` / 顶部块说明 **职责与禁止事项**。 |
| `export function` / `export const` 工厂 | 完整 JSDoc：`@param`、`@returns`；异步函数说明 rejection 场景或统一错误形态。 |
| React 组件（命名导出） | 说明 **数据来源**（store / props / URL）、**关键副作用**（订阅、阻塞导航）；props 非直观时逐项 `@param`。 |
| 自定义 Hook | 说明 **依赖**（哪些参数变化会触发重新请求）、**返回值契约**。 |
| 复杂对象形态 | 使用 `@typedef` 或与 Zod/schema 同处的注释，标明 **不变量**（例如「永远与 project 维度同源」）。 |

**推荐标签集合**（按需选用，避免堆砌）：`@param`、`@returns`、`@throws`、`@deprecated`、`@internal`（package 内边界）、`@example`（仅非平凡调用）、`@see`（指向规格或 OpenAPI）。

**反面模式**：整文件无注释但大量魔法字符串；仅英文拼音缩写无释义；注释与实现漂移（改代码必改注释）。

### Python（`apps/backend`）

- **路由 handler、service 公共方法、复杂纯函数**：使用 **Google 风格 docstring**（`Args` / `Returns` / `Raises`）；与 TS 侧同一语义的概念用词保持一致，便于对读。
- **AI 路由**：实现位于 `apps/backend/app/routers/ai/` 包；新端点在同一子模块内保持 **模块顶注释说明资源边界**。

### 验收心智（给审查者与 Agent）

新 PR / 新文件：公共 `export` 是否补齐 JSDoc；是否说明了 **错误与空状态** 的意图；是否在架构接缝（API、store、路由）有据可查的一句话 **设计动机**。

---

---

## 开发建议（给未来的 Claude）

0. **动手前先读「代码结构红线」与「上帝文件登记册」**：若改动文件已在登记册，**禁止**直接在原文件里加新功能；先按「拆分蓝图」的目标结构落新代码，再考虑老文件的迁移节奏。
1. **改 AI 调用**：动 `apps/backend/app/services/ai_service.py` 时**只允许修改/重构现有方法**，新增能力一律按蓝图放 `services/ai/<capability>.py`；router 层永远不直连 openai
2. **加新数据表**：在 `apps/backend/app/models/` 新建文件 → `models/__init__.py` 导出 → `schemas/` 对应 → `routers/` 路由 → `main.py` 注册
3. **Prompt 优化**：prompt 字符串统一放在 service 层；超 30 行抽到 `*/prompts/*.py`；需要 JSON 时在提示词末尾强调「只返回 JSON」
4. **JSON 解析**：所有 `_call_ai` 的 JSON 解析用 `_parse_json()` 统一处理，不要 try/except 分散在各处
5. **pgvector**：embedding 字段已在 `MemoryChunk` 预留，启用时需 `CREATE EXTENSION vector;` 并取消 `memory.py` 中的条件导入
6. **改创作端 UI**：主要改 `apps/client/`；**管理后台**改 `apps/frontend/`（与 client 独立依赖与构建）
7. **TS/JS 注释**：新增或修改公共 `export` 时，遵循上文「代码文档与注释契约」，使用 **严格 JSDoc**；后端对应模块用 Google 风格 docstring。
8. **PR 自检**：提交前对触线文件执行 `wc -l <file>`，超硬上限必须**先拆再合**；新建 step / capability / sub-router 必须落到拆分蓝图指定路径。

---

## 本地启动命令

```bash
# 环境与依赖（根目录）
bash bootstrap.sh

# Docker 一键启动（含 backend + client + frontend 管理端）
docker-compose up -d

# 本地裸跑：后端 + 创作端 + 管理后台（pnpm；端口见 env.local.ports.example）
./restart.sh

# 仅手动启后端
cd apps/backend && source .venv/bin/activate && uvicorn app.main:app --reload --port 9000

# 仅手动启创作端
cd apps/client && pnpm run dev

# 仅手动启管理后台（默认 http://localhost:3174）
cd apps/frontend && pnpm run dev
```
