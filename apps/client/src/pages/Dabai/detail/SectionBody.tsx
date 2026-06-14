/**
 * @file pages/Dabai/detail/SectionBody.tsx
 * 按 sectionId 分发到对应分区渲染组件的薄壳。
 */
import type { DabaiProjectDetail } from '../../../types/dabai'
import {
  OverviewSection, BenchmarkSection, GoldenSection, PowerSection,
  AntagonistSection, FactionsSection, CharactersSection,
  StorylinesSection, MysterySection,
} from './RenderPlanning'
import { VolumesSection, BeatsSection, QualitySection } from './RenderBeats'
import LedgerSection from './RenderLedger'

interface Props {
  sectionId: string
  projectId: string
  d: DabaiProjectDetail
  onRelint: () => void
  relinting: boolean
}

export default function SectionBody({ sectionId, projectId, d, onRelint, relinting }: Props) {
  switch (sectionId) {
    case 'overview': return <OverviewSection d={d} projectId={projectId} />
    case 'benchmark': return <BenchmarkSection d={d} />
    case 'golden': return <GoldenSection d={d} />
    case 'power': return <PowerSection d={d} />
    case 'antagonist': return <AntagonistSection d={d} />
    case 'factions': return <FactionsSection d={d} />
    case 'characters': return <CharactersSection d={d} />
    case 'storylines': return <StorylinesSection d={d} />
    case 'mystery': return <MysterySection d={d} />
    case 'volumes': return <VolumesSection d={d} />
    case 'beats': return <BeatsSection d={d} />
    case 'ledger': return <LedgerSection projectId={projectId} d={d} />
    case 'quality': return <QualitySection d={d} onRelint={onRelint} relinting={relinting} />
    default: return <OverviewSection d={d} projectId={projectId} />
  }
}
