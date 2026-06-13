/**
 * 情节档案明细区块（无章头，供右侧单章卡与左侧全量列表复用）。
 * 计划五拍 + 复盘实际(核心事件/摘要) + 线索埋设·回收 + 资产/关系变更 + 首次出场。
 */
import clsx from 'clsx'
import { AlertTriangle, Sparkles } from 'lucide-react'
import type { DabaiChapterArchive } from '../../../types/dabaiLab'
import { BEAT_LABELS, CLUE_TYPE_LABELS } from './side/labels'

const SECTION = 'text-[10px] font-medium uppercase tracking-wide'

function Beat({ label, text }: { label: string; text: string }) {
  if (!text?.trim()) return null
  return (
    <div className="flex gap-1.5 text-xs leading-snug">
      <span className="shrink-0 text-rose-400">{label}</span>
      <span className="text-gray-700">{text}</span>
    </div>
  )
}

export default function ArchiveSections({ archive }: { archive: DabaiChapterArchive }) {
  const p = archive.plan
  return (
    <div className="space-y-3">
      {/* 计划五拍 */}
      <div className="rounded-lg bg-rose-50/40 p-2.5 space-y-1">
        <div className="flex items-center gap-1.5">
          <span className={clsx(SECTION, 'text-rose-500')}>计划 · 五拍</span>
          {p.shuang_type ? (
            <span className="rounded bg-rose-100 px-1.5 py-0.5 text-[10px] text-rose-700">{p.shuang_type}</span>
          ) : null}
          {p.is_big_beat ? (
            <span className="inline-flex items-center gap-0.5 rounded bg-amber-100 px-1.5 py-0.5 text-[10px] text-amber-700">
              <Sparkles size={9} /> 大爆点
            </span>
          ) : null}
          {p.location ? <span className="text-[10px] text-gray-400">{p.location}</span> : null}
        </div>
        <Beat label={BEAT_LABELS.yaqu} text={p.yaqu_setup} />
        <Beat label={BEAT_LABELS.trigger} text={p.emotion_turn} />
        <Beat label={BEAT_LABELS.yinbao} text={p.yinbao} />
        <Beat label={BEAT_LABELS.payoff} text={p.shuang_payoff} />
        <Beat label={BEAT_LABELS.hook} text={p.end_hook} />
      </div>

      {!archive.debriefed ? (
        <p className="text-[11px] text-gray-400">本章尚未复盘——仅显示章纲计划；写完并复盘后这里会出现实际发生的事件。</p>
      ) : null}

      {/* 复盘摘要 */}
      {archive.summary ? (
        <div>
          <div className={clsx(SECTION, 'mb-1 text-gray-400')}>本章摘要</div>
          <p className="text-xs text-gray-700">{archive.summary}</p>
        </div>
      ) : null}

      {/* 核心事件（实际发生） */}
      {archive.core_events.length > 0 ? (
        <div>
          <div className={clsx(SECTION, 'mb-1 text-gray-400')}>核心事件（实际发生）</div>
          <ul className="space-y-0.5">
            {archive.core_events.map(ev => (
              <li key={ev.id} className="flex gap-1.5 text-xs text-gray-700">
                <span className="shrink-0 text-rose-300">{'★'.repeat(Math.min(ev.importance || 1, 5))}</span>
                <span>{ev.content}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {/* 埋设 / 回收线索 */}
      {archive.clues_planted.length > 0 ? (
        <div>
          <div className={clsx(SECTION, 'mb-1 text-amber-500')}>埋下线索</div>
          {archive.clues_planted.map(c => (
            <div key={c.id} className="mb-0.5 rounded bg-amber-50 px-2 py-1 text-xs text-gray-700">
              <span className="text-amber-600">[{CLUE_TYPE_LABELS[c.clue_type] ?? c.clue_type}]</span> {c.title}
              {c.status !== 'open' ? <span className="ml-1 text-[10px] text-gray-400">（{c.status === 'resolved' ? '已回收' : '已弃用'}）</span> : null}
            </div>
          ))}
        </div>
      ) : null}
      {archive.clues_resolved.length > 0 ? (
        <div>
          <div className={clsx(SECTION, 'mb-1 text-emerald-500')}>回收线索</div>
          {archive.clues_resolved.map(c => (
            <div key={c.id} className="mb-0.5 rounded bg-emerald-50 px-2 py-1 text-xs text-gray-700">{c.title}</div>
          ))}
        </div>
      ) : null}

      {/* 资产变更 */}
      {archive.asset_changes.length > 0 ? (
        <div className="flex flex-wrap items-center gap-1">
          <span className={clsx(SECTION, 'text-violet-500')}>资产</span>
          {archive.asset_changes.map((a, i) => (
            <span key={i} className="rounded bg-violet-50 px-1.5 py-0.5 text-[11px] text-violet-700">
              {a.change}：{a.name}
            </span>
          ))}
        </div>
      ) : null}

      {/* 关系变更 */}
      {archive.relation_changes.length > 0 ? (
        <div>
          <div className={clsx(SECTION, 'mb-1 text-sky-500')}>关系变化</div>
          {archive.relation_changes.map((r, i) => (
            <div key={i} className="text-xs text-gray-700">
              {r.from} → {r.to}：<span className="text-sky-700">{r.attitude}</span>
              {r.reason ? <span className="text-[10px] text-gray-400">（{r.reason}）</span> : null}
            </div>
          ))}
        </div>
      ) : null}

      {/* 首次出场 */}
      {archive.first_appearances.length > 0 ? (
        <div className="flex flex-wrap items-center gap-1">
          <span className="text-[10px] text-gray-400">首次出场：</span>
          {archive.first_appearances.map((n, i) => (
            <span key={i} className="rounded bg-purple-50 px-1.5 py-0.5 text-[10px] text-purple-600">{n}</span>
          ))}
        </div>
      ) : null}

      {/* 连续性提示：无任何实际内容时 */}
      {archive.debriefed
        && archive.core_events.length === 0
        && !archive.summary ? (
          <p className="flex items-center gap-1 text-[11px] text-gray-400">
            <AlertTriangle size={10} /> 已复盘但未提取到核心事件
          </p>
        ) : null}
    </div>
  )
}
