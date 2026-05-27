/**
 * useStorylineWeaveData — 拉取故事线织网矩阵 API
 */
import { useCallback, useEffect, useState } from 'react'
import { storylinesApi } from '../../api/client'

export type WeaveVolumeCell = {
  vol_index: number
  planned_tension: number
  actual_tension: number | null
  beat?: string
  is_active?: boolean
}

export type WeaveStorylineRow = {
  id: string
  name: string
  line_type: string
  weight?: number
  tension_curve: number[]
  volume_cells: WeaveVolumeCell[]
  crossover_nodes: Array<Record<string, unknown>>
}

export type WeaveMatrixOverview = {
  n_volumes: number
  volume_titles: string[]
  storylines: WeaveStorylineRow[]
  drift_alerts: Array<{
    storyline_id: string
    storyline_name: string
    vol_index: number
    message: string
  }>
}

export function useStorylineWeaveData(projectId: string) {
  const [data, setData] = useState<WeaveMatrixOverview | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(() => {
    if (!projectId) return
    setLoading(true)
    setError(null)
    void storylinesApi.weaveMatrix(projectId)
      .then(r => setData(r.data as WeaveMatrixOverview))
      .catch(e => setError(e?.message || '加载失败'))
      .finally(() => setLoading(false))
  }, [projectId])

  useEffect(() => {
    refresh()
  }, [refresh])

  return { data, loading, error, refresh }
}
