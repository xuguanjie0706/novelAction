/**
 * @file api/client.ts — 薄壳桶文件（barrel re-export）
 *
 * 历史上此文件为 979 行单体；现已按资源域拆分为多个子模块：
 *   base.ts        — axios 实例 + 拦截器 + LLM 计时工具
 *   projects.ts    — projectsApi / dashboardApi / coverApi
 *   worldbuilding.ts — settingsApi / charactersApi / storylinesApi / ...
 *   outline.ts     — outlineApi
 *   content.ts     — chaptersApi / foreshadowsApi / scenesApi / ...
 *   bootstrap.ts   — bootstrapApi / bootstrapRunsApi
 *   ai.ts          — llmApi / aiApi
 *
 * 所有对 `import ... from '../api/client'` 的路径保持不变，无需修改调用方。
 */

export { default } from './base'
export * from './base'
export * from './projects'
export * from './worldbuilding'
export * from './outline'
export * from './content'
export * from './bootstrap'
export * from './ai'
