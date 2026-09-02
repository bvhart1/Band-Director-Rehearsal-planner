import { useEffect, useState } from 'react'
import { supabase } from '../lib/supabaseClient'
import { useAuth } from '../context/AuthContext'
import type { DrillItem, Rehearsal, RehearsalPlan } from '../lib/types'

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

  useEffect(() => {
    if (!user) return
    let cancelled = false

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
    }

    loadRehearsals()
    return () => {
      cancelled = true
    }
  }, [user])

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
        drill_items: (drillRows as DrillItem[]) ?? [],
      })
    }

    loadPlan()
    return () => {
      cancelled = true
    }
  }, [selectedId])

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
            <p className="page-subtitle">
              {new Date(selected.recorded_at).toLocaleString()} ·{' '}
              <span className={`status-badge status-${selected.status}`}>
                {STATUS_LABEL[selected.status]}
              </span>
            </p>

            {!plan && selected.status !== 'analyzed' && (
              <p className="empty-plan">
                This recording hasn't been analyzed yet. Once the audio pipeline finishes,
                your prioritized rehearsal plan will show up here.
              </p>
            )}

            {plan && (
              <div className="plan">
                <p className="plan-summary">{plan.summary}</p>
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
                        {item.measures && <span>Measures {item.measures}</span>}
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
