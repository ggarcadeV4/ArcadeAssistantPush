export type AIAction =
  | 'edit_config'
  | 'generate_led_pattern'
  | 'launch_game'
  | 'create_playlist'
  | 'create_tournament'

export type DiffOp =
  | { op: 'replace'; match: string; value: string }
  | { op: 'insert'; match: string; value: string; before?: boolean }
  | { op: 'remove'; match: string }

export interface ActionEnvelope {
  action: AIAction
  target?: { path?: string; gameId?: string }
  intent?: string
  constraints?: { max_edits?: number; json_only?: boolean }
  diff?: DiffOp[]
  notes?: string
  metadata?: Record<string, any>
}

