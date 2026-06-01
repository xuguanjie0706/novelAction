/** @file 复盘面板文案常量 */

export const STATUS_LABEL: Record<string, string> = {
  alive: '存活', dead: '死亡', missing: '失踪', sealed: '封印', transformed: '变异',
}

export const STORYLINE_STATUS_LABEL: Record<string, string> = {
  planned: '规划中', active: '进行中', climax: '高潮', resolved: '已结局', dropped: '已废弃',
}

export const DEBRIEF_APPLY_SOURCE_LABEL: Record<string, string> = {
  queue_auto: '生成队列 · 自动落库',
  manual_tab: '复盘 Tab · 手动提交',
}

export const ASSET_UPDATE_LABELS: Record<string, string> = {
  new_items: '新增道具/法宝',
  item_updates: '更新道具/法宝',
  new_skills: '新增功法/技能',
  skill_updates: '更新功法/技能',
  new_factions: '新增势力',
  faction_updates: '更新势力',
}

export const DIRECTIVE_PATCH_LABEL: Record<string, string> = {
  add_foreshadow: '伏笔建议',
  force_pov: '强制 POV',
  increase_screen_time_for: '增加戏份',
  must_resolve_promise_in_next_N_chapters: 'N 章内兑现承诺',
  adjust_pacing: '节奏',
  reader_expectation_note: '读者期待',
}

export const PACING_LABEL: Record<string, string> = {
  fast: '加快',
  normal: '正常',
  slow: '放缓',
}

export const PROMISE_TYPE_LABEL: Record<string, string> = {
  chapter_ending: '章末悬念',
  volume_ending: '卷末钩子',
  name_implication: '名字/开篇暗示',
  chapter_comment_consensus: '章评共识',
  protagonist_claim: '主角宣言',
}
