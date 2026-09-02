export type RehearsalStatus = 'uploaded' | 'processing' | 'analyzed' | 'failed'

export interface Rehearsal {
  id: string
  user_id: string
  title: string
  audio_path: string
  status: RehearsalStatus
  recorded_at: string
  created_at: string
}

export type DrillPriority = 'high' | 'medium' | 'low'

export interface DrillItem {
  id: string
  rehearsal_id: string
  title: string
  description: string
  priority: DrillPriority
  suggested_minutes: number
  measures: string | null
  done: boolean
}

export interface RehearsalPlan {
  id: string
  rehearsal_id: string
  summary: string
  drill_items: DrillItem[]
}
