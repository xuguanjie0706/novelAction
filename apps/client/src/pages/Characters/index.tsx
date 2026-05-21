/**
 * @file 人物库页面
 */
import { Suspense, lazy } from 'react'
import { Sparkles, Users } from 'lucide-react'
import PageSpinner from '../../components/common/PageSpinner'
import { CharacterList } from './CharacterList'
import { CharacterEditor } from './CharacterEditor'
import { useCharactersPage } from './useCharactersPage'

const RelationshipGraph = lazy(() => import('../../components/Characters/RelationshipGraph'))

export default function CharactersPage() {
  const {
    projectId,
    characters,
    selected,
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
    setSelected,
  } = useCharactersPage()

  if (!projectId) return <PageSpinner />

  if (pageView === 'graph') {
    return (
      <div className="flex flex-col h-full">
        <div className="flex items-center justify-between px-4 py-2.5 border-b border-gray-100 bg-white shrink-0">
          <div className="flex items-center gap-2">
            <Sparkles size={14} className="text-indigo-500" />
            <span className="text-sm font-semibold text-gray-700">人物关系图</span>
            <span className="text-xs text-gray-400">{characters.length} 人 · 星座星图 / 阵营分层</span>
          </div>
          <button
            type="button"
            onClick={() => setPageView('list')}
            className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border border-gray-200 text-gray-500 hover:bg-gray-50 transition-colors"
          >
            <Users size={12} />
            返回人物列表
          </button>
        </div>
        <div className="flex-1 relative overflow-hidden">
          <Suspense fallback={<PageSpinner label="关系图加载中…" />}>
            <RelationshipGraph projectId={projectId} />
          </Suspense>
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-full">
      <CharacterList
        projectId={projectId}
        characters={characters}
        filteredChars={filteredChars}
        groups={groups}
        selected={selected}
        hasFilter={hasFilter}
        creating={creating}
        searchQ={searchQ}
        roleFilter={roleFilter}
        statusFilter={statusFilter}
        tierFilter={tierFilter}
        groupBy={groupBy}
        onSearchChange={setSearchQ}
        onRoleFilter={setRoleFilter}
        onStatusFilter={setStatusFilter}
        onTierFilter={setTierFilter}
        onGroupBy={setGroupBy}
        onSelect={setSelected}
        onCreate={handleCreate}
        onOpenGraph={() => setPageView('graph')}
        onClearFilters={clearFilters}
      />
      <div className="flex-1 overflow-hidden bg-[#FAF8F4]">
        {selected ? (
          <CharacterEditor
            char={selected}
            projectId={projectId}
            onUpdate={upsertCharacter}
            onDelete={handleDelete}
            batchTargets={filteredChars}
          />
        ) : (
          <div className="flex items-center justify-center h-full text-gray-400 text-sm">选择左侧人物查看详情</div>
        )}
      </div>
    </div>
  )
}
