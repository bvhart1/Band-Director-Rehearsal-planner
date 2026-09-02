# Rehearsal Coach (web app)

Mobile-friendly web app for band directors: record or upload rehearsal audio,
and get a prioritized, plain-language plan for the next rehearsal.

This is the MVP scaffold — auth, upload, and a dashboard shell. The audio
analysis pipeline (Librosa/Essentia tempo & rhythm scoring) and the Claude API
integration that turns that analysis into a rehearsal plan are not built yet;
they populate `rehearsal_plans` / `drill_items` once running.

## Stack

- React + TypeScript + Vite
- Supabase (auth, Postgres, storage) via `@supabase/supabase-js`
- React Router

## Setup

1. Create a Supabase project.
2. In the Supabase SQL editor, run `../supabase/schema.sql` to create the
   tables, row-level security policies, and the `rehearsal-audio` storage
   bucket.
3. Copy `.env.example` to `.env` and fill in your project URL and anon key
   (Supabase dashboard → Project Settings → API).
4. Install dependencies and start the dev server:

   ```bash
   npm install
   npm run dev
   ```

## What's here

- `src/context/AuthContext.tsx` — Supabase session state, sign in/up/out.
- `src/pages/Login.tsx`, `SignUp.tsx` — email/password auth.
- `src/pages/Upload.tsx` — uploads an audio file to the `rehearsal-audio`
  bucket and creates a `rehearsals` row (status `uploaded`).
- `src/pages/Dashboard.tsx` — lists a director's rehearsals; once a
  `rehearsal_plans` row (and its `drill_items`) exist for a rehearsal, shows
  the prioritized plan with a done/skip checkbox per drill item.

## Not built yet

- The pipeline that picks up `uploaded` rehearsals, converts audio with
  FFmpeg, runs tempo/rhythm analysis, and writes back a `rehearsal_plans` +
  `drill_items` row (this is what flips a rehearsal's status to `analyzed`).
- The Claude API call that turns structured analysis output into the plan
  `summary` and drill item text.
- Payments (Stripe) and multi-mic "pro tier" — intentionally out of MVP scope.
