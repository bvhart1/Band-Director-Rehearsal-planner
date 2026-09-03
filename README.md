# Band Director Rehearsal Planner

A web app for school band directors: record or upload rehearsal audio, get
tempo/rhythm analysis, and receive a plain-language, prioritized plan for the
next rehearsal.

## MVP scope

- Single phone/microphone recording (multi-mic "pro tier" is a planned
  future feature)
- Tempo and rhythm analysis only (no pitch/intonation in v1 — full-ensemble
  mixes can't be reliably split into instrument stems without source
  separation, which isn't robust enough yet)
- Output: a structured next-rehearsal plan with prioritized drill sections
  and suggested time blocks

## Stack

- **Frontend:** React + TypeScript + Vite, mobile-friendly SPA, deployed to
  GitHub Pages
- **Backend:** Python + FastAPI, deployed as a Docker service (Render)
- **Auth/DB:** Supabase (Postgres, row-level security)
- **File storage:** Supabase Storage (audio uploads)
- **Audio processing:** FFmpeg (format conversion) + Librosa (beat tracking,
  tempo drift, rhythm-consistency scoring)
- **AI layer:** Anthropic Claude API — turns the structured tempo/rhythm
  analysis into a plain-language, prioritized rehearsal plan

## How it works

1. Director signs in, uploads (or records) a rehearsal file.
2. The frontend uploads the audio to Supabase Storage, creates a
   `rehearsals` row, and calls the backend's `/analyze/{id}` endpoint.
3. The backend downloads the audio, converts it with FFmpeg, splits it into
   playing segments (using stops as natural breakpoints), and runs Librosa
   beat tracking per segment to get tempo, tempo drift, and a
   rhythm-consistency score.
4. That structured analysis goes to Claude, which writes a prioritized,
   time-blocked rehearsal plan.
5. The plan and drill items are written back to Supabase; the dashboard
   polls until they're ready, then shows them with per-item done/skip
   checkboxes.

## Layout

- `app/` — the React frontend. See `app/README.md` for setup.
- `backend/` — the FastAPI analysis service. See `backend/README.md` for
  setup and deployment.
- `supabase/schema.sql` — the database schema (rehearsals, rehearsal_plans,
  drill_items) with row-level security and storage bucket policies.
- `render.yaml` — Render Blueprint for deploying `backend/`.
- `.github/workflows/deploy.yml` — builds and deploys `app/` to GitHub Pages
  on every push to `main`.

## Status

End-to-end MVP is built: auth, upload, the analysis pipeline, Claude plan
generation, and the dashboard are all wired together. What's left before
this is genuinely usable by directors:

- Deploy the backend (Render Blueprint is ready; needs Supabase + Anthropic
  credentials set as secrets) and point `VITE_BACKEND_URL` at it.
- Test against real rehearsal recordings — the segmentation/tempo thresholds
  in `backend/app/audio_pipeline.py` were tuned against a synthetic test
  file, not a real ensemble recording, and will likely need adjustment.
- Payments (Stripe) and the multi-mic "pro tier" — intentionally out of MVP
  scope.
