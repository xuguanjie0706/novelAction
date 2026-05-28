import React from 'react'
import {
  ArrowRight,
  BookOpen,
  Coins,
  ChevronRight,
  Lightbulb,
  PenLine,
  Plus,
  RefreshCw,
  Sparkles,
  Timer,
  Wand2,
} from 'lucide-react'
import type { DashboardHome, Project } from '../../types'
import { TargetWordsInput } from '../TargetWordsInput'
import {
  HOME_INSPIRATION,
  HOME_RECOMMENDATIONS,
  HOME_WRITING_STATS,
} from '../../data/homeMock'

export type RecentEdit = {
  id: string
  title: string
  chapter: string
  words: number
  timeLabel: string
  project?: Project
}

const quickActions = [
  {
    id: 'chapter',
    label: '新建章节',
    description: '创建新章节',
    icon: BookOpen,
    tone: 'text-amber-500 bg-amber-50',
  },
  {
    id: 'inspiration',
    label: '灵感记录',
    description: '记录创作灵感',
    icon: Lightbulb,
    tone: 'text-amber-500 bg-amber-50',
  },
  {
    id: 'name',
    label: '随机取名',
    description: '生成小说名字',
    icon: Wand2,
    tone: 'text-violet-500 bg-violet-50',
  },
  {
    id: 'wallet',
    label: '我的钱包',
    description: '查看余额与明细',
    icon: Coins,
    tone: 'text-amber-500 bg-amber-50',
  },
  {
    id: 'timer',
    label: '码字计时器',
    description: '专注写作',
    icon: Timer,
    tone: 'text-orange-500 bg-orange-50',
  },
]

function wordsLabel(words: number) {
  return `${words.toLocaleString()} 字`
}

export function HeroPanel({ onCreate, onContinue }: { onCreate: () => void; onContinue: () => void }) {
  return (
    <div className="relative mt-6 overflow-hidden rounded-lg border border-amber-100 bg-[#fff7e9] p-8 shadow-sm">
      <div className="relative z-10 max-w-md">
        <h2 className="text-2xl font-bold text-gray-950">开始创作吧</h2>
        <p className="mt-3 text-sm text-gray-600">每一个故事都从第一章开始！</p>
        <div className="mt-7 flex flex-wrap gap-3">
          <button
            type="button"
            onClick={onCreate}
            className="flex h-12 items-center gap-2 rounded-lg bg-amber-500 px-7 text-sm font-semibold text-white shadow-[0_12px_24px_rgba(245,158,11,0.25)] transition-colors hover:bg-amber-600"
          >
            <Plus size={18} />
            新建小说
          </button>
          <button
            type="button"
            onClick={onContinue}
            className="flex h-12 items-center gap-2 rounded-lg border border-gray-200 bg-white px-7 text-sm font-semibold text-gray-700 transition-colors hover:border-amber-200 hover:text-amber-600"
          >
            <PenLine size={18} />
            继续写作
          </button>
        </div>
      </div>

      <div className="pointer-events-none absolute bottom-0 right-6 hidden h-full w-[360px] sm:block">
        <div className="absolute bottom-8 right-2 h-28 w-48 rotate-[-7deg] rounded-lg border border-amber-100 bg-white/90 shadow-lg" />
        <div className="absolute bottom-8 right-5 h-28 w-48 rotate-[7deg] rounded-lg border border-emerald-100 bg-[#f5f6ed] shadow-md" />
        <div className="absolute bottom-[74px] right-[118px] h-[3px] w-24 rotate-[-57deg] rounded-full bg-gray-900 shadow-sm" />
        <div className="absolute bottom-[72px] right-[120px] h-[3px] w-7 rotate-[-57deg] rounded-full bg-amber-500" />
        <div className="absolute right-8 top-3 h-20 w-20 rounded-full bg-[#ead9bd] shadow-lg" />
        <div className="absolute right-12 top-7 h-12 w-12 rounded-full bg-[#8b5e34]/75" />
        <div className="absolute right-[-4px] top-8 h-9 w-8 rounded-full border-[8px] border-[#ead9bd]" />
        <div className="absolute bottom-20 right-[250px] h-24 w-2 rotate-[18deg] rounded-full bg-emerald-300/70" />
        <div className="absolute bottom-[134px] right-[244px] h-6 w-3 rotate-[22deg] rounded-full bg-lime-300" />
        <div className="absolute bottom-[118px] right-[222px] h-6 w-3 rotate-[42deg] rounded-full bg-lime-300" />
      </div>
    </div>
  )
}

export function QuickActionsGrid({ onAction }: { onAction: (actionId: string) => void }) {
  return (
    <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {quickActions.map(({ id, label, description, icon: Icon, tone }) => (
        <button
          key={id}
          type="button"
          onClick={() => onAction(id)}
          className="flex min-h-[78px] items-center gap-4 rounded-lg border border-gray-100 bg-white px-4 text-left shadow-sm transition hover:border-amber-200 hover:shadow-md"
        >
          <span className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg ${tone}`}>
            <Icon size={22} />
          </span>
          <span className="min-w-0">
            <span className="block truncate text-sm font-bold text-gray-950">{label}</span>
            <span className="mt-1 block truncate text-xs text-gray-400">{description}</span>
          </span>
        </button>
      ))}
    </div>
  )
}

export function RecentEdits({ edits, onOpen, onViewAll }: { edits: RecentEdit[]; onOpen: (project?: Project) => void; onViewAll?: () => void }) {
  return (
    <section id="recent-projects" className="mt-9">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-bold text-gray-950">最近编辑</h2>
        <button
          type="button"
          onClick={onViewAll}
          className="rounded-lg px-2 py-1 text-sm text-gray-500 transition-colors hover:bg-gray-50 hover:text-gray-900"
        >
          查看书架 →
        </button>
      </div>

      <div className="mt-3 rounded-lg border border-gray-100 bg-white px-4 py-2 shadow-sm">
        {edits.length === 0 ? (
          <div className="py-8 text-center text-sm text-gray-400">还没有写作记录，先开个头吧</div>
        ) : (
          edits.map(edit => (
            <button
              key={edit.id}
              type="button"
              onClick={() => onOpen(edit.project)}
              className="flex w-full items-center gap-4 border-b border-gray-100 py-4 text-left last:border-b-0"
            >
              <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-lg bg-amber-50 text-amber-500">
                <BookOpen size={22} />
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[15px] font-bold text-gray-950">{edit.title}</span>
                <span className="mt-1 block truncate text-sm text-gray-500">
                  {edit.chapter} · {wordsLabel(edit.words)}
                </span>
              </span>
              <span className="shrink-0 text-sm text-gray-400">{edit.timeLabel}</span>
            </button>
          ))
        )}
      </div>
    </section>
  )
}

/**
 * 写作数据面板。
 *
 * @param data 后端聚合数据 `dashboardApi.home()`；为 null 时退化到 mock，加载中显示 skeleton。
 * @param loading 首次加载未完成；显示骨架屏避免白板闪烁。
 */
export function WritingStatsPanel({ data, loading = false }: { data?: DashboardHome | null; loading?: boolean }) {
  // 兜底：未登录或网络异常时仍展示静态 mock，保持版面稳定
  const stats = data ?? HOME_WRITING_STATS_FALLBACK

  return (
    <section className="rounded-lg border border-gray-100 bg-white p-5 shadow-sm">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-bold text-gray-950">写作数据</h2>
        <span className="flex h-8 items-center gap-1 rounded-lg border border-gray-100 px-3 text-xs text-gray-500">
          本周
          <ChevronRight size={13} className="rotate-90" />
        </span>
      </div>

      {loading ? (
        <div className="mt-7 space-y-5">
          <div className="grid grid-cols-2 gap-4">
            <div className="h-12 animate-pulse rounded bg-gray-100" />
            <div className="h-12 animate-pulse rounded bg-gray-100" />
          </div>
          <div className="h-[118px] animate-pulse rounded bg-gray-100" />
        </div>
      ) : (
        <>
          <div className="mt-7 grid grid-cols-2 gap-4">
            <Metric value={stats.total_words.toLocaleString()} label="总字数" suffix="字" />
            <Metric value={String(stats.streak_days)} label="连续创作" suffix="天" />
          </div>

          <div className="mt-7 h-[118px] border-t border-gray-100 pt-3">
            <div className="flex h-full items-end gap-4">
              {stats.week.map(day => (
                <div key={day.date} className="flex flex-1 flex-col items-center gap-2">
                  <div className="relative flex h-[78px] w-full items-end justify-center">
                    <div
                      className="w-2 rounded-full bg-amber-500"
                      title={`${day.words.toLocaleString()} 字`}
                      style={{ height: day.height }}
                    />
                  </div>
                  <span className="text-xs text-gray-400">{day.weekday_label}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="mt-5 grid grid-cols-2 gap-5 border-t border-gray-100 pt-5">
            <Metric value={stats.average_words.toLocaleString()} label="平均字数" suffix="字" compact />
            <Metric value={String(stats.writing_days)} label="创作天数" suffix="天" compact />
          </div>
        </>
      )}
    </section>
  )
}

// 旧版 mock 数据（HOME_WRITING_STATS）字段名是 totalWords/streakDays/...，这里转成与
// DashboardHome 一致的 snake_case 兜底，方便上方组件统一处理。后端不可用时使用。
const HOME_WRITING_STATS_FALLBACK: Pick<
  DashboardHome,
  'total_words' | 'streak_days' | 'writing_days' | 'average_words' | 'week'
> = {
  total_words: HOME_WRITING_STATS.totalWords,
  streak_days: HOME_WRITING_STATS.streakDays,
  writing_days: HOME_WRITING_STATS.writingDays,
  average_words: HOME_WRITING_STATS.averageWords,
  week: HOME_WRITING_STATS.week.map(d => ({
    date: d.label,
    weekday_label: d.label,
    words: d.words,
    height: d.height,
  })),
}

function Metric({ value, suffix, label, compact = false }: { value: string; suffix: string; label: string; compact?: boolean }) {
  return (
    <div>
      <div className={compact ? 'text-xl font-bold text-gray-950' : 'text-[28px] font-bold text-gray-950'}>
        {value}
        <span className="ml-1 text-sm font-medium text-gray-700">{suffix}</span>
      </div>
      <div className="mt-2 text-xs text-gray-400">{label}</div>
    </div>
  )
}

export function InspirationPanel() {
  return (
    <section className="rounded-lg border border-gray-100 bg-white p-5 shadow-sm">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-bold text-gray-950">今日灵感</h2>
        <button
          type="button"
          className="flex items-center gap-1 rounded-lg px-2 py-1 text-xs text-gray-500 transition-colors hover:bg-gray-50 hover:text-gray-900"
        >
          <RefreshCw size={14} />
          换一换
        </button>
      </div>
      <div className="mt-4 rounded-lg bg-[#fbf3e8] p-4">
        <p className="text-sm font-medium leading-7 text-gray-800">{HOME_INSPIRATION.text}</p>
        <div className="mt-3 inline-flex rounded-md bg-white/70 px-2 py-1 text-xs text-amber-700">
          # {HOME_INSPIRATION.tag}
        </div>
      </div>
    </section>
  )
}

export function RecommendationsPanel() {
  return (
    <section className="rounded-lg border border-gray-100 bg-white p-5 shadow-sm">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-bold text-gray-950">推荐阅读</h2>
        <button
          type="button"
          className="flex items-center gap-1 rounded-lg px-2 py-1 text-xs text-gray-500 transition-colors hover:bg-gray-50 hover:text-gray-900"
        >
          <RefreshCw size={14} />
          换一换
        </button>
      </div>

      <div className="mt-4 space-y-3">
        {HOME_RECOMMENDATIONS.map(book => (
          <div key={book.id} className="flex items-center gap-3">
            <div
              className="flex h-[74px] w-[54px] shrink-0 items-end rounded-md p-1.5 text-[11px] font-bold leading-tight text-white shadow-sm"
              style={{ background: book.coverStyle }}
            >
              {book.title.slice(0, 4)}
            </div>
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-bold text-gray-950">{book.title}</div>
              <div className="mt-1 truncate text-xs text-gray-500">{book.author}</div>
              <div className="mt-1 inline-flex rounded-md bg-gray-100 px-2 py-0.5 text-xs text-gray-500">
                {book.meta}
              </div>
            </div>
          </div>
        ))}
      </div>

      <button
        type="button"
        className="mx-auto mt-5 flex items-center gap-1 rounded-lg px-3 py-2 text-sm font-medium text-gray-600 transition-colors hover:bg-gray-50 hover:text-gray-950"
      >
        查看更多推荐
        <ChevronRight size={16} />
      </button>
    </section>
  )
}

export function WalletEntryCard({
  balance,
  loading = false,
  onOpen,
}: {
  balance: number | null
  loading?: boolean
  onOpen: () => void
}) {
  return (
    <section className="rounded-lg border border-amber-100 bg-[#fff7e9] p-5 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-bold text-gray-950">我的钱包</h2>
          <p className="mt-1 text-xs text-gray-500">积分余额与消费记录</p>
        </div>
        <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-white/90 text-amber-500 shadow-sm">
          <Coins size={18} />
        </span>
      </div>
      <div className="mt-4 rounded-lg border border-amber-100/70 bg-white/80 px-4 py-3">
        <div className="text-xs text-gray-500">当前可用积分</div>
        {loading ? (
          <div className="mt-2 h-8 w-24 animate-pulse rounded bg-amber-100/80" />
        ) : (
          <div className="mt-1 text-2xl font-bold text-gray-950 tabular-nums">
            {(balance ?? 0).toLocaleString()}
          </div>
        )}
      </div>
      <button
        type="button"
        onClick={onOpen}
        className="mt-4 flex h-10 w-full items-center justify-center gap-1.5 rounded-lg bg-amber-500 text-sm font-semibold text-white transition-colors hover:bg-amber-600"
      >
        进入钱包
        <ArrowRight size={15} />
      </button>
    </section>
  )
}

// 字数选项配置
const WORD_COUNT_OPTIONS = [
  { label: '短篇', value: 800000,  sub: '约80万字 / 6卷' },
  { label: '标准', value: 1200000, sub: '约120万字 / 9卷' },
  { label: '长篇', value: 1500000, sub: '约150万字 / 11卷' },
  { label: '超长', value: 2000000, sub: '约200万字 / 15卷' },
] as const

function wordsToVols(w: number) {
  return Math.ceil(Math.round(w / 2300) / 60)
}

export function CreateProjectDialog({
  form,
  creating,
  onChange,
  onCreate,
  onClose,
  onUseAi,
}: {
  form: { title: string; genre: string; logline: string; premise: string; target_words: number }
  creating: boolean
  onChange: React.Dispatch<React.SetStateAction<{ title: string; genre: string; logline: string; premise: string; target_words: number }>>
  onCreate: () => void
  onClose: () => void
  onUseAi: () => void
}) {
  const [customMode, setCustomMode] = React.useState(false)
  const estChapters = Math.round(form.target_words / 2300)
  const estVols = wordsToVols(form.target_words)

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-gray-950/30 px-4">
      <div className="w-full max-w-lg rounded-lg bg-white p-5 shadow-xl">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-bold text-gray-950">新建小说</h3>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg px-2 py-1 text-sm text-gray-400 transition-colors hover:bg-gray-50 hover:text-gray-900"
          >
            关闭
          </button>
        </div>

        <div className="mt-5 space-y-3">
          <input
            placeholder="小说名称 *"
            value={form.title}
            onChange={e => onChange(f => ({ ...f, title: e.target.value }))}
            className="h-11 w-full rounded-lg border border-gray-200 px-3 text-sm outline-none transition focus:border-amber-400 focus:ring-2 focus:ring-amber-100"
          />
          <input
            placeholder="类型（玄幻 / 都市 / 科幻...）"
            value={form.genre}
            onChange={e => onChange(f => ({ ...f, genre: e.target.value }))}
            className="h-11 w-full rounded-lg border border-gray-200 px-3 text-sm outline-none transition focus:border-amber-400 focus:ring-2 focus:ring-amber-100"
          />
          <textarea
            placeholder="一句话创意（选填）"
            value={form.logline}
            onChange={e => onChange(f => ({ ...f, logline: e.target.value }))}
            rows={3}
            className="w-full resize-none rounded-lg border border-gray-200 px-3 py-3 text-sm outline-none transition focus:border-amber-400 focus:ring-2 focus:ring-amber-100"
          />
          <textarea
            placeholder="立意与类型（选填）：目标读者、主题命题、核心矛盾、禁忌边界..."
            value={form.premise}
            onChange={e => onChange(f => ({ ...f, premise: e.target.value }))}
            rows={5}
            className="w-full resize-none rounded-lg border border-gray-200 px-3 py-3 text-sm outline-none transition focus:border-amber-400 focus:ring-2 focus:ring-amber-100"
          />

          {/* 字数目标选择器 */}
          <div>
            <div className="mb-1.5 flex items-center justify-between">
              <span className="text-xs font-medium text-gray-500">全书字数目标</span>
              <button
                type="button"
                onClick={() => setCustomMode(m => !m)}
                className="text-xs text-amber-500 hover:text-amber-600"
              >
                {customMode ? '快捷选择' : '自定义'}
              </button>
            </div>

            {customMode ? (
              <TargetWordsInput
                value={form.target_words}
                onChange={n => onChange(f => ({ ...f, target_words: n }))}
                hint={<>（约 {estChapters} 章 / {estVols} 卷）</>}
              />
            ) : (
              <div className="grid grid-cols-4 gap-1.5">
                {WORD_COUNT_OPTIONS.map(opt => (
                  <button
                    key={opt.value}
                    type="button"
                    onClick={() => onChange(f => ({ ...f, target_words: opt.value }))}
                    className={`rounded-lg border py-2 text-center transition ${
                      form.target_words === opt.value
                        ? 'border-amber-400 bg-amber-50 text-amber-700'
                        : 'border-gray-200 text-gray-600 hover:border-amber-200'
                    }`}
                  >
                    <div className="text-sm font-semibold">{opt.label}</div>
                    <div className="text-[10px] text-gray-400">{opt.sub}</div>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="mt-5 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={onCreate}
            disabled={creating}
            className="flex h-10 items-center gap-2 rounded-lg bg-amber-500 px-4 text-sm font-semibold text-white transition-colors hover:bg-amber-600 disabled:opacity-50"
          >
            <Plus size={16} />
            {creating ? '创建中...' : '创建'}
          </button>
          <button
            type="button"
            onClick={onUseAi}
            className="flex h-10 items-center gap-2 rounded-lg border border-gray-200 px-4 text-sm font-semibold text-gray-700 transition-colors hover:border-amber-200 hover:text-amber-600"
          >
            <Sparkles size={16} />
            AI 一键生成
          </button>
          <button
            type="button"
            onClick={onClose}
            className="h-10 rounded-lg bg-gray-100 px-4 text-sm font-medium text-gray-600 transition-colors hover:bg-gray-200"
          >
            取消
          </button>
        </div>
      </div>
    </div>
  )
}
