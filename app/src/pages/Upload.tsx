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

type Source = 'file' | 'record' | 'link'

export function Upload() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const [source, setSource] = useState<Source>('file')
  const [file, setFile] = useState<File | null>(null)
  const [linkUrl, setLinkUrl] = useState('')
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

  function selectSource(next: Source) {
    setSource(next)
    setFile(null)
    setLinkUrl('')
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
    if (!user) return
    if (source === 'link') {
      if (!linkUrl.trim()) return
    } else if (!file) {
      return
    }

    setStatus('uploading')
    setError(null)

    let audioPath: string
    let insertTitle: string

    if (source === 'link') {
      audioPath = 'pending'
      insertTitle = title || 'Rehearsal recording'
    } else {
      const ext = file!.name.split('.').pop() ?? 'audio'
      audioPath = `${user.id}/${Date.now()}.${ext}`
      insertTitle = title || file!.name

      const { error: uploadError } = await supabase.storage.from(AUDIO_BUCKET).upload(audioPath, file!)
      if (uploadError) {
        setStatus('error')
        setError(uploadError.message)
        return
      }
    }

    const { data: inserted, error: insertError } = await supabase
      .from('rehearsals')
      .insert({
        user_id: user.id,
        title: insertTitle,
        audio_path: audioPath,
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

    await triggerAnalysis(inserted.id, source === 'link' ? { sourceUrl: linkUrl.trim() } : undefined)
    navigate('/dashboard')
  }

  const recordingAccepted = source === 'record' && !!file
  const canSubmit = source === 'link' ? linkUrl.trim().length > 0 : !!file

  return (
    <div className="page">
      <h1>Upload a rehearsal recording</h1>
      <p className="page-subtitle">
        Record straight from your phone's browser during rehearsal, or upload an existing
        recording from your device.
      </p>

      <div className="source-toggle">
        <button
          type="button"
          className={source === 'file' ? 'source-tab active' : 'source-tab'}
          onClick={() => selectSource('file')}
        >
          Upload a file
        </button>
        {isRecordingSupported && (
          <button
            type="button"
            className={source === 'record' ? 'source-tab active' : 'source-tab'}
            onClick={() => selectSource('record')}
          >
            Record now
          </button>
        )}
        <button
          type="button"
          className={source === 'link' ? 'source-tab active' : 'source-tab'}
          onClick={() => selectSource('link')}
        >
          Link to a file
        </button>
      </div>

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

        {source === 'link' && (
          <label>
            Link to the recording
            <input
              type="url"
              inputMode="url"
              placeholder="https://... or a Google Drive share link"
              required
              value={linkUrl}
              onChange={(e) => setLinkUrl(e.target.value)}
            />
            <span className="field-hint">
              Works with direct file links and Google Drive share links (the file needs to be
              shared as "Anyone with the link"). YouTube links aren't supported.
            </span>
          </label>
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
        <button type="submit" disabled={!canSubmit || status === 'uploading'}>
          {status === 'uploading' ? 'Saving…' : 'Upload recording'}
        </button>
      </form>
    </div>
  )
}
