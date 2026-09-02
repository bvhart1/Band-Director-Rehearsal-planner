import { useState, type ChangeEvent, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { supabase, AUDIO_BUCKET } from '../lib/supabaseClient'
import { useAuth } from '../context/AuthContext'

export function Upload() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const [file, setFile] = useState<File | null>(null)
  const [title, setTitle] = useState('')
  const [recordedAt, setRecordedAt] = useState(() => new Date().toISOString().slice(0, 16))
  const [status, setStatus] = useState<'idle' | 'uploading' | 'error'>('idle')
  const [error, setError] = useState<string | null>(null)

  function handleFileChange(e: ChangeEvent<HTMLInputElement>) {
    const selected = e.target.files?.[0] ?? null
    setFile(selected)
    if (selected && !title) {
      setTitle(selected.name.replace(/\.[^/.]+$/, ''))
    }
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (!file || !user) return

    setStatus('uploading')
    setError(null)

    const ext = file.name.split('.').pop() ?? 'audio'
    const path = `${user.id}/${Date.now()}.${ext}`

    const { error: uploadError } = await supabase.storage.from(AUDIO_BUCKET).upload(path, file)
    if (uploadError) {
      setStatus('error')
      setError(uploadError.message)
      return
    }

    const { error: insertError } = await supabase.from('rehearsals').insert({
      user_id: user.id,
      title: title || file.name,
      audio_path: path,
      status: 'uploaded',
      recorded_at: new Date(recordedAt).toISOString(),
    })

    if (insertError) {
      setStatus('error')
      setError(insertError.message)
      return
    }

    navigate('/dashboard')
  }

  return (
    <div className="page">
      <h1>Upload a rehearsal recording</h1>
      <p className="page-subtitle">
        Record on your phone during rehearsal, then upload the file here — or choose an
        existing recording from your device.
      </p>
      <form className="upload-form" onSubmit={handleSubmit}>
        <label>
          Recording
          <input type="file" accept="audio/*" required onChange={handleFileChange} />
        </label>
        <label>
          Title
          <input
            type="text"
            placeholder="e.g. Tuesday full ensemble rehearsal"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
        </label>
        <label>
          Rehearsal date &amp; time
          <input
            type="datetime-local"
            value={recordedAt}
            onChange={(e) => setRecordedAt(e.target.value)}
          />
        </label>
        {error && <p className="form-error">{error}</p>}
        <button type="submit" disabled={!file || status === 'uploading'}>
          {status === 'uploading' ? 'Uploading…' : 'Upload recording'}
        </button>
      </form>
    </div>
  )
}
