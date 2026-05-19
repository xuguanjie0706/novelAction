# Novel System — Agent 入口

> **项目记忆的唯一定稿在 [`CLAUDE.md`](./CLAUDE.md)。**  
> 本文件仅供 Cursor / 兼容脚本识别仓库根路径；**不要在此维护与 `CLAUDE.md` 重复的清单**（已完成功能、待办、架构决策、上帝文件登记册等一律只改 `CLAUDE.md`）。

---

## 使用说明（给 Agent）

1. **动手前先读 [`CLAUDE.md`](./CLAUDE.md)** — 含 Bootstrap 步骤、数据模型、API 约定、代码结构红线、已完成功能与待办。
2. 日常研发约束另见 [`.cursor/rules/novelaction-core-principles.mdc`](./.cursor/rules/novelaction-core-principles.mdc)（产品定位、monorepo 路径、AI 调用分层等）。
3. **更新进度时只编辑 `CLAUDE.md`**；无需把相同条目再抄进本文件。

---

## 快速索引（正文均在 CLAUDE.md）

| 主题 | 在 CLAUDE.md 中查找 |
|------|---------------------|
| Scene 三层调度（plan-save / draft / stitch + 写作页分场面板） | 「已完成功能」Scene 相关 `[x]` 条目 |
| Bootstrap 串行步骤与 SSE 映射 | 「Bootstrap 步骤映射表」 |
| 任务级采样 `llm_task_profiles` | 「AI 模型策略」→ 任务级采样配置 |
| Service/Router 拆分蓝图、上帝文件登记册 | 「代码结构红线」「上帝文件登记册」 |
| 本地启动 | 文末「本地启动命令」 |

---

## 与历史副本的关系

- 此前 `AGENTS.md` 与 `CLAUDE.md` 曾并行维护，易产生漂移（例如 Scene 三层调度在 `CLAUDE.md` 已勾选完成、`AGENTS.md` 仍标待办）。
- **自本条起：`CLAUDE.md` 为唯一事实来源；`AGENTS.md` 仅作入口与索引。**
