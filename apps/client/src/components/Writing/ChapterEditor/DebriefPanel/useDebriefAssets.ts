/**
 * @file 复盘资产变化勾选状态
 */
import { useEffect, useMemo, useState } from 'react'
import { ASSET_UPDATE_LABELS } from './constants'

export function useDebriefAssets(aiSuggestedAssetUpdates: Record<string, unknown> | null | undefined) {
  const assetSections = useMemo(() => {
    const source = aiSuggestedAssetUpdates || {}
    return Object.entries(ASSET_UPDATE_LABELS)
      .map(([key, label]) => {
        const list = source[key]
        return {
          key,
          label,
          items: Array.isArray(list) ? list.filter(item => typeof item === 'object' && item !== null) : [],
        }
      })
      .filter(section => section.items.length > 0)
  }, [aiSuggestedAssetUpdates])

  const [assetSelections, setAssetSelections] = useState<Record<string, boolean[]>>({})

  useEffect(() => {
    const nextSelections: Record<string, boolean[]> = {}
    for (const section of assetSections) {
      nextSelections[section.key] = section.items.map(() => true)
    }
    setAssetSelections(nextSelections)
  }, [assetSections])

  const totalAssetCount = assetSections.reduce((sum, section) => sum + section.items.length, 0)
  const selectedAssetCount = assetSections.reduce((sum, section) => {
    const flags = assetSelections[section.key] || []
    return sum + flags.filter(Boolean).length
  }, 0)

  const buildSelectedAssetUpdates = (): Record<string, unknown> | undefined => {
    const picked: Record<string, unknown> = {}
    for (const section of assetSections) {
      const flags = assetSelections[section.key] || []
      const selectedItems = section.items.filter((_, idx) => flags[idx])
      if (selectedItems.length > 0) picked[section.key] = selectedItems
    }
    return Object.keys(picked).length > 0 ? picked : undefined
  }

  return {
    assetSections,
    assetSelections,
    setAssetSelections,
    totalAssetCount,
    selectedAssetCount,
    buildSelectedAssetUpdates,
  }
}
