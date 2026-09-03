export type RehearsalStatus = 'uploaded' | 'processing' | 'analyzed' | 'failed'

export interface Rehearsal {
  id: string
  user_id: string
  title: string
  audio_path: string
  status: RehearsalStatus
  error_message: string | null
  piece_title: string | null
  composer: string | null
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

export interface RubricCriterionFeedback {
  criterion: string
  observation: string
}

export interface RubricCaptionFeedback {
  caption: string
  assessed: RubricCriterionFeedback[]
  not_assessed: string[]
}

export interface RehearsalPlan {
  id: string
  rehearsal_id: string
  summary: string
  rubric_feedback: RubricCaptionFeedback[]
  drill_items: DrillItem[]
}
