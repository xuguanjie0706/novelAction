export type WorkspaceTab =
  | 'write' | 'volumes' | 'characters' | 'world' | 'quality' | 'memory' | 'clues' | 'ledger'

export const WORKSPACE_TABS: WorkspaceTab[] = [
  'write', 'volumes', 'characters', 'world', 'quality', 'memory', 'clues', 'ledger',
]

export function parseWorkspaceTab(raw: string | null): WorkspaceTab {
  return WORKSPACE_TABS.includes(raw as WorkspaceTab) ? (raw as WorkspaceTab) : 'write'
}
