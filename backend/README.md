# Rehearsal Coach — analysis service

Python/FastAPI service that turns an uploaded rehearsal recording into a
prioritized rehearsal plan:

1. Downloads the audio from Supabase Storage.
2. Converts it to mono WAV via FFmpeg.
3. Segments it into playing sections (splitting on stops/silence — see
   `app/audio_pipeline.py`), and computes per-segment tempo, tempo drift, and
   a rhythm-consistency score with Librosa beat tracking.
4. Sends that structured analysis to the Claude API, which generates a
   plain-language, prioritized, time-blocked rehearsal plan.
5. Writes the plan and drill items back to Supabase and marks the rehearsal
   `analyzed` (or `failed`, with `error_message` set, if anything goes wrong).

No pitch/intonation analysis — see the project README for why (out of MVP
scope; full-mix source separation isn't reliable enough yet).

## Running locally

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env  # fill in SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, ANTHROPIC_API_KEY

uvicorn app.main:app --reload --port 8000
```

Requires `ffmpeg` on `PATH` (`apt install ffmpeg` / `brew install ffmpeg`).

The frontend calls `POST /analyze/{rehearsal_id}` with the director's
Supabase access token (`Authorization: Bearer <token>`) after a successful
upload. The service verifies the token, confirms the rehearsal belongs to
that user, and processes it in the background — the endpoint returns `202`
immediately.

## Deploying

`Dockerfile` + `render.yaml` (at the repo root) are set up for
[Render](https://render.com): create a new Blueprint from this repo, and
Render will provision the service from `render.yaml`. Set the three secret
env vars (`SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `ANTHROPIC_API_KEY`)
in the Render dashboard — they're marked `sync: false` so they're not
committed. `SUPABASE_SERVICE_ROLE_KEY` is the **service role** key (Project
Settings → API in Supabase) — it bypasses row-level security, so treat it
like a root credential and never expose it to the frontend.

Once deployed, set `VITE_BACKEND_URL` (in the frontend's GitHub Actions
secrets, see `app/README.md`) to this service's URL, and add that same URL
to `ALLOWED_ORIGINS` if it differs from the defaults in `render.yaml`.

## Why a separate backend at all

The frontend is a static SPA on GitHub Pages talking to Supabase directly —
that works for auth, uploads, and reading results, but tempo/rhythm analysis
needs Librosa + FFmpeg (Python, not something a browser can run), and the
Claude API call needs a server-held API key. This service is that missing
piece.
