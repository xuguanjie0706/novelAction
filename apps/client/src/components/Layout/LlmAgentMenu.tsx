import React, { useEffect, useMemo } from 'react'
import { Cpu } from 'lucide-react'
import { llmApi } from '../../api/client'
import { useAppStore } from '../../store'
import type { LlmOverview } from '../../types'

/**
 * 顶部栏：单一「模型 / 线路」下拉（本地 + 各条启用的远程 LlmProvider）。
 */
export default function LlmAgentMenu() {
  const aiBackendRoute = useAppStore(s => s.aiBackendRoute)
  const setAiBackendRoute = useAppStore(s => s.setAiBackendRoute)
  const [data, setData] = React.useState<LlmOverview | null>(null)
  const [loading, setLoading] = React.useState(true)

  const load = () => {
    setLoading(true)
    llmApi
      .overview()
      .then(res => {
        setData(res.data)
        setLoading(false)
      })
      .catch(() => {
        setData(null)
        setLoading(false)
      })
  }

  useEffect(() => {
    load()
  }, [])

  // 列表刷新后：纠正失效的 remote:<uuid>；把裸 `remote` 收敛到具体 provider（便于展示）
  useEffect(() => {
    if (!data?.remote_providers?.length) return
    const r = useAppStore.getState().aiBackendRoute
    const pick = () =>
      data.remote_providers!.find(p => p.is_default) ?? data.remote_providers![0]

    if (r === 'remote') {
      const def = pick()
      setAiBackendRoute(`remote:${def.id}`)
      return
    }
    if (r.startsWith('remote:')) {
      const id = r.slice('remote:'.length)
      const ok = data.remote_providers.some(p => p.id === id)
      if (!ok) {
        const def = pick()
        setAiBackendRoute(`remote:${def.id}`)
      }
    }
  }, [data, setAiBackendRoute])

  useEffect(() => {
    if (loading || !data) return
    const r = useAppStore.getState().aiBackendRoute
    const hasDb = (data.remote_providers?.length ?? 0) > 0
    if (r !== 'local' && !data.remote_ready && !hasDb) {
      setAiBackendRoute('local')
      return
    }
    // 仅环境变量远程、无 DB 行时，不应保留无效的 remote:<uuid>
    if (!hasDb && data.remote_ready && r.startsWith('remote:')) {
      setAiBackendRoute('remote')
    }
  }, [loading, data, setAiBackendRoute])

  const selectValue = useMemo(() => {
    if (aiBackendRoute === 'local') return 'local'
    if (aiBackendRoute.startsWith('remote:')) return aiBackendRoute
    if (aiBackendRoute === 'remote') return 'remote'
    return 'local'
  }, [aiBackendRoute])

  const warn = useMemo(() => {
    if (loading) return false
    if (!data) return true
    if (selectValue === 'local') return false
    if (selectValue === 'remote') return !data.remote_ready
    return !data.remote_ready
  }, [loading, data, selectValue])

  return (
    <div className="flex items-center gap-1.5 rounded-lg border border-gray-200 bg-gray-50/80 px-2 py-1 min-w-0">
      <Cpu size={13} className="text-gray-500 shrink-0" aria-hidden />
      <label htmlFor="global-ai-route" className="sr-only">
        创作使用的模型线路
      </label>
      <select
        id="global-ai-route"
        value={selectValue}
        disabled={loading && !data}
        onChange={e => setAiBackendRoute(e.target.value)}
        title="全局模型：正文起笔、AI 助手、大纲展开等均使用此项"
        className={[
          'min-w-0 flex-1 max-w-[11rem] sm:max-w-[20rem] text-xs bg-transparent border-0 py-0.5 pl-0 pr-1',
          'text-gray-700 focus:outline-none focus:ring-0 cursor-pointer truncate',
          warn ? 'text-amber-800' : '',
        ].join(' ')}
      >
        <option value="local">
          {loading ? '本地…' : `本地 · ${data?.local_model_name ?? '默认'}`}
        </option>
        {!loading &&
          data?.remote_providers?.map(p => (
            <option key={p.id} value={`remote:${p.id}`}>
              远程 · {p.name} 
            </option>
          ))}
        {!loading && data?.remote_ready && (data.remote_providers?.length ?? 0) === 0 && (
          <option value="remote">
            远程 · 环境变量 ({data.effective_remote_model ?? '—'})
          </option>
        )}
        {!loading && !data?.remote_ready && (data?.remote_providers?.length ?? 0) === 0 && (
          <option value="remote" disabled>
            远程（未配置）
          </option>
        )}
      </select>
    </div>
  )
}
