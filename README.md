# NeuroNudge

Predictive wellness tracker for SDG 3 (Good Health & Well-Being).
FastAPI + PostgreSQL + Scikit-learn backend, vanilla JS frontend, deployed on Vercel.

## Deploy in 5 steps

1. **Provision Postgres** (free): create a database on [Neon](https://neon.tech),
   [Supabase](https://supabase.com), or [Railway](https://railway.app) and
   copy the connection string.
2. **Push this folder to GitHub.**
3. **Import to Vercel** → New Project → select the repo → Deploy.
4. In Vercel → Project → Settings → Environment Variables, add:
   - `DATABASE_URL` = your Postgres connection string (must include `?sslmode=require` for Neon/Supabase)
   - `JWT_SECRET`   = a long random string (e.g. `openssl rand -hex 32`)
5. Redeploy. Tables are created automatically on first request.

## Local dev

```bash
npm i -g vercel
vercel dev
```

Set the same env vars in a local `.env` file.

## Architecture

- `/api/index.py` — FastAPI app, mounted by Vercel's Python runtime
- `/api/database.py` — SQLAlchemy engine, models, session dependency
- `/api/predictive_model.py` — Decision Tree Classifier + nudge generator
- `/public/*` — static HTML/CSS/JS served by Vercel's static builder
- `vercel.json` — routes `/api/*` to the Python function, everything else to `public/`
