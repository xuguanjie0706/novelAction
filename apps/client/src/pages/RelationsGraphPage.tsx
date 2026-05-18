/**
 * 人物关系图独立页 — 侧栏「关系图」直达。
 */
import { useEffect } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Sparkles, Users } from 'lucide-react'
import { charactersApi } from '../api/client'
import RelationshipGraph from '../components/Characters/RelationshipGraph'
import { GRAPH_THEME } from '../components/Characters/RelationshipGraph/constants'
import { useAppStore } from '../store'

export default function RelationsGraphPage() {
  const { projectId } = useParams<{ projectId: string }>()
  const { characters, setCharacters } = useAppStore()

  useEffect(() => {
    if (!projectId) return
    charactersApi.list(projectId).then(res => setCharacters(res.data))
  }, [projectId, setCharacters])

  return (
    <div className="flex flex-col h-full min-h-0" style={{ background: GRAPH_THEME.canvasBg }}>
      <div
        className="flex items-center justify-between px-4 py-2.5 border-b shrink-0"
        style={{ borderColor: GRAPH_THEME.border, background: GRAPH_THEME.sidebarBg }}
      >
        <div className="flex items-center gap-2">
          <Sparkles size={16} style={{ color: GRAPH_THEME.accent }} />
          <span className="text-sm font-semibold" style={{ color: GRAPH_THEME.text }}>
            人物关系图
          </span>
          <span className="text-xs" style={{ color: GRAPH_THEME.textMuted }}>
            {characters.length} 人 · 3D 星图
          </span>
        </div>
        <Link
          to={`/project/${projectId}/characters`}
          className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border transition-colors"
          style={{ borderColor: GRAPH_THEME.border, color: GRAPH_THEME.text }}
        >
          <Users size={12} />
          人物库
        </Link>
      </div>
      <div className="flex-1 min-h-0 relative overflow-hidden">
        <RelationshipGraph projectId={projectId!} />
      </div>
    </div>
  )
}
