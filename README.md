# Band Director Rehearsal Planner

A web app for school band directors: record or upload rehearsal audio, get
tempo/rhythm analysis, and receive a plain-language, prioritized plan for the
next rehearsal.

## MVP scope

- Single phone/microphone recording (multi-mic "pro tier" is a planned
  future feature)
- Tempo and rhythm analysis only (no pitch/intonation in v1)
- Output: a structured next-rehearsal plan with prioritized drill sections
  and suggested time blocks

## Stack

- **Frontend:** React + TypeScript + Vite, mobile-friendly web app
- **Auth/DB:** Supabase (Postgres)
- **File storage:** Supabase Storage (audio uploads)
- **Audio processing (planned):** Python, Librosa/Essentia for tempo & beat
  tracking, FFmpeg for format conversion
- **AI layer (planned):** Anthropic Claude API — turns structured tempo/
  rhythm analysis into a plain-language rehearsal plan

## Layout

- `app/` — the React frontend (auth, upload, dashboard). See `app/README.md`
  for setup instructions.
- `supabase/schema.sql` — the database schema (rehearsals, rehearsal_plans,
  drill_items) with row-level security and storage bucket policies.

## Status

Scaffolded: auth, audio upload, and a dashboard shell that renders a
prioritized plan once one exists. Not yet built: the audio analysis
pipeline and the Claude API integration that generates the plan.
