/**
 * WeaveMatrixView — 故事线 × 卷张力热力图
 */
import clsx from 'clsx'
import type { WeaveMatrixOverview } from './useStorylineWeaveData'

function tensionColor(t: number, isActual = false): string {
  if (t <= 0) return 'bg-novel-panel text-novel-ink-faint'
  if (t < 30) return isActual ? 'bg-sky-100 text-sky-800' : 'bg-slate-100 text-slate-600'
  if (t < 60) return isActual ? 'bg-indigo-200 text-indigo-900' : 'bg-indigo-100 text-indigo-800'
  if (t < 85) return isActual ? 'bg-amber-200 text-amber-900' : 'bg-amber-100 text-amber-800'
  return isActual ? 'bg-rose-300 text-rose-950' : 'bg-rose-200 text-rose-900'
}

export default function WeaveMatrixView({ data }: { data: WeaveMatrixOverview }) {
  const cols = data.n_volumes

  return (
    <div className="space-y-6">
      {data.drift_alerts.length > 0 && (
        <div className="rounded-novel border border-amber-200 bg-amber-50/80 p-3">
          <p className="text-xs font-semibold text-amber-900 mb-2">漂移警报</p>
          <ul className="text-xs text-amber-800 space-y-1">
            {data.drift_alerts.map((a, i) => (
              <li key={`${a.storyline_id}-${a.vol_index}-${i}`}>
                {a.storyline_name} · 第{a.vol_index + 1}卷：{a.message}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="overflow-x-auto rounded-novel border border-novel-border">
        <table className="min-w-full text-xs">
          <thead>
            <tr className="bg-novel-panel border-b border-novel-border">
              <th className="text-left p-2 sticky left-0 bg-novel-panel z-10 min-w-[140px]">故事线</th>
              {Array.from({ length: cols }, (_, i) => (
                <th key={i} className="p-2 text-center min-w-[88px]">
                  <div className="font-medium">{data.volume_titles[i] || `卷${i + 1}`}</div>
                  <div className="text-[10px] text-novel-ink-faint font-normal">计划 / 实际</div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.storylines.map(row => (
              <tr key={row.id} className="border-b border-novel-border/60">
                <td className="p-2 sticky left-0 bg-novel-card z-10">
                  <div className="font-medium text-novel-ink truncate" title={row.name}>
                    {row.name}
                  </div>
                  <div className="text-[10px] text-novel-ink-faint">
                    {row.line_type}
                    {row.weight != null ? ` · ${(row.weight * 100).toFixed(0)}%` : ''}
                  </div>
                </td>
                {row.volume_cells.map(cell => (
                  <td key={cell.vol_index} className="p-1 align-top">
                    {!cell.is_active ? (
                      <div className="h-12 rounded bg-novel-panel/50 text-[10px] text-center text-novel-ink-faint flex items-center justify-center">
                        休眠
                      </div>
                    ) : (
                      <div className="space-y-0.5">
                        <div
                          className={clsx('rounded px-1 py-0.5 text-center font-mono', tensionColor(cell.planned_tension))}
                          title={cell.beat || ''}
                        >
                          {cell.planned_tension}
                        </div>
                        <div
                          className={clsx(
                            'rounded px-1 py-0.5 text-center font-mono text-[10px]',
                            cell.actual_tension != null
                              ? tensionColor(cell.actual_tension, true)
                              : 'bg-novel-panel text-novel-ink-faint',
                          )}
                        >
                          {cell.actual_tension ?? '—'}
                        </div>
                      </div>
                    )}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="text-[10px] text-novel-ink-faint">
        上格为计划张力，下格为复盘实际均值。颜色越深张力越高。需 Bootstrap Step 4 织网数据。
      </p>
    </div>
  )
}
