import { useEffect, useState, type ChangeEvent, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { supabase, AUDIO_BUCKET } from '../lib/supabaseClient'
import { triggerAnalysis } from '../lib/analysis'
import { useAuth } from '../context/AuthContext'
import { isRecordingSupported, useAudioRecorder } from '../hooks/useAudioRecorder'

function formatElapsed(totalSeconds: number): string {
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return `${minutes}:${seconds.toString().padStart(2, '0')}`
}

export function Upload() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const [source, setSource] = useState<'file' | 'record'>('file')
  const [file, setFile] = useState<File | null>(null)
  const [title, setTitle] = useState('')
  const [recordedAt, setRecordedAt] = useState(() => new Date().toISOString().slice(0, 16))
  const [status, setStatus] = useState<'idle' | 'uploading' | 'error'>('idle')
  const [error, setError] = useState<string | null>(null)
  const recorder = useAudioRecorder()
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)

  useEffect(() => {
    if (recorder.status !== 'stopped' || !recorder.file) {
      setPreviewUrl(null)
      return
    }
    const url = URL.createObjectURL(recorder.file)
    setPreviewUrl(url)
    return () => URL.revokeObjectURL(url)
  }, [recorder.status, recorder.file])

  function handleFileChange(e: ChangeEvent<HTMLInputElement>) {
    const selected = e.target.files?.[0] ?? null
    setFile(selected)
    if (selected && !title) {
      setTitle(selected.name.replace(/\.[^/.]+$/, ''))
    }
  }

  function selectSource(next: 'file' | 'record') {
    setSource(next)
    setFile(null)
    recorder.reset()
  }

  function acceptRecording() {
    if (!recorder.file) return
    setFile(recorder.file)
    if (!title) {
      setTitle(`Rehearsal recording ${new Date().toLocaleDateString()}`)
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

    const { data: inserted, error: insertError } = await supabase
      .from('rehearsals')
      .insert({
        user_id: user.id,
        title: title || file.name,
        audio_path: path,
        status: 'uploaded',
        recorded_at: new Date(recordedAt).toISOString(),
      })
      .select()
      .single()

    if (insertError || !inserted) {
      setStatus('error')
      setError(insertError?.message ?? 'Could not save the rehearsal record.')
      return
    }

    await triggerAnalysis(inserted.id)
    navigate('/dashboard')
  }

  const recordingAccepted = source === 'record' && !!file

  return (
    <div className="page">
      <h1>Upload a rehearsal recording</h1>
      <p className="page-subtitle">
        Record straight from your phone's browser during rehearsal, or upload an existing
        recording from your device.
      </p>

      {isRecordingSupported && (
        <div className="source-toggle">
          <button
            type="button"
            className={source === 'file' ? 'source-tab active' : 'source-tab'}
            onClick={() => selectSource('file')}
          >
            Upload a file
          </button>
          <button
            type="button"
            className={source === 'record' ? 'source-tab active' : 'source-tab'}
            onClick={() => selectSource('record')}
          >
            Record now
          </button>
        </div>
      )}

      <form className="upload-form" onSubmit={handleSubmit}>
        {source === 'file' && (
          <label>
            Recording
            <input
              type="file"
              accept="audio/*,.m4a,.caf,.mp3,.wav,.aac,.ogg,.webm"
              required
              onChange={handleFileChange}
            />
            <span className="field-hint">
              On iPhone: tap <strong>Browse</strong> in the picker, not Photos — Voice Memos only
              show up there if they're synced to iCloud Drive, or saved to Files from the Voice
              Memos app (open the recording → Share → Save to Files).
            </span>
          </label>
        )}

        {source === 'record' && !recordingAccepted && (
          <div className="recorder">
            {recorder.status === 'idle' && (
              <button type="button" onClick={recorder.start}>
                Start recording
              </button>
            )}

            {recorder.status === 'requesting' && <p>Requesting microphone access…</p>}

            {recorder.status === 'recording' && (
              <>
                <p className="recorder-timer">
                  <span className="recorder-dot" /> Recording — {formatElapsed(recorder.seconds)}
                </p>
                <button type="button" onClick={recorder.stop}>
                  Stop recording
                </button>
              </>
            )}

            {recorder.status === 'stopped' && recorder.file && previewUrl && (
              <>
                <audio controls src={previewUrl} />
                <div className="recorder-actions">
                  <button type="button" onClick={acceptRecording}>
                    Use this recording
                  </button>
                  <button type="button" className="link-button" onClick={recorder.reset}>
                    Re-record
                  </button>
                </div>
              </>
            )}

            {recorder.status === 'error' && (
              <>
                <p className="form-error">{recorder.error}</p>
                <button type="button" onClick={recorder.start}>
                  Try again
                </button>
              </>
            )}
          </div>
        )}

        {recordingAccepted && (
          <div className="recorder recorder-accepted">
            <p>Recording ready ({formatElapsed(recorder.seconds)}).</p>
            <button
              type="button"
              className="link-button"
              onClick={() => {
                setFile(null)
                recorder.reset()
              }}
            >
              Record a different take
            </button>
          </div>
        )}

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
