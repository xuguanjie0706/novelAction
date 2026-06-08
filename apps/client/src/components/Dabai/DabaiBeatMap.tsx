/**
 * @file DabaiBeatMap — 大白文双轨地图：境界脊柱 + 爽点节拍带。
 * 数据来自 DabaiProjectDetail（卷区间 realm_start/end、章 realm_rank、shuang_type）。
 */
import { Layers, Flame } from 'lucide-react'
import type { DabaiChapter, DabaiProjectDetail, DabaiVolume } from '../../types/dabai'

const SHUANG_COLOR: Record<string, string> = {
  打脸: '#fb7185', 升级: '#fbbf24', 获宝: '#34d399', 扮猪吃虎: '#a78bfa',
  装逼: '#38bdf8', 群嘲反转: '#f472b6', 收小弟: '#2dd4bf', 救场: '#fb923c', 扬名: '#818cf8',
}

function realmLabel(levels: DabaiProjectDetail['power_ladder']['levels'], rank: number): string {
  const lv = levels?.find((l) => l.rank === rank)
  return lv ? lv.name : `第${rank}档`
}

/** 按卷切分章纲（大白文默认只展开第 1 卷，其余卷仅展示区间带）。 */
function chaptersByVolume(chapters: DabaiChapter[], volumes: DabaiVolume[]) {
  if (!volumes.length) return [{ vol: null as DabaiVolume | null, chapters }]
  const sorted = [...volumes].sort((a, b) => a.volume_number - b.volume_number)
  let cursor = 1
  return sorted.map((vol) => {
    const n = vol.planned_chapters ?? 0
    const slice = chapters.filter((c) => c.chapter_number >= cursor && c.chapter_number < cursor + n)
    cursor += n
    return { vol, chapters: slice }
  })
}

function RealmSpineChart({
  detail,
  groups,
}: {
  detail: DabaiProjectDetail
  groups: ReturnType<typeof chaptersByVolume>
}) {
  const levels = detail.power_ladder?.levels ?? []
  if (!levels.length && !detail.chapter_outlines.some((c) => c.realm_rank)) return null

  const ranks = levels.length
    ? [...levels].sort((a, b) => a.rank - b.rank).map((l) => l.rank)
    : [...new Set(detail.chapter_outlines.map((c) => c.realm_rank).filter(Boolean) as number[])].sort((a, b) => a - b)

  const maxRank = ranks.length ? Math.max(...ranks) : 1
  const minRank = ranks.length ? Math.min(...ranks) : 1
  const span = Math.max(maxRank - minRank, 1)

  const W = 640
  const H = 160
  const padL = 72
  const padR = 12
  const padT = 20
  const padB = 28
  const plotW = W - padL - padR
  const plotH = H - padT - padB

  const yOf = (rank: number) => padT + plotH - ((rank - minRank) / span) * plotH

  const totalCols = groups.reduce((s, g) => s + Math.max(g.chapters.length, 1), 0)
  let col = 0

  return (
    <div className="overflow-x-auto">
      <svg viewBox={`0 0 ${W} ${H}`} className="min-w-[520px] w-full h-auto">
        {/* Y 轴档位 */}
        {ranks.map((r) => (
          <g key={r}>
            <line x1={padL} y1={yOf(r)} x2={W - padR} y2={yOf(r)} stroke="#e5e7eb" strokeDasharray="4 4" />
            <text x={padL - 6} y={yOf(r) + 4} textAnchor="end" className="fill-gray-500 text-[9px]">
              {realmLabel(levels, r)}
            </text>
          </g>
        ))}

        {/* 卷区间带 */}
        {groups.map(({ vol, chapters: chs }, gi) => {
          const cols = Math.max(chs.length, 1)
          const x0 = padL + (col / totalCols) * plotW
          col += cols
          const x1 = padL + (col / totalCols) * plotW
          if (!vol?.realm_start_rank || !vol.realm_end_rank) return null
          const yTop = yOf(vol.realm_end_rank)
          const yBot = yOf(vol.realm_start_rank)
          return (
            <g key={gi}>
              <rect
                x={x0} y={Math.min(yTop, yBot)} width={x1 - x0} height={Math.abs(yBot - yTop) || 4}
                fill="#eef2ff" stroke="#c7d2fe" strokeWidth={0.5} rx={4}
              />
              <text x={(x0 + x1) / 2} y={H - 8} textAnchor="middle" className="fill-indigo-600 text-[9px] font-medium">
                第{vol.volume_number}卷
              </text>
            </g>
          )
        })}

        {/* 章节点 + 折线 */}
        {(() => {
          col = 0
          const pts: { x: number; y: number; ch: DabaiChapter }[] = []
          groups.forEach(({ chapters: chs }) => {
            const cols = Math.max(chs.length, 1)
            chs.forEach((ch, i) => {
              if (!ch.realm_rank) return
              const x = padL + ((col + i + 0.5) / totalCols) * plotW
              pts.push({ x, y: yOf(ch.realm_rank), ch })
            })
            col += cols
          })
          const d = pts.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ')
          return (
            <>
              {d && <path d={d} fill="none" stroke="#6366f1" strokeWidth={1.5} opacity={0.7} />}
              {pts.map((p) => (
                <g key={p.ch.chapter_number}>
                  <circle cx={p.x} cy={p.y} r={p.ch.is_big_beat ? 5 : 3.5} fill={p.ch.is_big_beat ? '#f59e0b' : '#4f46e5'} />
                  <title>{`第${p.ch.chapter_number}章 ${realmLabel(levels, p.ch.realm_rank!)}`}</title>
                </g>
              ))}
            </>
          )
        })()}
      </svg>
    </div>
  )
}

function ShuangStrip({ chapters }: { chapters: DabaiChapter[] }) {
  if (!chapters.length) return null
  return (
    <div className="flex gap-px overflow-x-auto rounded-lg border border-gray-100 bg-gray-50 p-1">
      {chapters.map((ch) => (
        <div
          key={ch.chapter_number}
          title={`第${ch.chapter_number}章 · ${ch.shuang_type}${ch.is_big_beat ? ' · 大爆点' : ''}`}
          className="relative h-8 min-w-[10px] flex-1 rounded-sm"
          style={{ backgroundColor: SHUANG_COLOR[ch.shuang_type] ?? '#d1d5db', opacity: ch.is_big_beat ? 1 : 0.85 }}
        >
          {ch.is_big_beat && (
            <span className="absolute -top-1 left-1/2 -translate-x-1/2 text-[8px] text-amber-700">★</span>
          )}
        </div>
      ))}
    </div>
  )
}

export default function DabaiBeatMap({ detail }: { detail: DabaiProjectDetail }) {
  const chapters = detail.chapter_outlines ?? []
  const volumes = detail.volumes ?? []
  if (!chapters.length && !volumes.some((v) => v.realm_start_rank)) return null

  const groups = chaptersByVolume(chapters, volumes)

  return (
    <section className="rounded-2xl border border-indigo-100 bg-white p-5 shadow-sm">
      <div className="mb-4 flex items-center gap-2 text-sm font-bold text-gray-900">
        <Layers size={15} className="text-indigo-500" />
        境界脊柱 · 爽点节拍图
        <span className="ml-1 text-xs font-normal text-gray-400">非地理 Location；大白文 REALM 闸门可视化</span>
      </div>

      <div className="mb-1 flex items-center gap-1.5 text-xs font-semibold text-indigo-700">
        <Layers size={12} /> 境界脊柱（卷区间带 + 章节点折线）
      </div>
      <RealmSpineChart detail={detail} groups={groups} />

      <div className="mt-4 mb-1.5 flex items-center gap-1.5 text-xs font-semibold text-rose-700">
        <Flame size={12} /> 爽点节拍带（色块=爽点类型，★=大爆点）
      </div>
      <ShuangStrip chapters={chapters} />

      <div className="mt-3 flex flex-wrap gap-2 text-[10px] text-gray-500">
        {Object.entries(SHUANG_COLOR).map(([k, c]) => (
          <span key={k} className="inline-flex items-center gap-1">
            <span className="h-2 w-2 rounded-sm" style={{ backgroundColor: c }} />{k}
          </span>
        ))}
      </div>
    </section>
  )
}
