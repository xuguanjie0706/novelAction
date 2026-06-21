/**
 * 人物档案（右栏详情）—— 英雄区通栏 + 全部区块「铺平展开」于多列瀑布流（不再用标签隐藏）。
 * 宽屏铺 3 列、中屏 2 列、窄屏 1 列，尽量填满横向空间。关系网点击关联人物触发上层切换。
 */
import type { DabaiLabAsset, DabaiLabRelation } from '../../../../../types/dabaiLab'
import { SectionCard, type DabaiChar } from './charMeta'
import DossierHero from './DossierHero'
import { profileSections } from './DossierProfile'
import { recordSections } from './DossierRecords'

interface Props {
  character: DabaiChar
  characters: DabaiChar[]
  assets: DabaiLabAsset[]
  relation: DabaiLabRelation | null
  relations: DabaiLabRelation[]
  onSelect: (name: string) => void
  meta?: Record<string, unknown>
}

export default function CharacterDossier({ character, characters, assets, relation, relations, onSelect, meta }: Props) {
  const sections = [
    ...profileSections(character),
    ...recordSections({ character, characters, assets, relation, relations, onSelect, meta }),
  ]

  return (
    <div className="mx-auto max-w-6xl p-5 lg:p-6">
      <div className="rounded-xl border border-gray-100 bg-white p-5 shadow-sm">
        <DossierHero character={character} relation={relation} assetCount={assets.length} meta={meta} />
      </div>

      <div className="mt-4 gap-4 [column-fill:_balance] columns-1 md:columns-2 xl:columns-3">
        {sections.map(s => (
          <div key={s.key} className="mb-4 break-inside-avoid">
            <SectionCard title={s.title} icon={s.icon}>{s.body}</SectionCard>
          </div>
        ))}
      </div>
    </div>
  )
}
