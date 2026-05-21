import React from 'react'
import type { StepKey } from './hooks/useBootstrapStream'

const SPRITE_URL = '/assets/bootstrap-step-icons.svg'
const ICON_SIZE = 24
const COLS = 5
const ROWS = 5

const ICON_COORDS: Record<StepKey, { col: number; row: number }> = {
  positioning: { col: 0, row: 0 },
  project: { col: 1, row: 0 },
  power_systems: { col: 2, row: 0 },
  factions: { col: 3, row: 0 },
  storylines: { col: 4, row: 0 },
  characters: { col: 0, row: 1 },
  skills: { col: 1, row: 1 },
  items: { col: 2, row: 1 },
  settings: { col: 3, row: 1 },
  volumes: { col: 4, row: 1 },
  memory: { col: 0, row: 2 },
  relations: { col: 1, row: 2 },
  opening_contract: { col: 2, row: 2 },
  consistency: { col: 3, row: 2 },
  all: { col: 1, row: 3 },
  saving: { col: 2, row: 3 },
  contrast_design: { col: 3, row: 3 },
  golden_finger: { col: 4, row: 3 },
  face_slap_map: { col: 0, row: 4 },
  power_ladder: { col: 1, row: 4 },
  opening_5chapters: { col: 2, row: 4 },
  rhythm_map: { col: 3, row: 4 },
  signal_audit: { col: 4, row: 4 },
}

interface Props {
  iconKey: StepKey
  size?: number
  className?: string
  title?: string
}

export default function BootstrapStepIcon({ iconKey, size = 16, className, title }: Props) {
  const coord = ICON_COORDS[iconKey] ?? ICON_COORDS.all
  const scale = size / ICON_SIZE

  return (
    <span
      className={className}
      role={title ? 'img' : undefined}
      aria-hidden={title ? undefined : true}
      aria-label={title}
      style={{
        display: 'inline-block',
        width: size,
        height: size,
        flexShrink: 0,
        backgroundImage: `url("${SPRITE_URL}")`,
        backgroundRepeat: 'no-repeat',
        backgroundSize: `${COLS * ICON_SIZE * scale}px ${ROWS * ICON_SIZE * scale}px`,
        backgroundPosition: `${-coord.col * size}px ${-coord.row * size}px`,
      }}
    />
  )
}
