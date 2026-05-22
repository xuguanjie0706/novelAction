/**
 * @file 人物页：列表筛选、分组、CRUD 与视图切换
 */
import { useEffect, useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import toast from 'react-hot-toast'
import { charactersApi } from '../../api/client'
import { useAppStore } from '../../store'
import type { Character } from '../../types'
import {
  ROLE_META,
  type RoleFilter,
  type StatusFilter,
  type TierFilter,
  type GroupBy,
} from './shared/constants'
import type { CharacterGroup } from './CharacterList'

export function useCharactersPage() {
  const { projectId } = useParams<{ projectId: string }>()
  const { characters, setCharacters, upsertCharacter, removeCharacter } = useAppStore()
  const [selected, setSelected] = useState<Character | null>(null)
  const [creating, setCreating] = useState(false)
  const [searchQ, setSearchQ] = useState('')
  const [roleFilter, setRoleFilter] = useState<RoleFilter>('all')
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')
  const [tierFilter, setTierFilter] = useState<TierFilter>('all')
  const [groupBy, setGroupBy] = useState<GroupBy>('role')
  const [pageView, setPageView] = useState<'list' | 'graph'>('list')

  useEffect(() => {
    if (!projectId) return
    charactersApi.list(projectId).then(res => {
      setCharacters(res.data)
      if (res.data.length > 0) setSelected(res.data[0])
    })
  }, [projectId, setCharacters])

  /** 写作复盘等路径 upsert 到 store 后，保持侧栏/详情与库内数据一致 */
  useEffect(() => {
    if (!selected?.id) return
    const fresh = characters.find(c => c.id === selected.id)
    if (fresh) setSelected(fresh)
  }, [characters, selected?.id])

  const filteredChars = useMemo(() => {
    const q = searchQ.trim().toLowerCase()
    return characters.filter(c => {
      if (q && !c.name.toLowerCase().includes(q) && !(c.faction ?? '').toLowerCase().includes(q)) return false
      if (roleFilter !== 'all' && c.role !== roleFilter) return false
      if (statusFilter !== 'all' && (c.current_status ?? 'alive') !== statusFilter) return false
      if (tierFilter !== 'all' && (c.character_tier ?? 'core') !== tierFilter) return false
      return true
    })
  }, [characters, searchQ, roleFilter, statusFilter, tierFilter])

  const groups = useMemo((): CharacterGroup[] => {
    if (groupBy === 'role') {
      const order: RoleFilter[] = ['protagonist', 'antagonist', 'supporting', 'neutral']
      return order
        .map(role => ({
          key: role,
          label: ROLE_META[role as keyof typeof ROLE_META]?.label ?? role,
          color: ROLE_META[role as keyof typeof ROLE_META]?.color ?? '',
          chars: filteredChars.filter(c => c.role === role),
        }))
        .filter(g => g.chars.length > 0)
    }
    const map = new Map<string, Character[]>()
    filteredChars.forEach(c => {
      const key = c.faction?.trim() || '无势力'
      if (!map.has(key)) map.set(key, [])
      map.get(key)!.push(c)
    })
    return Array.from(map.entries())
      .sort((a, b) => {
        if (a[0] === '无势力') return 1
        if (b[0] === '无势力') return -1
        return b[1].length - a[1].length
      })
      .map(([faction, chars]) => ({
        key: faction,
        label: faction,
        color: 'bg-blue-50 text-blue-700 border-blue-200',
        chars,
      }))
  }, [filteredChars, groupBy])

  const handleCreate = async () => {
    if (!projectId || creating) return
    setCreating(true)
    try {
      const res = await charactersApi.create(projectId, { name: '新人物', role: 'supporting' })
      upsertCharacter(res.data)
      setSelected(res.data)
    } catch {
      toast.error('创建失败')
    } finally {
      setCreating(false)
    }
  }

  const handleDelete = async (id: string) => {
    if (!projectId || !confirm('确认删除这个人物？')) return
    await charactersApi.delete(projectId, id)
    removeCharacter(id)
    const rest = characters.filter(c => c.id !== id)
    setSelected(rest.length > 0 ? rest[0] : null)
    toast.success('已删除')
  }

  const clearFilters = () => {
    setSearchQ('')
    setRoleFilter('all')
    setStatusFilter('all')
    setTierFilter('all')
  }

  const hasFilter = searchQ.trim() !== '' || roleFilter !== 'all' || statusFilter !== 'all' || tierFilter !== 'all'

  return {
    projectId,
    characters,
    selected,
    setSelected,
    filteredChars,
    groups,
    hasFilter,
    creating,
    searchQ,
    roleFilter,
    statusFilter,
    tierFilter,
    groupBy,
    pageView,
    setPageView,
    setSearchQ,
    setRoleFilter,
    setStatusFilter,
    setTierFilter,
    setGroupBy,
    handleCreate,
    handleDelete,
    clearFilters,
    upsertCharacter,
  }
}
