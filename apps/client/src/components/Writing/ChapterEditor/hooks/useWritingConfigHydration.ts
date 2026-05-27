/**
 * useWritingConfigHydration — 拉取并写入 currentProject.extra.writing_config
 */
import { useEffect } from 'react'
import { projectsApi, type WritingConfig } from '../../../../api/client'
import { useAppStore } from '../../../../store'

/** 从 store 读取写作门控配置；缺失时后台补拉一次。 */
export function useWritingConfigHydration(projectId: string) {
  const currentProject = useAppStore(s => s.currentProject)
  const setCurrentProject = useAppStore(s => s.setCurrentProject)

  const writingConfig = useAppStore(s => {
    const ex = (s.currentProject as { extra?: Record<string, unknown> } | null)?.extra
    return ex && typeof ex === 'object' ? (ex.writing_config as WritingConfig | null ?? null) : null
  })

  useEffect(() => {
    if (!projectId || currentProject?.id !== projectId) return
    const ex = (currentProject.extra as Record<string, unknown> | undefined) ?? {}
    if (ex.writing_config && typeof ex.writing_config === 'object') return
    projectsApi.getWritingConfig(projectId)
      .then(res => {
        const cp = useAppStore.getState().currentProject
        if (!cp || cp.id !== projectId) return
        setCurrentProject({
          ...cp,
          extra: {
            ...((cp.extra as Record<string, unknown>) ?? {}),
            writing_config: res.data.writing_config,
          } as typeof cp.extra,
        })
      })
      .catch(() => { /* 静默；门控退化为关闭 */ })
  }, [projectId, currentProject?.id, currentProject?.extra, setCurrentProject])

  return writingConfig
}
