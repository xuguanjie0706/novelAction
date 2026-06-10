/** @file 侧栏共享文案映射（五拍/记忆类型/线索类型）。 */

export const BEAT_LABELS: Record<string, string> = {
  yaqu: '憋屈铺垫',
  trigger: '转折扳机',
  yinbao: '引爆',
  payoff: '爽点+见证者',
  hook: '章末钩子',
}

export const BEAT_KEYS = ['yaqu', 'trigger', 'yinbao', 'payoff', 'hook'] as const

export const MEM_TYPE_LABELS: Record<string, string> = {
  summary: '摘要',
  fact: '事实',
  event: '事件',
  state: '状态',
  relation: '关系',
}

export const CLUE_TYPE_LABELS: Record<string, string> = {
  hook: '钩子',
  foreshadow: '伏笔',
  promise: '承诺',
}

export const CLUE_STATUS_LABELS: Record<string, string> = {
  open: '未回收',
  resolved: '已回收',
  dropped: '已弃用',
}
