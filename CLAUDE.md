# Novel System — 项目记忆 (CLAUDE.md)

> 这个文件是给 AI 助手（Claude）读的上下文锚点。  
> 每次重要决策、架构变更、未完成事项都记录在这里，避免重复推导。

---

## 项目概述

**目标**：一个面向网络小说作者的 AI 辅助创作系统。  
**核心特性**：输入一句话创意，AI 自动生成小说名称、世界观设定、人物、大纲、记忆库；后续写作时提供质检、建议、长篇记忆管理。

**技术栈**：
- 后端：FastAPI + SQLAlchemy + PostgreSQL（含 pgvector）
- 前端：React + TypeScript + Vite + TailwindCSS + Zustand + TipTap
- AI：统一走 OpenAI 兼容协议（`AsyncOpenAI(base_url=..., api_key=...)`）

---

## AI 模型策略

### 当前模型

| 环境 | 模型 | base_url |
|------|------|----------|
| 本地开发 | `qwen3:8b`（Ollama） | `http://localhost:11434/v1` |
| 生产/未来 | Gemini（通过兼容代理） | 待填 |

### 关键决策：统一用 OpenAI 兼容协议

**原因**：不绑定任何 SDK，只需改 `.env` 的 `LLM_BASE_URL` + `LLM_API_KEY` + `AI_MODEL` 即可切换模型。

```env
# 本地
LLM_BASE_URL=http://localhost:11434/v1
LLM_API_KEY=ollama
AI_MODEL=qwen3:8b

# Gemini（通过 OpenAI 兼容层）
LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai
LLM_API_KEY=your-gemini-api-key
AI_MODEL=gemini-2.0-flash
```

### qwen3:8b 特别注意

- context window 约 8k，单次 prompt **控制在 1500 token 以内**
- JSON 输出偶有格式错误，`_parse_json()` 要做容错（去 markdown fence，strip 空白）
- 不支持 `thinking` 参数（Qwen3 某些版本有），如遇报错加 `extra_body={"enable_thinking": False}`

### Gemini 迁移时的变化

- Gemini 支持 100 万 token context，可以切换到**方案 B（单次全量生成）**
- `generation_service.py` 里 `mode="single_shot"` 已预留，切换只需改前端请求参数

---

## 数据模型速查

```
Project
  ├── WorldSetting（设定卡，有 category）
  ├── Character + CharacterRelationship
  ├── OutlineNode（树形：volume → arc → chapter_plan）
  ├── Chapter + ChapterVersion
  └── MemoryChunk（长篇记忆，后续接 pgvector embedding）
```

所有 UUID 主键，`project_id` 外键贯穿所有表。

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
| `POST /api/v1/bootstrap/stream` | **一句话→全量生成（SSE）** |

---

## 一句话生成（Bootstrap）双方案

### 方案 A：串行步进（Sequential）— 默认，适合小模型

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
{ "logline": "...", "mode": "sequential" }   // qwen3
{ "logline": "...", "mode": "single_shot" }  // gemini
```

---

## 前端状态管理约定

全局用 **Zustand**（`src/store/index.ts`），规则：
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

---

## 开发建议（给未来的 Claude）

1. **改 AI 调用**：只需动 `app/services/ai_service.py`，不要在 router 层直接调 openai
2. **加新数据表**：在 `models/` 新建文件 → `models/__init__.py` 导出 → `schemas/` 对应 → `routers/` 路由 → `main.py` 注册
3. **Prompt 优化**：prompt 字符串统一放在 service 层，方便整体调整；8b 模型 prompt 末尾加 "只返回JSON，不要任何解释文字"
4. **JSON 解析**：所有 `_call_ai` 的 JSON 解析用 `_parse_json()` 统一处理，不要 try/except 分散在各处
5. **pgvector**：embedding 字段已在 `MemoryChunk` 预留，启用时需 `CREATE EXTENSION vector;` 并取消 `memory.py` 中的条件导入

---

## 本地启动命令

```bash
# Docker 一键启动
docker-compose up -d

# 手动启动后端
cd backend && uvicorn app.main:app --reload

# 手动启动前端
cd frontend && npm run dev
```
