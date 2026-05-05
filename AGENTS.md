# Novel System — 项目记忆 (AGENTS.md)

> 这个文件是给 AI 助手（Codex）读的上下文锚点。  
> 每次重要决策、架构变更、未完成事项都记录在这里，避免重复推导。

---

## 项目概述


**目标**：一个以 AI 生成为核心的网络小说创作系统。人工不负责填写设定，所有世界观、势力、境界、人物、大纲均由 AI 从一句话创意全量生成。  
**核心特性**：输入一句话创意，AI 全量生成结构化设定（境界体系、势力档案、故事线、人物、技能、道具）并存入对应数据表；后续章节写作、质检、记忆管理也全部由 AI 驱动，人工只做审阅和微调。

> ⚠️ **设计原则**：系统是 AI 生成系统，不是辅助填写工具。所有新功能的出发点是"AI 能生成/校验/推进什么"，而非"给用户提供什么表单"。

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
| 远程 · 某条提供者 | 管理后台 `llm_providers`（请求带 `llm_provider_id`） |
| 远程 · 环境变量 | `GEMINI_BASE_URL` + `GEMINI_MODEL`（无 DB 行时） |
| 本地 | `apps/backend/.env` 的 `LLM_BASE_URL` + `LLM_API_KEY` + **`AI_MODEL`（必填）** |

### 关键决策：统一用 OpenAI 兼容协议

**原因**：不绑定任何 SDK；远程由管理后台或 `GEMINI_*`；本地由 `LLM_*` + `AI_MODEL`。

```env
# 仅在使用「本地」线路时需要配置 AI_MODEL
LLM_BASE_URL=http://localhost:11434/v1
LLM_API_KEY=ollama
# AI_MODEL=你的本地模型 id

# 可选：无 DB 时的远程兜底
# GEMINI_BASE_URL=https://...
# GEMINI_API_KEY=...
# GEMINI_MODEL=...
```

### 本地线路与短上下文（`model_profile=local`）

- 小上下文时控制单次 prompt 长度；`_parse_json()` 做容错（fence、strip、部分网关夹带的 think 标签）
- 若某网关对 `thinking` 类参数报错，可按网关文档在调用层用 `extra_body` 关闭

### Gemini 迁移时的变化

- Gemini 支持 100 万 token context，可以切换到**方案 B（单次全量生成）**
- `generation_service.py` 里 `mode="single_shot"` 已预留，切换只需改前端请求参数

### Gemini 章节写作与质检核心流程

当前正文生成、单章质检、多章连贯性检测都按 **model_profile** 分流：

- `local/default`：短上下文策略，严格裁剪 prompt，避免本地模型 context 溢出。
- `gemini`：启用长上下文策略，不优先考虑 token 节省，而优先保证故事事实、人物状态、伏笔和章节承接完整。

核心链路如下：

```
章节写作请求
  → apps/backend/app/routers/ai/ 聚合项目事实
  → AIService.draft_assist_stream 组装长上下文 prompt
  → Gemini 流式生成正文 + 章节速查索引
  → 写完后 chapter-debrief / auto-extract 产出记忆与章节索引
  → 下一章生成与质检继续读取这些事实
```

生成正文时，Gemini 分支会尽量传入：

- 作品基本面：`Project.premise`
- 本章大纲：开篇钩子、核心事件、人物变化、章末方向、实力里程碑、情感基调、伏笔要求
- 世界观设定：更多 `WorldSetting` 完整内容
- 人物事实：境界、位置、状态、技能、道具、价值观、恐惧、秘密等
- 故事线：planned / active / climax 的故事线与关键节拍
- 近期记忆：更多 `MemoryChunk`
- 上一章尾部：Gemini 读取更长的前章结尾用于情绪和因果衔接
- 连续性账本：人物状态、力量体系、最近章节、未解决承接点、禁止事项
- 章节速查索引：最近章节核心事件、章末钩子、未回收伏笔

质检分两层：

- **单章质检** `/quality-check`：Gemini 读取完整正文，结合连续性账本、章节索引、人物状态、故事线和力量体系，重点查境界/技能/位置/状态/信息来源是否矛盾。
- **多章连贯性检测** `/chapter-coherence-check`：Gemini 读取所选章节更完整正文，并额外读取项目事实、世界观、人物状态、故事线、章节索引和记忆库，用来检查标题兑现、跨章因果、时间线、人物状态突变和伏笔承接。

重要原则：**Gemini 路径不要回退到“小模型省 token”思路。** 如果连贯性差，优先检查是否漏传了结构化事实（章节索引、复盘记忆、人物状态、故事线节拍、伏笔表），而不是继续缩短 prompt。

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
  └── Faction（势力/宗门/国家，支持父子层级）
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

### 方案 A：串行步进（Sequential）— 默认，适合

```
logline → [Step1 项目] → [Step2 设定] → [Step3 人物] → [Step4 大纲] → [Step5 记忆] → [Step6 关系]
```

- 每步独立 prompt，上下文逐步累积（压缩摘要传入）
- 单步失败重试 1 次，不影响其他步骤
- SSE 每步推送 `step_start` / `step_done` / `error`

### 方案 B：单次全量（Single-shot）— 适合大 context 模型（Gemini）

```
logline → 1次 AI 调用 → 完整 JSON（含项目+设定+人物+大纲+记忆）
```

- 速度快，前后一致性最佳
- 要求模型 context ≥ 32k，输出 token ≥ 4096

### 切换方式

前端请求 `POST /api/v1/bootstrap/stream` 时传 `mode` 参数：
```json
{ "logline": "...", "mode": "sequential" }   // 串行，适合短上下文本地模型
{ "logline": "...", "mode": "single_shot" }  // 单次全量，适合大上下文远程模型
```

---

## 前端状态管理约定

创作端全局用 **Zustand**（`apps/client/src/store/index.ts`），规则：
- 列表数据（`chapters[]`、`characters[]`等）存 store
- 组件内临时 UI 状态（loading、modal open）用 `useState`
- API 调用后用 `upsert*` 系列方法更新 store，不要重新 fetch 整个列表

---

## 已完成功能

- [x] 项目 CRUD
- [x] 世界观设定 CRUD
- [x] 人物 + 关系 CRUD
- [x] 大纲树（层级编辑）
- [x] 章节写作（TipTap + 自动保存 + 版本快照）
- [x] AI 质检（JSON 评分报告）
- [x] AI 流式建议（SSE）
- [x] 记忆提取
- [x] 一句话生成（方案A串行 + 方案B单次）

## 待完成功能

- [ ] 人物关系图可视化（ReactFlow）
- [ ] 世界观设定卡完整 UI（分类卡片布局）
- [ ] 前十章追读分析表
- [ ] pgvector 语义记忆检索（`MemoryChunk.embedding` 字段已预留）
- [ ] 导出 TXT / EPUB
- [ ] 登录鉴权（目前无 auth）
- [ ] 故事线/境界体系/技能/道具/势力的前端 UI
- [ ] Bootstrap 生成时同步生成故事线、境界体系、核心技能与道具
- [ ] AI 质检时结合故事线进度与境界体系做一致性检查

---

<span id="documentation-contract"></span>

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

## 开发建议（给未来的 Codex）

1. **改 AI 调用**：只需动 `apps/backend/app/services/ai_service.py`，不要在 router 层直接调 openai
2. **加新数据表**：在 `apps/backend/app/models/` 新建文件 → `models/__init__.py` 导出 → `schemas/` 对应 → `routers/` 路由 → `main.py` 注册
3. **Prompt 优化**：prompt 字符串统一放在 service 层；需要 JSON 时在提示词末尾强调「只返回 JSON」
4. **JSON 解析**：所有 `_call_ai` 的 JSON 解析用 `_parse_json()` 统一处理，不要 try/except 分散在各处
5. **pgvector**：embedding 字段已在 `MemoryChunk` 预留，启用时需 `CREATE EXTENSION vector;` 并取消 `memory.py` 中的条件导入
6. **改创作端 UI**：主要改 `apps/client/`；**管理后台**改 `apps/frontend/`（与 client 独立依赖与构建）
7. **TS/JS 注释**：新增或修改公共 `export` 时，遵循上文「代码文档与注释契约」，使用 **严格 JSDoc**；后端对应模块用 Google 风格 docstring。

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
