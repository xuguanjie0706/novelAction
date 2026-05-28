import { useCallback } from 'react'
import toast from 'react-hot-toast'
import type { Project } from '../types'

type SidebarTarget =
  | 'home'
  | 'projects'
  | 'write'
  | 'memory'
  | 'characters'
  | 'outline'
  | 'coherence'
  | 'stats'
  | 'wallet'
  | 'trash'
  | 'fanqie'

type ProjectTabTarget = 'write' | 'memory' | 'characters' | 'outline'

interface UseHomeSidebarNavigateOptions {
  projects: Project[]
  activeId?: SidebarTarget
  onHome?: () => void
  navigate: (to: string) => void
  setCurrentProject: (project: Project) => void
}

/**
 * 统一 HomeSidebar 导航行为，避免各页面 targetMap 漂移。
 */
export function useHomeSidebarNavigate({
  projects,
  activeId,
  onHome,
  navigate,
  setCurrentProject,
}: UseHomeSidebarNavigateOptions) {
  const gotoProjectTab = useCallback((tab: ProjectTabTarget) => {
    const firstProject = projects[0]
    if (!firstProject) {
      toast('还没有小说，先新建一部吧')
      return
    }
    setCurrentProject(firstProject)
    navigate(`/project/${firstProject.id}/${tab}`)
  }, [navigate, projects, setCurrentProject])

  return useCallback((target: string) => {
    const navTarget = target as SidebarTarget
    if (activeId && navTarget === activeId) return

    switch (navTarget) {
      case 'home':
        if (onHome) onHome()
        else navigate('/')
        return
      case 'projects':
        navigate('/bookshelf')
        return
      case 'write':
      case 'memory':
      case 'characters':
      case 'outline':
        gotoProjectTab(navTarget)
        return
      case 'coherence':
        navigate('/coherence-check')
        return
      case 'stats':
        navigate('/stats')
        return
      case 'wallet':
        navigate('/wallet')
        return
      case 'fanqie':
        navigate('/fanqie')
        return
      case 'trash':
        toast('回收站暂无内容')
        return
      default:
        toast('功能建设中')
    }
  }, [activeId, gotoProjectTab, navigate, onHome])
}
