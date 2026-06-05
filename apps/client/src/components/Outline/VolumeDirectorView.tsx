/**
 * @file 卷级导演单展示（燃点 / 卷末高潮 / 节奏骨架 / 下卷悬念）
 */
import { Flame, Target, Sparkles, GitBranch, Clock, AlertCircle } from 'lucide-react'
import clsx from 'clsx'
import type { OutlineNode } from '../../types'
import {
  parseVolumeDirector,
  PHASE_LABEL,
  beatTypeLabel,
  formatBeatChapterHint,
  type VolumeDirectorData,
} from '../../utils/volumeBeatsDisplay'
import { Field } from '../../pages/Outline/shared/Field'

const PHASE_BADGE: Record<string, string> = {
  opening: 'bg-emerald-100 text-emerald-800',
  rising: 'bg-cyan-100 text-cyan-800',
  turning: 'bg-amber-100 text-amber-800',
  dark_hour: 'bg-violet-100 text-violet-800',
  climax: 'bg-red-100 text-red-800',
  ending: 'bg-purple-100 text-purple-800',
}

export interface VolumeDirectorForm {
  title: string
  summary: string
  conflict: string
  climaxSummary: string
  climaxChapter: string
  nextVolumeHook: string
  pacingSkeleton: string
  turningDescription: string
  turningChapter: string
}

export function volumeDirectorFormFromNode(
  node: OutlineNode,
  options?: { allVolumes?: OutlineNode[] },
): VolumeDirectorForm {
  const d = parseVolumeDirector(node, options)
  return {
    title: node.title ?? '',
    summary: node.summary ?? '',
    conflict: node.conflict ?? '',
    climaxSummary: d.climaxSummary,
    climaxChapter: d.volumeClimax?.chapter_hint ? String(d.volumeClimax.chapter_hint) : '',
    nextVolumeHook: node.hook ?? '',
    pacingSkeleton: d.pacingSkeleton,
    turningDescription: d.emotionalTurningPoint?.description ?? '',
    turningChapter: d.emotionalTurningPoint?.chapter_hint
      ? String(d.emotionalTurningPoint.chapter_hint)
      : '',
  }
}

export function buildVolumeDirectorSavePayload(
  node: OutlineNode,
  form: VolumeDirectorForm,
): Record<string, unknown> {
  const extra = { ...(node.extra ?? {}) }
  const climaxHint = parseInt(form.climaxChapter, 10)
  extra.volume_climax = {
    chapter_hint: Number.isFinite(climaxHint) && climaxHint > 0 ? climaxHint : undefined,
    description: form.climaxSummary.trim() || undefined,
  }
  if (form.pacingSkeleton.trim()) {
    extra.pacing_skeleton = form.pacingSkeleton.trim()
  }
  const turnHint = parseInt(form.turningChapter, 10)
  if (form.turningDescription.trim()) {
    extra.emotional_turning_point = {
      chapter_hint: Number.isFinite(turnHint) && turnHint > 0 ? turnHint : undefined,
      description: form.turningDescription.trim(),
    }
  }
  return {
    title: form.title,
    summary: form.summary,
    conflict: form.conflict,
    hook: form.nextVolumeHook.trim() || null,
    highlight: form.climaxSummary.trim() || null,
    extra,
  }
}

function MetaBadges({ d }: { d: VolumeDirectorData }) {
  const phase = d.phase
  const rangeHint = d.chapterStartGlobal > 1 && d.plannedChapters
    ? `全书约第${d.chapterStartGlobal}–${d.chapterStartGlobal + d.plannedChapters - 1}章`
    : null
  return (
    <div className="flex flex-wrap items-center gap-2 mb-3">
      {rangeHint && (
        <span className="text-[10px] text-sky-700 font-medium" title="节拍章号为卷内序号，此处为全书累计">
          {rangeHint}
        </span>
      )}
      {phase && (
        <span className={clsx(
          'text-[10px] font-bold px-2 py-0.5 rounded-full',
          PHASE_BADGE[phase] ?? 'bg-gray-100 text-gray-600',
        )}>
          {PHASE_LABEL[phase] ?? phase}
        </span>
      )}
      {d.plannedChapters != null && (
        <span className="text-[10px] text-gray-500">{d.plannedChapters} 章</span>
      )}
      {d.beatHighlights.length > 0 && (
        <span className="text-[10px] text-orange-600 font-medium">
          {d.beatHighlights.length} 处燃点
        </span>
      )}
      {d.volumeClimax?.chapter_hint != null && (
        <span className="text-[10px] text-red-600 font-medium">
          高潮 {formatBeatChapterHint(d.volumeClimax.chapter_hint, d.chapterStartGlobal)}
        </span>
      )}
      {d.protagonistRealmRange && (
        <span
          className="text-[10px] text-indigo-700 font-medium truncate max-w-[200px]"
          title={`主角境界：${d.protagonistRealmRange}`}
        >
          主角：{d.protagonistRealmRange}
        </span>
      )}
      {(d.volumeBoss || d.volumeBossRealm) && (
        <span
          className="text-[10px] text-gray-500 truncate max-w-[200px]"
          title={[d.volumeBoss, d.volumeBossRealm].filter(Boolean).join(' · ')}
        >
          BOSS：{d.volumeBoss || '—'}
          {d.volumeBossRealm ? `（${d.volumeBossRealm}）` : ''}
        </span>
      )}
    </div>
  )
}

function BeatList({
  beats,
  chapterStartGlobal,
}: {
  beats: VolumeDirectorData['beatHighlights']
  chapterStartGlobal: number
}) {
  if (beats.length === 0) return null
  return (
    <section>
      <SectionLabel
        icon={<Flame size={12} className="text-orange-500" />}
        title="燃点节拍"
        hint={chapterStartGlobal > 1 ? '章纲按本卷内章号兑现；标签已标全书章号' : '章纲展开须按章号兑现'}
      />
      <ul className="space-y-2">
        {beats.map((b, i) => (
          <li key={i} className="rounded-lg border border-orange-100 bg-orange-50/50 px-3 py-2">
            <div className="flex flex-wrap items-center gap-2 mb-1">
              <span className="text-[10px] font-bold text-orange-700">#{i + 1}</span>
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-orange-100 text-orange-800">
                {formatBeatChapterHint(b.chapter_hint, chapterStartGlobal)}
              </span>
              <span className="text-[10px] text-gray-500">{beatTypeLabel(b.beat_type)}</span>
            </div>
            <p className="text-xs text-gray-800 leading-relaxed">{b.description}</p>
            {b.payoff_of && (
              <p className="text-[10px] text-gray-500 mt-1">承接：{b.payoff_of}</p>
            )}
          </li>
        ))}
      </ul>
    </section>
  )
}

function SectionLabel({
  icon, title, hint,
}: {
  icon: React.ReactNode
  title: string
  hint?: string
}) {
  return (
    <div className="flex items-baseline gap-2 mb-1.5">
      {icon}
      <span className="text-xs font-semibold text-gray-700">{title}</span>
      {hint && <span className="text-[10px] text-gray-400">{hint}</span>}
    </div>
  )
}

function ReadBlock({ label, sublabel, children, accent }: {
  label: string
  sublabel?: string
  children: React.ReactNode
  accent?: 'purple' | 'red' | 'gray'
}) {
  const accentCls = accent === 'purple'
    ? 'border-violet-100 bg-violet-50/40 text-violet-900'
    : accent === 'red'
      ? 'border-red-100 bg-red-50/40 text-red-900'
      : 'border-gray-200 bg-gray-50 text-gray-700'
  return (
    <section>
      <SectionLabel
        icon={<Target size={12} className="text-gray-400" />}
        title={label}
        hint={sublabel}
      />
      <div className={clsx('rounded-lg border px-3 py-2 text-sm leading-relaxed', accentCls)}>
        {children}
      </div>
    </section>
  )
}

/** 大纲页「基础」Tab：卷级完整导演单（可编辑） */
export function VolumeDirectorPanel({
  node,
  editing,
  form,
  setForm,
  allVolumes,
}: {
  node: OutlineNode
  editing: boolean
  form: VolumeDirectorForm
  setForm: React.Dispatch<React.SetStateAction<VolumeDirectorForm>>
  /** 全书卷节点列表，用于推算全书章号（无 chapter_start_global 的旧数据） */
  allVolumes?: OutlineNode[]
}) {
  const d = parseVolumeDirector(node, { allVolumes })
  const localChapterHint = d.chapterStartGlobal > 1 ? '本卷内章号' : '章号'

  if (editing) {
    return (
      <div className="space-y-4">
        <Field label="标题" value={form.title} editing={editing} onChange={v => setForm(f => ({ ...f, title: v }))} singleLine />
        <Field label="情节摘要" sublabel="本卷核心剧情链" value={form.summary} editing={editing} onChange={v => setForm(f => ({ ...f, summary: v }))} />
        <Field label="核心冲突" sublabel="不可调和的矛盾" value={form.conflict} editing={editing} onChange={v => setForm(f => ({ ...f, conflict: v }))} />
        <div className="grid grid-cols-1 sm:grid-cols-[1fr_5rem] gap-3">
          <Field label="卷末高潮" sublabel="本卷情绪最高点场面" value={form.climaxSummary} editing={editing} onChange={v => setForm(f => ({ ...f, climaxSummary: v }))} />
          <Field label="高潮章" sublabel={localChapterHint} value={form.climaxChapter} editing={editing} onChange={v => setForm(f => ({ ...f, climaxChapter: v }))} singleLine />
        </div>
        {!d.hasDirectorBeats ? (
          <Field label="本卷追读悬念" sublabel="旧版 hook 字段（重新生成 Step 9 后将拆分为燃点+高潮）" value={form.nextVolumeHook} editing={editing} onChange={v => setForm(f => ({ ...f, nextVolumeHook: v }))} />
        ) : (
          <Field label="下卷悬念种子" sublabel="留给下一卷承接的悬念（hook 字段）" value={form.nextVolumeHook} editing={editing} onChange={v => setForm(f => ({ ...f, nextVolumeHook: v }))} />
        )}
        <Field
          label="节奏骨架"
          sublabel={d.chapterStartGlobal > 1 ? '本卷内章段（如 1-15章）' : '快/慢/打脸章段分布'}
          value={form.pacingSkeleton}
          editing={editing}
          onChange={v => setForm(f => ({ ...f, pacingSkeleton: v }))}
        />
        <div className="grid grid-cols-1 sm:grid-cols-[1fr_5rem] gap-3">
          <Field label="情感转折点" sublabel="主角认知/关系不可逆变化（可选）" value={form.turningDescription} editing={editing} onChange={v => setForm(f => ({ ...f, turningDescription: v }))} />
          <Field label="转折章" sublabel={localChapterHint} value={form.turningChapter} editing={editing} onChange={v => setForm(f => ({ ...f, turningChapter: v }))} singleLine />
        </div>
        {d.beatHighlights.length > 0 && (
          <p className="text-[11px] text-gray-400 flex items-start gap-1">
            <AlertCircle size={12} className="shrink-0 mt-0.5" />
            燃点列表由 Bootstrap Step 9 生成，编辑请重新生成卷骨架或在后续版本支持手动改 extra。
          </p>
        )}
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <MetaBadges d={d} />
      {d.protagonistRealmRange && (
        <ReadBlock label="主角境界" sublabel="本卷初 → 卷末（Step 9 战力曲线）" accent="gray">
          {d.protagonistRealmRange}
        </ReadBlock>
      )}
      <Field label="标题" value={node.title ?? ''} editing={false} onChange={() => {}} singleLine />
      {node.summary && (
        <ReadBlock label="情节摘要" sublabel="本卷核心剧情">
          {node.summary}
        </ReadBlock>
      )}
      {node.conflict && (
        <ReadBlock label="核心冲突" sublabel="本卷矛盾引擎">
          {node.conflict}
        </ReadBlock>
      )}
      <BeatList beats={d.beatHighlights} chapterStartGlobal={d.chapterStartGlobal} />
      {d.climaxSummary && (
        <ReadBlock
          label="卷末高潮"
          sublabel={d.volumeClimax?.chapter_hint
            ? formatBeatChapterHint(d.volumeClimax.chapter_hint, d.chapterStartGlobal)
            : '情绪最高点'}
          accent="red"
        >
          {d.climaxSummary}
        </ReadBlock>
      )}
      {d.emotionalTurningPoint?.description && (
        <ReadBlock
          label="情感转折"
          sublabel={d.emotionalTurningPoint.chapter_hint
            ? formatBeatChapterHint(d.emotionalTurningPoint.chapter_hint, d.chapterStartGlobal)
            : undefined}
        >
          {d.emotionalTurningPoint.description}
        </ReadBlock>
      )}
      {d.mustPayoffs.length > 0 && (
        <section>
          <SectionLabel icon={<GitBranch size={12} className="text-green-600" />} title="卷末前必兑现" />
          <ul className="list-disc pl-5 text-xs text-gray-700 space-y-1">
            {d.mustPayoffs.map((p, i) => <li key={i}>{p}</li>)}
          </ul>
        </section>
      )}
      {d.pacingSkeleton && (
        <ReadBlock
          label="节奏骨架"
          sublabel={d.chapterStartGlobal > 1 ? '全书章段（由本卷内序号换算）' : '全卷快慢分布'}
          accent="gray"
        >
          <span className="flex items-center gap-1.5 text-xs">
            <Clock size={11} className="shrink-0 opacity-60" />
            {d.pacingSkeletonDisplay}
          </span>
        </ReadBlock>
      )}
      {d.legacyReaderHook && (
        <ReadBlock label="本卷追读悬念" sublabel="（旧版数据，建议重新生成 Step 9）" accent="purple">
          {d.legacyReaderHook}
        </ReadBlock>
      )}
      {d.nextVolumeHook && (
        <ReadBlock label="下卷悬念种子" sublabel="hook 字段 · 承上启下" accent="purple">
          {d.nextVolumeHook}
        </ReadBlock>
      )}
      {!d.hasDirectorBeats && !d.legacyReaderHook && (
        <p className="text-xs text-gray-400 italic flex items-center gap-1">
          <Sparkles size={12} />
          暂无导演单节拍数据，请重新运行 Bootstrap Step 9 或展开章纲后由 AI 补全。
        </p>
      )}
    </div>
  )
}

/** 书架/详情页卷卡片（紧凑） */
export function VolumeDirectorCard({
  vol,
  index,
  chapterCount,
  variant = 'inline',
  allVolumes,
}: {
  vol: OutlineNode
  index: number
  chapterCount?: number
  variant?: 'inline' | 'tailwind'
  allVolumes?: OutlineNode[]
}) {
  const d = parseVolumeDirector(vol, { allVolumes })
  const phase = d.phase

  if (variant === 'inline') {
    return (
      <VolumeDirectorCardInline vol={vol} d={d} index={index} chapterCount={chapterCount} phase={phase} />
    )
  }
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-3">
      <VolumeDirectorCardBody vol={vol} d={d} index={index} chapterCount={chapterCount} phase={phase} />
    </div>
  )
}

function VolumeDirectorCardInline({
  vol, d, index, chapterCount, phase,
}: {
  vol: OutlineNode
  d: ReturnType<typeof parseVolumeDirector>
  index: number
  chapterCount?: number
  phase?: string
}) {
  const S = {
    tiny: { fontSize: 11, color: '#6b7280' } as const,
    muted: { fontSize: 13, color: '#4b5563', lineHeight: 1.55, margin: 0 } as const,
    text: { fontSize: 13, color: '#111827' } as const,
    badge: (c: string) => ({
      fontSize: 10, fontWeight: 700, padding: '2px 8px', borderRadius: 999,
      background: `${c}22`, color: c,
    } as const),
  }
  const phaseColors: Record<string, string> = {
    opening: '#22c55e', rising: '#06b6d4', turning: '#f59e0b',
    dark_hour: '#a78bfa', climax: '#ef4444', ending: '#8b5cf6',
  }

  return (
    <>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6, flexWrap: 'wrap' }}>
        <span style={{ ...S.tiny, width: 36 }}>第{index + 1}卷</span>
        <strong style={S.text}>{vol.title}</strong>
        {phase && (
          <span style={{ ...S.badge(phaseColors[phase] ?? '#6b7280'), marginLeft: 'auto' }}>
            {PHASE_LABEL[phase] ?? phase}
          </span>
        )}
        {chapterCount != null && chapterCount > 0 && <span style={S.tiny}>{chapterCount} 章</span>}
        {d.beatHighlights.length > 0 && (
          <span style={{ ...S.tiny, color: '#ea580c' }}>{d.beatHighlights.length} 燃点</span>
        )}
      </div>
      {(d.protagonistRealmRange || d.volumeBoss || d.volumeBossRealm) && (
        <p style={{ ...S.tiny, marginBottom: 6, color: '#4338ca' }}>
          {d.protagonistRealmRange ? `主角：${d.protagonistRealmRange}` : null}
          {d.protagonistRealmRange && (d.volumeBoss || d.volumeBossRealm) ? ' · ' : null}
          {(d.volumeBoss || d.volumeBossRealm) && (
            <span style={{ color: '#6b7280' }}>
              BOSS：{d.volumeBoss || '—'}
              {d.volumeBossRealm ? `（${d.volumeBossRealm}）` : ''}
            </span>
          )}
        </p>
      )}
      <VolumeDirectorCardBodyContent d={d} vol={vol} styles={S} />
    </>
  )
}

function VolumeDirectorCardBody({
  vol, d, index, chapterCount, phase,
}: {
  vol: OutlineNode
  d: ReturnType<typeof parseVolumeDirector>
  index: number
  chapterCount?: number
  phase?: string
}) {
  return (
    <>
      <div className="flex flex-wrap items-center gap-2 mb-2">
        <span className="text-[11px] text-gray-400">第{index + 1}卷</span>
        <strong className="text-sm text-gray-900">{vol.title}</strong>
        {phase && (
          <span className={clsx('text-[10px] font-bold px-2 py-0.5 rounded-full ml-auto', PHASE_BADGE[phase] ?? 'bg-gray-100')}>
            {PHASE_LABEL[phase]}
          </span>
        )}
        {chapterCount != null && chapterCount > 0 && (
          <span className="text-[10px] text-gray-400">{chapterCount} 章</span>
        )}
      </div>
      {(d.protagonistRealmRange || d.volumeBoss || d.volumeBossRealm) && (
        <p className="text-[11px] text-indigo-800 mb-2 leading-snug">
          {d.protagonistRealmRange ? (
            <span className="font-medium">主角：{d.protagonistRealmRange}</span>
          ) : null}
          {d.protagonistRealmRange && (d.volumeBoss || d.volumeBossRealm) ? (
            <span className="text-gray-400 mx-1.5">·</span>
          ) : null}
          {(d.volumeBoss || d.volumeBossRealm) && (
            <span className="text-gray-600">
              BOSS：{d.volumeBoss || '—'}
              {d.volumeBossRealm ? `（${d.volumeBossRealm}）` : ''}
            </span>
          )}
        </p>
      )}
      <VolumeDirectorCardBodyContent d={d} vol={vol} />
    </>
  )
}

function VolumeDirectorCardBodyContent({
  d, vol, styles,
}: {
  d: ReturnType<typeof parseVolumeDirector>
  vol: OutlineNode
  styles?: {
    muted: React.CSSProperties
    tiny: React.CSSProperties
  }
}) {
  const mutedCls = styles ? undefined : 'text-xs text-gray-600 leading-relaxed'
  const tinyPurple = styles
    ? { ...styles.tiny, marginTop: 6, color: '#7c3aed' }
    : undefined
  const tinyRed = styles
    ? { ...styles.tiny, marginTop: 6, color: '#b91c1c' }
    : undefined

  return (
    <>
      {vol.summary && (
        styles
          ? <p style={styles.muted}>{vol.summary}</p>
          : <p className={mutedCls}>{vol.summary}</p>
      )}
      {d.beatHighlights.slice(0, 3).map((b, i) => (
        styles ? (
          <p key={i} style={{ ...styles.tiny, marginTop: 4, color: '#c2410c' }}>
            燃·{formatBeatChapterHint(b.chapter_hint, d.chapterStartGlobal)}：{b.description.slice(0, 60)}{b.description.length > 60 ? '…' : ''}
          </p>
        ) : (
          <p key={i} className="text-[11px] text-orange-700 mt-1">
            燃·{formatBeatChapterHint(b.chapter_hint, d.chapterStartGlobal)}：{b.description.slice(0, 60)}{b.description.length > 60 ? '…' : ''}
          </p>
        )
      ))}
      {d.climaxSummary && (
        styles
          ? <p style={tinyRed}>高潮{d.volumeClimax?.chapter_hint ? `·${formatBeatChapterHint(d.volumeClimax.chapter_hint, d.chapterStartGlobal)}` : ''}：{d.climaxSummary}</p>
          : <p className="text-[11px] text-red-700 mt-1.5">高潮{d.volumeClimax?.chapter_hint ? `·${formatBeatChapterHint(d.volumeClimax.chapter_hint, d.chapterStartGlobal)}` : ''}：{d.climaxSummary}</p>
      )}
      {d.legacyReaderHook && (
        styles
          ? <p style={tinyPurple}>追读悬念：{d.legacyReaderHook}</p>
          : <p className="text-[11px] text-violet-700 mt-1.5">追读悬念：{d.legacyReaderHook}</p>
      )}
      {d.nextVolumeHook && (
        styles
          ? <p style={tinyPurple}>下卷悬念：{d.nextVolumeHook}</p>
          : <p className="text-[11px] text-violet-700 mt-1.5">下卷悬念：{d.nextVolumeHook}</p>
      )}
      {vol.conflict && (
        styles
          ? <p style={{ ...styles.tiny, marginTop: 4 }}>冲突：{vol.conflict}</p>
          : <p className="text-[11px] text-gray-500 mt-1">冲突：{vol.conflict}</p>
      )}
      {d.pacingSkeleton && (
        styles
          ? <p style={{ ...styles.tiny, marginTop: 4, fontStyle: 'italic' }}>节奏：{d.pacingSkeleton}</p>
          : <p className="text-[10px] text-gray-400 mt-1 italic">节奏：{d.pacingSkeleton}</p>
      )}
    </>
  )
}
