import type { Project } from '../types'

export const HOME_WORD_GOAL = 5000

export const HOME_WRITING_STATS = {
  totalWords: 18560,
  streakDays: 8,
  averageWords: 2651,
  writingDays: 6,
  week: [
    { label: '一', words: 0, height: 4 },
    { label: '二', words: 2100, height: 48 },
    { label: '三', words: 1980, height: 44 },
    { label: '四', words: 983, height: 25 },
    { label: '五', words: 1620, height: 39 },
    { label: '六', words: 3120, height: 70 },
    { label: '日', words: 520, height: 16 },
  ],
}

export const HOME_MOCK_PROJECTS: Project[] = [
  {
    id: 'mock-embers',
    title: '焚天战纪',
    genre: '玄幻',
    logline: '少年从边陲小城出发，追索失落火种与王朝真相。',
    status: 'writing',
    target_words: 1200000,
    cover_url: '',
    created_at: '2026-04-01T08:00:00.000Z',
    updated_at: '2026-04-28T09:30:00.000Z',
  },
  {
    id: 'mock-city',
    title: '都市禁区：暗影猎人',
    genre: '都市异能',
    logline: '城市裂缝后，普通调查员被卷入异能组织的暗战。',
    status: 'drafting',
    target_words: 800000,
    cover_url: '',
    created_at: '2026-03-18T08:00:00.000Z',
    updated_at: '2026-04-26T21:10:00.000Z',
  },
]

export const HOME_RECENT_FALLBACK = [
  {
    id: 'recent-1',
    title: '焚天战纪',
    chapter: '第23章 生死一线',
    words: 2560,
    timeLabel: '刚刚',
  },
  {
    id: 'recent-2',
    title: '逆天裁决：从剥离天道命格开始',
    chapter: '第18章 命格觉醒',
    words: 1872,
    timeLabel: '2 小时前',
  },
  {
    id: 'recent-3',
    title: '都市禁区：暗影猎人',
    chapter: '第15章 夜幕降临',
    words: 1320,
    timeLabel: '昨天',
  },
  {
    id: 'recent-4',
    title: '万古吞天诀：从废脉觉醒开始无敌',
    chapter: '第8章 吞噬之力',
    words: 983,
    timeLabel: '2 天前',
  },
  {
    id: 'recent-5',
    title: '都市猎人',
    chapter: '第3章 初入都市',
    words: 654,
    timeLabel: '3 天前',
  },
]

export const HOME_INSPIRATION = {
  text: '在最深的黑暗中，往往孕育着最耀眼的光明。',
  tag: '逆境成长',
}

export const HOME_RECOMMENDATIONS = [
  {
    id: 'book-1',
    title: '诡秘之主',
    author: '爱潜水的乌贼',
    meta: '玄幻 · 连载中',
    coverStyle: 'linear-gradient(145deg, #0f172a 0%, #334155 48%, #f59e0b 100%)',
  },
  {
    id: 'book-2',
    title: '大奉打更人',
    author: '卖报小郎君',
    meta: '仙侠 · 连载中',
    coverStyle: 'linear-gradient(145deg, #dbeafe 0%, #64748b 48%, #111827 100%)',
  },
  {
    id: 'book-3',
    title: '我有一座冒险屋',
    author: '我会修空调',
    meta: '悬疑 · 完结',
    coverStyle: 'linear-gradient(145deg, #111827 0%, #7f1d1d 55%, #fef2f2 100%)',
  },
]
