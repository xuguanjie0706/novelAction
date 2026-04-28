# Quickstart：验收 001-enrich-novel-ui

**路径前缀**：仓库根目录 `/Users/xgj/Documents/Claude/Projects/novelAction`

## 1. 启动前端

```bash
cd /Users/xgj/Documents/Claude/Projects/novelAction/frontend
pnpm install
pnpm run dev
```

浏览器打开 Vite 提示的本地 URL（默认常为 `http://localhost:3173`）。

## 2. 构建校验（合并前必跑）

```bash
cd /Users/xgj/Documents/Claude/Projects/novelAction/frontend
pnpm run build
```

预期：`tsc` 与 `vite build` 无错误。

## 3. 走查顺序（对齐 `contracts/ui-surfaces.md`）

1. **壳层（S-09）**：打开任意页；确认侧栏、顶栏、主内容区 **边界清晰**；当前模块在侧栏或标题可识别。  
2. **项目列表（S-01）**：空列表与有数据两种；空列表符合 **空状态契约**。  
3. **写作（S-02）**：打开含较长正文的章节；检查 **行长**、段落层次、与 AI 区 **边界**。  
4. **大纲 / 人物 / 记忆（S-03～S-05）**：各至少触发一次 **空列表** 与 **加载失败**（可断网或关后端）观察 FR-005。  
5. **AI 与队列（S-07、S-08）**：展开面板、观察辅区层次与队列状态区分。

## 4. 可选：无障碍抽查

- 浏览器放大至 **125%～150%**，核心路径仍可完成。  
- 在系统设置中开启 **减少动态效果**，界面无令人不适的长动画。

## 5. 已知限制（合并说明模板）

- 当前 `package.json` **无** Playwright/Vitest；**SC-001、SC-005** 需人工可用性样本时在 `spec.md` 建议规模外另行组织。  
- 本 quickstart **不** 要求后端启动即可完成的项：仅前端样式可走查；数据相关以 mock/已有环境为准。
