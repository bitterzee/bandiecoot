# Bandiecoot

A private web app for the 7 members of Bandiecoot (Cendana Rumbai, class of 2004):
pixel maps of Camp Rumbai and SMP/SMA Cendana, shared photo moments, the Jamesbon Room
(end-to-end encrypted stories), the band studio with relay jam and a rhythm game.

Static site (one `index.html`, no build) + Supabase (auth, Postgres, storage, realtime), hosted on Vercel.

## How access works

- Sign-in is by emailed link or 6-digit code (Supabase email OTP).
- Only emails in `public.members` can create an account (before-user-created hook), and the list is capped at 7 (`add_member`).
- Every table and the `media` storage bucket are protected by row-level security: only members can read or write.
- The admin (renrasfuldi@gmail.com) invites people from **Akun** in the app.
- Jamesbon Room stories are encrypted in the browser with a key derived from the room PIN (PBKDF2 → AES-256-GCM). The database only stores ciphertext; a forgotten PIN can't be recovered.

## What's in here

| Path | What it is |
| --- | --- |
| `index.html` | The whole app (UI, audio engine, pixel maps, sync). |
| `config.js` | Supabase URL and public anon key. |
| `supabase/migrations/` | Schema: members/invites, `items` (all shared data), `media` bucket, RLS. |
| `api/bike.mjs` | Kereta Den's "Bengkel Claude": members ask Claude for small changes to the shared bike (needs `ANTHROPIC_API_KEY` in Vercel; 15 per person per day). |
| `vercel.json` | Static hosting config and headers. |
| `.github/workflows/database.yml` | Applies new migrations on merge to `main`. |

## One-time setup

1. **Supabase → Authentication → Hooks → Before User Created:** enable, Postgres function `public.hook_before_user_created`.
2. **Supabase → Authentication → URL Configuration:** Site URL = your Vercel address; add `https://YOUR-SITE/**` to Redirect URLs.
3. **Supabase → Authentication → Emails → Magic Link:** add `Kode kamu: {{ .Token }}` next to the link, so people on the home-screen app can type the code.
4. **Supabase → Authentication → SMTP:** add a sender (same as Capcus). The built-in sender only mails project owners and is rate-limited, so the other 6 won't get emails without this.
5. **Vercel:** Add New → Project → import this repo → Deploy (no build settings needed).
6. **Vercel → Settings → Environment Variables:** `ANTHROPIC_API_KEY` for the Kereta Den bike workshop (optional `BIKE_MODEL`, default `claude-haiku-5-5`). Redeploy after adding.
7. **GitHub → Settings → Secrets:** `SUPABASE_ACCESS_TOKEN`, `PRODUCTION_DB_PASSWORD` for the migration workflow.

Every push to `main` redeploys.
