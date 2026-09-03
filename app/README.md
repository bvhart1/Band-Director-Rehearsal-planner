# Rehearsal Coach (web app)

Mobile-friendly web app for band directors: record or upload rehearsal audio,
and get a prioritized, plain-language plan for the next rehearsal.

Deployed to GitHub Pages via `.github/workflows/deploy.yml`. Talks to
Supabase directly for auth/uploads/reads, and to the `backend/` service
(see `../backend/README.md`) for the actual audio analysis and Claude plan
generation.

## Stack

- React + TypeScript + Vite
- Supabase (auth, Postgres, storage) via `@supabase/supabase-js`
- React Router (`HashRouter`, so client-side routes work on static GitHub
  Pages hosting without server rewrite rules)

## Setup

1. Create a Supabase project.
2. In the Supabase SQL editor, run `../supabase/schema.sql` to create the
   tables, row-level security policies, and the `rehearsal-audio` storage
   bucket.
3. Deploy `../backend/` somewhere (see its README) and note its URL.
4. Copy `.env.example` to `.env` and fill in your Supabase project URL/anon
   key and the backend URL.
5. Install dependencies and start the dev server:

   ```bash
   npm install
   npm run dev
   ```

For the deployed GitHub Pages build, set `VITE_SUPABASE_URL`,
`VITE_SUPABASE_ANON_KEY`, and `VITE_BACKEND_URL` as **Actions secrets**
(Settings → Secrets and variables → Actions) — the deploy workflow injects
them at build time.

## What's here

- `src/context/AuthContext.tsx` — Supabase session state, sign in/up/out.
- `src/pages/Login.tsx`, `SignUp.tsx` — email/password auth.
- `src/pages/Upload.tsx` — uploads an audio file to the `rehearsal-audio`
  bucket, creates a `rehearsals` row, and calls the backend to kick off
  analysis.
- `src/pages/Dashboard.tsx` — lists a director's rehearsals, polling while
  any are `uploaded`/`processing`; once a `rehearsal_plans` row (and its
  `drill_items`) exist, shows the prioritized plan with a done/skip
  checkbox per drill item. Shows a retry button on `failed` (with the
  backend's error message) or stalled `uploaded` rehearsals.
- `src/lib/analysis.ts` — calls the backend's `/analyze/{id}` endpoint with
  the user's Supabase access token.

## Not built yet

Payments (Stripe) and the multi-mic "pro tier" — intentionally out of MVP
scope.
