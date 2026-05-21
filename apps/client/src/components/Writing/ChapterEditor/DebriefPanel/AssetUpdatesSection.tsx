/**
 * @file 复盘 — 资产变化勾选区
 */
import { Flag } from 'lucide-react'
import type { useDebriefAssets } from './useDebriefAssets'

type AssetHook = ReturnType<typeof useDebriefAssets>

export interface AssetUpdatesSectionProps {
  assetSections: AssetHook['assetSections']
  assetSelections: AssetHook['assetSelections']
  setAssetSelections: AssetHook['setAssetSelections']
  selectedAssetCount: number
  totalAssetCount: number
}

export function AssetUpdatesSection({
  assetSections,
  assetSelections,
  setAssetSelections,
  selectedAssetCount,
  totalAssetCount,
}: AssetUpdatesSectionProps) {
  if (assetSections.length === 0) return null

  return (
    <section>
      <div className="flex items-center justify-between gap-2 mb-2">
        <div className="flex items-center gap-1.5">
          <Flag size={11} className="text-novel-ink-muted" />
          <span className="text-[10px] font-semibold text-novel-ink-muted uppercase tracking-wider">
            资产变化（可勾选提交）
          </span>
          <span className="text-[10px] text-novel-ink-faint">
            {selectedAssetCount}/{totalAssetCount}
          </span>
        </div>
        <button
          type="button"
          onClick={() => {
            const allSelected = selectedAssetCount === totalAssetCount && totalAssetCount > 0
            setAssetSelections(prev => {
              const next = { ...prev }
              for (const section of assetSections) {
                next[section.key] = section.items.map(() => !allSelected)
              }
              return next
            })
          }}
          className="text-[10px] px-2 py-1 rounded border border-novel-border bg-white text-novel-ink-muted hover:bg-novel-panel transition-novel"
        >
          {selectedAssetCount === totalAssetCount && totalAssetCount > 0 ? '全部取消' : '全部勾选'}
        </button>
      </div>

      <div className="space-y-2.5">
        {assetSections.map(section => (
          <div key={section.key} className="rounded-novel border border-novel-border bg-novel-card px-3 py-2.5">
            <div className="text-[10px] font-semibold text-novel-ink-muted mb-1.5">{section.label}</div>
            <div className="space-y-1">
              {section.items.map((item, idx) => {
                const row = item as Record<string, unknown>
                const name = String(
                  row.name
                  || row.item_name
                  || row.skill_name
                  || row.faction_name
                  || `${section.label}#${idx + 1}`,
                )
                const note = String(
                  row.reason_to_store
                  || row.event_note
                  || row.story_significance
                  || row.effects
                  || row.goals
                  || '',
                )
                const checked = assetSelections[section.key]?.[idx] ?? false
                return (
                  <label key={`${section.key}-${idx}`} className="flex items-start gap-2 text-[11px] text-novel-ink">
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={e => {
                        const { checked: nextChecked } = e.target
                        setAssetSelections(prev => {
                          const sectionFlags = [...(prev[section.key] || section.items.map(() => true))]
                          sectionFlags[idx] = nextChecked
                          return { ...prev, [section.key]: sectionFlags }
                        })
                      }}
                      className="mt-0.5"
                    />
                    <span className="leading-relaxed">
                      <span className="font-medium">{name}</span>
                      {note && <span className="text-novel-ink-faint"> · {note}</span>}
                    </span>
                  </label>
                )
              })}
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}
