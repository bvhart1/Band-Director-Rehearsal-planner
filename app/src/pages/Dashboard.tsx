import { useEffect, useState } from 'react'
import { supabase } from '../lib/supabaseClient'
import { triggerAnalysis } from '../lib/analysis'
import { useAuth } from '../context/AuthContext'
import type { DrillItem, Rehearsal, RehearsalPlan, RubricCaptionFeedback } from '../lib/types'

const POLL_INTERVAL_MS = 5000

const STATUS_LABEL: Record<Rehearsal['status'], string> = {
  uploaded: 'Waiting to be analyzed',
  processing: 'Analyzing…',
  analyzed: 'Plan ready',
  failed: 'Analysis failed',
}

export function Dashboard() {
  const { user } = useAuth()
  const [rehearsals, setRehearsals] = useState<Rehearsal[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [plan, setPlan] = useState<RehearsalPlan | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshNonce, setRefreshNonce] = useState(0)

  useEffect(() => {
    if (!user) return
    let cancelled = false
    let timer: ReturnType<typeof setTimeout>

    async function loadRehearsals() {
      const { data } = await supabase
        .from('rehearsals')
        .select('*')
        .eq('user_id', user!.id)
        .order('recorded_at', { ascending: false })

      if (cancelled) return
      const list = (data as Rehearsal[]) ?? []
      setRehearsals(list)
      setSelectedId((current) => current ?? list[0]?.id ?? null)
      setLoading(false)

      const stillWorking = list.some((r) => r.status === 'uploaded' || r.status === 'processing')
      if (stillWorking) {
        timer = setTimeout(loadRehearsals, POLL_INTERVAL_MS)
      }
    }

    loadRehearsals()
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [user, refreshNonce])

  const selectedStatus = rehearsals.find((r) => r.id === selectedId)?.status ?? null

  useEffect(() => {
    if (!selectedId) {
      setPlan(null)
      return
    }
    let cancelled = false

    async function loadPlan() {
      const { data: planRow } = await supabase
        .from('rehearsal_plans')
        .select('*')
        .eq('rehearsal_id', selectedId)
        .maybeSingle()

      if (!planRow) {
        if (!cancelled) setPlan(null)
        return
      }

      const { data: drillRows } = await supabase
        .from('drill_items')
        .select('*')
        .eq('rehearsal_id', selectedId)
        .order('priority', { ascending: true })

      if (cancelled) return
      setPlan({
        id: planRow.id,
        rehearsal_id: planRow.rehearsal_id,
        summary: planRow.summary,
        rubric_feedback: (planRow.rubric_feedback as RubricCaptionFeedback[]) ?? [],
        drill_items: (drillRows as DrillItem[]) ?? [],
      })
    }

    loadPlan()
    return () => {
      cancelled = true
    }
  }, [selectedId, selectedStatus])

  async function retryAnalysis(rehearsalId: string) {
    await triggerAnalysis(rehearsalId)
    setRefreshNonce((n) => n + 1)
  }

  async function toggleDrillDone(item: DrillItem) {
    if (!plan) return
    const nextDone = !item.done
    setPlan({
      ...plan,
      drill_items: plan.drill_items.map((d) => (d.id === item.id ? { ...d, done: nextDone } : d)),
    })
    await supabase.from('drill_items').update({ done: nextDone }).eq('id', item.id)
  }

  const selected = rehearsals.find((r) => r.id === selectedId) ?? null

  if (loading) return <div className="page-loading">Loading rehearsals…</div>

  if (rehearsals.length === 0) {
    return (
      <div className="page">
        <h1>Dashboard</h1>
        <p className="page-subtitle">No rehearsals yet. Upload a recording to get your first plan.</p>
      </div>
    )
  }

  return (
    <div className="page dashboard">
      <aside className="rehearsal-list">
        <h2>Rehearsals</h2>
        <ul>
          {rehearsals.map((r) => (
            <li key={r.id}>
              <button
                className={r.id === selectedId ? 'rehearsal-item active' : 'rehearsal-item'}
                onClick={() => setSelectedId(r.id)}
              >
                <span className="rehearsal-title">{r.title}</span>
                <span className={`status-badge status-${r.status}`}>{STATUS_LABEL[r.status]}</span>
              </button>
            </li>
          ))}
        </ul>
      </aside>

      <section className="rehearsal-detail">
        {selected && (
          <>
            <h1>{selected.title}</h1>
            {selected.piece_title && (
              <p className="piece-byline">
                {selected.piece_title}
                {selected.composer && <> — {selected.composer}</>}
              </p>
            )}
            <p className="page-subtitle">
              {new Date(selected.recorded_at).toLocaleString()} ·{' '}
              <span className={`status-badge status-${selected.status}`}>
                {STATUS_LABEL[selected.status]}
              </span>
            </p>

            {selected.status === 'failed' && (
              <div className="empty-plan">
                <p>
                  {selected.error_message ??
                    'Something went wrong analyzing this recording.'}
                </p>
                <button type="button" onClick={() => retryAnalysis(selected.id)}>
                  Retry analysis
                </button>
              </div>
            )}

            {(selected.status === 'uploaded' || selected.status === 'processing') && !plan && (
              <p className="empty-plan">
                {selected.status === 'processing'
                  ? 'Analyzing tempo and rhythm now — this can take a minute or two.'
                  : "Waiting to start analysis. If this doesn't move to \"Analyzing…\" shortly,"}
                {selected.status === 'uploaded' && (
                  <>
                    {' '}
                    <button type="button" onClick={() => retryAnalysis(selected.id)}>
                      try again
                    </button>
                    .
                  </>
                )}
              </p>
            )}

            {plan && (
              <div className="plan">
                <p className="plan-summary">{plan.summary}</p>

                {plan.rubric_feedback.length > 0 && (
                  <div className="rubric">
                    <h2>FBA Rubric Feedback</h2>
                    <p className="rubric-caveat">
                      This tool only measures tempo and rhythm timing, so it can only speak to a
                      handful of the rubric's 24 criteria. Everything else is explicitly marked as
                      not assessed rather than guessed at.
                    </p>
                    <div className="rubric-columns">
                      {plan.rubric_feedback.map((caption) => (
                        <div key={caption.caption} className="rubric-caption">
                          <h3>{caption.caption}</h3>
                          {caption.assessed.map((item) => (
                            <div key={item.criterion} className="rubric-criterion">
                              <span className="rubric-criterion-name">{item.criterion}</span>
                              <p>{item.observation}</p>
                            </div>
                          ))}
                          {caption.not_assessed.length > 0 && (
                            <p className="rubric-not-assessed">
                              Not assessed by this tool: {caption.not_assessed.join(', ')}
                            </p>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                <div className="drill-list">
                  {plan.drill_items.map((item) => (
                    <div key={item.id} className={`drill-item priority-${item.priority}`}>
                      <label className="drill-checkbox">
                        <input
                          type="checkbox"
                          checked={item.done}
                          onChange={() => toggleDrillDone(item)}
                        />
                        <span className={item.done ? 'drill-title done' : 'drill-title'}>
                          {item.title}
                        </span>
                      </label>
                      <div className="drill-meta">
                        <span className={`priority-badge priority-${item.priority}`}>
                          {item.priority}
                        </span>
                        <span>{item.suggested_minutes} min</span>
                        {item.measures && <span>{item.measures}</span>}
                      </div>
                      <p className="drill-description">{item.description}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </section>
    </div>
  )
}
