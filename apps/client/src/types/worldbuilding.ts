// ── World Setting ─────────────────────────────────────
export interface WorldSetting {
  id: string
  project_id: string
  category_id?: string
  title: string
  content?: string
  tags: string[]
  extra: Record<string, any>
  created_at: string
  updated_at?: string
}

// ── Character ─────────────────────────────────────────
export interface Character {
  id: string
  project_id: string
  name: string
  alias: string[]
  role: 'protagonist' | 'supporting' | 'antagonist' | 'neutral'
  /** 叙事层级：core=核心长线 / arc=弧线支柱 / plot=剧情推手 / background=背景填充 */
  character_tier: 'core' | 'arc' | 'plot' | 'background'
  gender?: string
  age?: string
  avatar_url?: string
  // 归属
  faction?: string
  faction_id?: string
  faction_rank?: string
  birthplace?: string
  // 外貌
  appearance?: string
  clothing_style?: string
  // 能力
  current_realm?: string
  power_system_id?: string
  realm_rank?: number
  // 性格
  personality?: string
  speech_style?: string
  /** 结构化语风指纹（P2 新增） */
  speech_kit?: {
    signature_words?: string[]
    sentence_length_pref?: string
    taboo_words?: string[]
    sample_dialogues?: string[]
    inner_monologue_style?: string
    recent_evolution_notes?: Array<{ chapter_id: string; chapter_title: string; note: string }>
  }
  values?: string
  // 背景
  background?: string
  secrets?: string
  trauma?: string
  // 动机成长
  motivation?: string
  fear?: string
  arc?: string
  arc_stages: any[]
  // 能力标签
  strengths: string[]
  weaknesses: string[]
  special_traits: string[]
  // 技能道具
  known_skills: any[]
  owned_items: any[]
  // 状态
  current_status: 'alive' | 'dead' | 'missing' | 'sealed' | 'transformed'
  current_location?: string
  author_notes?: string
  extra: Record<string, any>
  created_at: string
  updated_at?: string
}

export interface CharacterRelationship {
  id: string
  project_id: string
  from_character_id: string
  to_character_id: string
  relation_type: string
  description?: string
  intensity: number
  is_dynamic: string
  evolution_note?: string
}

// ── StoryLine ─────────────────────────────────────────
export interface StoryLine {
  id: string
  project_id: string
  name: string
  line_type: 'main' | 'sub' | 'romance' | 'growth' | 'mystery' | 'faction' | 'antagonist'
  description?: string
  status: 'planned' | 'active' | 'climax' | 'resolved' | 'dropped'
  start_chapter?: number
  end_chapter?: number
  related_character_ids: string[]
  key_beats: any[]
  core_conflict?: string
  resolution_direction?: string
  sort_order: number
  extra: Record<string, any>
  created_at: string
  updated_at?: string
}

// ── PowerSystem ───────────────────────────────────────
export interface PowerLevel {
  rank: number
  name: string
  description?: string
  requirements?: string
  abilities?: string[]
  approximate_chapter?: string
  sub_level_count?: number
}

export interface PowerSystem {
  id: string
  project_id: string
  name: string
  system_type: 'cultivation' | 'magic' | 'ability' | 'tech' | 'hybrid'
  description?: string
  levels: PowerLevel[]
  cultivation_method?: string
  breakthrough_condition?: string
  special_rules?: string
  protagonist_current_rank?: number
  protagonist_end_rank?: number
  sort_order: number
  extra: Record<string, any>
  created_at: string
  updated_at?: string
}

// ── Skill ─────────────────────────────────────────────
export interface Skill {
  id: string
  project_id: string
  power_system_id?: string
  name: string
  skill_type: 'combat' | 'defense' | 'movement' | 'support' | 'bloodline' | 'special'
  grade: 'mortal' | 'earth' | 'sky' | 'profound' | 'saint' | 'divine' | 'supreme'
  source?: string
  level_required?: string
  prerequisites?: string
  description?: string
  effects?: string
  limitations?: string
  mastery_stages: any[]
  mastered_by_character_ids: string[]
  first_appearance_chapter?: number
  sort_order: number
  extra: Record<string, any>
  created_at: string
  updated_at?: string
}

// ── Item ──────────────────────────────────────────────
export interface Item {
  id: string
  project_id: string
  name: string
  item_type: 'weapon' | 'armor' | 'pill' | 'artifact' | 'material' | 'scroll' | 'beast' | 'other'
  rarity: 'common' | 'uncommon' | 'rare' | 'epic' | 'legendary' | 'mythic' | 'unique'
  description?: string
  origin?: string
  effects?: string
  limitations?: string
  current_owner_id?: string
  ownership_history: any[]
  story_significance?: string
  first_appearance_chapter?: number
  status: 'intact' | 'damaged' | 'destroyed' | 'lost' | 'unknown'
  sort_order: number
  extra: Record<string, any>
  created_at: string
  updated_at?: string
}

// ── Faction ───────────────────────────────────────────
export interface Faction {
  id: string
  project_id: string
  parent_faction_id?: string
  name: string
  faction_type: 'sect' | 'kingdom' | 'family' | 'guild' | 'evil' | 'race' | 'other'
  alignment: 'protagonist' | 'neutral' | 'antagonist' | 'unknown'
  description?: string
  territory?: string
  strength_level?: string
  member_count?: string
  top_power?: string
  leader_character_id?: string
  key_members: any[]
  goals?: string
  resources?: string
  rivals: string[]
  allies: string[]
  attitude_to_protagonist: string
  history?: string
  secrets?: string
  sort_order: number
  extra: Record<string, any>
  created_at: string
  updated_at?: string
}
