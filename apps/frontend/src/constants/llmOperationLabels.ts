/**
 * LLM 调用 operation / task 中文标签。
 * 供管理后台「LLM 调用记录」与 Dashboard「Token 消耗 TOP 任务」共用。
 *
 * 键来源：后端 context.operation、context.task（见 llm_task_profiles / 各 service 落库）。
 */

/** 完整中文说明（副标题 / 详情） */
export const LLM_OPERATION_LABELS: Record<string, string> = {
  // ── Bootstrap 主流程 ──────────────────────────────────────────
  'bootstrap.positioning': 'Bootstrap 立项会议：提炼题材定位与卖点承诺',
  'bootstrap.project': 'Bootstrap 项目初始化：生成书名、前提与世界观概览',
  'bootstrap.power_systems': 'Bootstrap 力量体系：生成境界等级、机制与代价',
  'bootstrap.factions': 'Bootstrap 阵营势力：生成组织关系与立场冲突',
  'bootstrap.storylines': 'Bootstrap 故事线：生成主线/支线与推进节奏',
  'bootstrap.storyline_weave': 'Bootstrap 故事线编织：校验各线交汇与卷级分配',
  'bootstrap.antagonist_ladder': 'Bootstrap 卷级对立面：生成各卷 Boss 名与境界阶梯',
  'bootstrap.characters': 'Bootstrap 人物库：生成核心角色与关系锚点',
  'bootstrap.skills': 'Bootstrap 技能体系：生成功法/技能结构与成长路径',
  'bootstrap.items': 'Bootstrap 道具体系：生成资源、稀有度与用途',
  'bootstrap.settings': 'Bootstrap 世界观总设：生成设定卡',
  'bootstrap.volumes': 'Bootstrap 卷章规划：生成卷级骨架、阶段与节拍',
  'bootstrap.emotion_arc': 'Bootstrap 情绪节律：生成各卷情绪收支与主色调',
  'bootstrap.villain_arc': 'Bootstrap 反派行动线：生成主要反派卷级计划',
  'bootstrap.memory': 'Bootstrap 记忆库：生成可复用事实与约束种子',
  'bootstrap.relations': 'Bootstrap 人物关系：生成人际网络与动态张力',
  'bootstrap.core_mysteries': 'Bootstrap 核心谜题：跨卷核心谜团预分配与伏笔台账',
  'bootstrap.opening_contract': 'Bootstrap 开局承诺：生成追读承诺清单与读者预期',
  'bootstrap.consistency_scan': 'Bootstrap 一致性扫描：检测设定冲突与结构缺口',
  'bootstrap.vol_chapters': '按卷展开章纲：生成章节蓝图与章纲 linter 校验',
  'bootstrap.vol1_chapters': 'Bootstrap 第一卷章纲：生成首卷章节拆分与推进线（遗留路径）',
  'bootstrap.ch1_scenes': 'Bootstrap 第一章场景：生成开篇场景与节奏节点（遗留路径）',
  bootstrap_complete_settings: 'Bootstrap 设定补全：补齐世界观结构化条目',
  bootstrap_complete_characters: 'Bootstrap 人物补全：补齐角色画像与关系',

  // ── 写作 / 起草 ───────────────────────────────────────────────
  draft_assist_stream: '写作辅助：流式起笔/续写/重写章节正文',
  'draft.chapter': '章节正文起草：按章纲与分场生成正文',
  'draft.opening': '开局期正文：高钩子密度、偏短篇幅起草',
  'draft.rising': '起飞期正文：势力扩张与感情线接入',
  'draft.turning': '转折期正文：矛盾升级与代价兑现',
  'draft.dark_hour': '至暗期正文：节奏放缓、允许虐点',
  'draft.climax': '高潮期正文：伏笔回收与爆点拉满',
  'draft.ending': '收束期正文：卷末悬念种子与收束',
  'draft.scene_plan': '分场计划：将章纲拆分为逐场写作蓝图',

  // ── 大纲 ───────────────────────────────────────────────────────
  expand_outline: '大纲展开：把卷/节点展开成章节计划',
  plan_full_structure: '全量结构规划：规划卷级结构与篇幅节奏',
  'outline.expand': '大纲展开：把节点展开为子结构或章节计划',
  'outline.full_structure': '全量结构规划：规划卷级结构与篇幅节奏',
  'outline.repair': '大纲修复：在保留连贯性前提下局部修正章纲',
  'outline.character_gap': '人物缺口补全：识别并补齐大纲人物覆盖',

  // ── 质检 / 一致性 ─────────────────────────────────────────────
  quality_check: '章节质检：检查剧情、人物一致性与设定冲突',
  quality_micro_patch: '质检微修：按质检结论最小幅度改正文',
  'quality.check': '章节质检：检查剧情、人物一致性与设定冲突',
  'quality.micro_patch': '质检微修：按质检结论最小幅度改正文',
  'quality.outline_check': '大纲质检：检查章纲结构与设定一致性',
  'quality.causality_check': '因果链审计：检查章节/大纲因果逻辑',
  'quality.character_arc_check': '人物弧审计：检查角色成长与行为一致性',
  'quality.foreshadow_audit': '伏笔审计：检查伏笔埋设与回收配对',
  'quality.coherence_check': '多章节连贯性检测：检查标题匹配与章节衔接',
  'quality.coherence_apply': '连贯性修订：按评测结论最小幅度改正文',
  chapter_coherence_check: '多章节连贯性检测：检查标题匹配与章节衔接',
  chapter_coherence_apply: '连贯性修订：按评测结论最小幅度改正文',
  outline_quality_check: '大纲质检：检查章纲结构与设定一致性',
  outline_repair_plan: '大纲修复方案：生成章纲局部修正计划',
  outline_check_causality: '大纲因果链审计：检查章纲因果逻辑',
  outline_check_character_arc: '大纲人物弧审计：检查角色成长覆盖',
  outline_check_foreshadow_audit: '大纲伏笔审计：检查伏笔埋设与回收',
  violation_scan: '违规扫描：按平台规则检测敏感内容',
  pre_write_warning: '写前预警：起草前扫描潜在一致性与节奏风险',
  reader_psychology_sim: '读者心理模拟：预测追读体验与章末钩子效果',

  // ── 复盘 / 记忆 ────────────────────────────────────────────────
  auto_extract_debrief: '自动复盘：提取人物/故事线变化与章节索引',
  extract_memory: '记忆提取：从章节抽取可复用记忆点',
  'debrief.auto': '自动复盘：提取人物/故事线变化与章节索引',
  'debrief.extract_memory': '记忆提取：从章节抽取可复用记忆点',
  'debrief.foreshadow': '伏笔复盘：从章节提取伏笔埋设与回收信号',
  memory_conflict_detect: '记忆冲突检测：扫描记忆库前后矛盾',
  'memory.conflict_detect': '记忆冲突检测：扫描记忆库前后矛盾',

  // ── 交互建议 ───────────────────────────────────────────────────
  suggest_stream: 'AI 写作建议：流式生成优化建议',
  'suggest.stream': 'AI 写作建议：流式生成优化建议',
  chat_stream: 'AI 对话：流式聊天辅助',
}

/** Dashboard / 表格主标题用的短标签 */
export const LLM_OPERATION_SHORT: Record<string, string> = {
  'bootstrap.positioning': 'BS 立项',
  'bootstrap.project': 'BS 项目初始化',
  'bootstrap.settings': 'BS 设定卡',
  'bootstrap.power_systems': 'BS 境界体系',
  'bootstrap.factions': 'BS 势力',
  'bootstrap.storylines': 'BS 故事线',
  'bootstrap.storyline_weave': 'BS 故事线编织',
  'bootstrap.antagonist_ladder': 'BS 卷级 Boss',
  'bootstrap.characters': 'BS 人物库',
  'bootstrap.skills': 'BS 技能体系',
  'bootstrap.items': 'BS 道具体系',
  'bootstrap.volumes': 'BS 卷规划',
  'bootstrap.emotion_arc': 'BS 情绪节律',
  'bootstrap.villain_arc': 'BS 反派行动线',
  'bootstrap.memory': 'BS 记忆库',
  'bootstrap.relations': 'BS 人物关系',
  'bootstrap.core_mysteries': 'BS 核心谜题',
  'bootstrap.opening_contract': 'BS 开局承诺',
  'bootstrap.consistency_scan': 'BS 一致性扫描',
  'bootstrap.vol_chapters': '卷纲展开',
  'bootstrap.vol1_chapters': 'BS 首卷章纲',
  'bootstrap.ch1_scenes': 'BS 首章场景',
  draft_assist_stream: '章节写作',
  'draft.chapter': '章节正文',
  'draft.scene_plan': '分场计划',
  quality_check: '章节质检',
  'quality.check': '章节质检',
  expand_outline: '大纲展开',
  'outline.expand': '大纲展开',
  auto_extract_debrief: '自动复盘',
  'debrief.auto': '自动复盘',
  extract_memory: '记忆提取',
  suggest_stream: 'AI 建议',
  'suggest.stream': 'AI 建议',
  memory_conflict_detect: '记忆冲突',
  'memory.conflict_detect': '记忆冲突',
  chapter_coherence_check: '连贯性检测',
  'quality.coherence_check': '连贯性检测',
}

/** Bootstrap 步骤后缀 → 中文（task 未显式登记时的兜底） */
const BOOTSTRAP_STEP_CN: Record<string, string> = {
  positioning: '立项会议',
  project: '项目初始化',
  power_systems: '境界体系',
  factions: '势力组织',
  storylines: '故事线',
  storyline_weave: '故事线编织',
  antagonist_ladder: '卷级对立面',
  characters: '人物库',
  skills: '技能体系',
  items: '道具体系',
  settings: '世界观设定',
  volumes: '卷骨架规划',
  emotion_arc: '情绪节律图',
  villain_arc: '反派行动线',
  memory: '记忆种子',
  relations: '人物关系',
  core_mysteries: '核心谜题',
  opening_contract: '开局追读承诺',
  consistency_scan: '一致性扫描',
  vol_chapters: '按卷展开章纲',
  vol1_chapters: '第一卷章纲',
  ch1_scenes: '第一章场景',
}

const DOMAIN_CN: Record<string, string> = {
  bootstrap: 'Bootstrap',
  draft: '写作',
  quality: '质检',
  outline: '大纲',
  debrief: '复盘',
  memory: '记忆',
  suggest: 'AI 建议',
}

const SNAKE_CN: Record<string, string> = {
  quality_check: '章节质检',
  quality_micro_patch: '质检微修',
  draft_assist_stream: '章节写作',
  expand_outline: '大纲展开',
  plan_full_structure: '全量结构规划',
  auto_extract_debrief: '自动复盘',
  extract_memory: '记忆提取',
  suggest_stream: 'AI 建议',
  chat_stream: 'AI 对话',
  memory_conflict_detect: '记忆冲突检测',
  chapter_coherence_check: '连贯性检测',
  chapter_coherence_apply: '连贯性修订',
  reader_psychology_sim: '读者心理模拟',
  pre_write_warning: '写前预警',
  violation_scan: '违规扫描',
}

function bootstrapFallback(step: string): string {
  const cn = BOOTSTRAP_STEP_CN[step]
  return cn ? `Bootstrap：${cn}` : `Bootstrap 流程：${step.replace(/_/g, ' ')}`
}

function dottedFallback(key: string): string | null {
  const dot = key.indexOf('.')
  if (dot <= 0) return null
  const domain = key.slice(0, dot)
  const step = key.slice(dot + 1)
  if (domain === 'bootstrap') return bootstrapFallback(step)
  const domainCn = DOMAIN_CN[domain]
  if (!domainCn) return null
  const stepCn = BOOTSTRAP_STEP_CN[step] ?? step.replace(/_/g, ' ')
  return `${domainCn}：${stepCn}`
}

/** 完整中文说明；未知键尽量给出可读中文而非裸英文 slug。 */
export function getLlmOperationLabel(key?: string): string {
  if (!key?.trim()) return '未标注作用'
  const k = key.trim()
  if (LLM_OPERATION_LABELS[k]) return LLM_OPERATION_LABELS[k]
  if (SNAKE_CN[k]) return SNAKE_CN[k]
  const dotted = dottedFallback(k)
  if (dotted) return dotted
  return `未登记作用：${k}`
}

/** 短标签；Dashboard 条形图与列表主标题。 */
export function getLlmOperationShortLabel(key?: string): string {
  if (!key?.trim()) return '未知'
  const k = key.trim()
  if (LLM_OPERATION_SHORT[k]) return LLM_OPERATION_SHORT[k]
  const full = getLlmOperationLabel(k)
  const colon = full.indexOf('：')
  if (colon > 0 && colon < 24) return full.slice(0, colon)
  if (k.startsWith('bootstrap.')) return `BS ${BOOTSTRAP_STEP_CN[k.slice(10)] ?? k.slice(10)}`
  return k.length > 16 ? `${k.slice(0, 16)}…` : k
}
