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

export const PROMISE_TYPE_LABEL: Record<string, string> = {
  chapter_ending: '章末悬念',
  volume_ending: '卷末钩子',
  name_implication: '名字/开篇暗示',
  chapter_comment_consensus: '章评共识',
  protagonist_claim: '主角宣言',
}
