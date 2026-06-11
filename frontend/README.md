# Arada Frontend (Next.js 14)

## Quick start
```bash
cp .env.local.example .env.local   # point API_URL at your backend
npm install
npm run dev                        # http://localhost:3000
```

## Architecture
- **httpOnly cookie auth** — the browser never sees the JWT. Login/register go
  through Next.js route handlers (`app/api/auth/*`) which proxy FastAPI and set
  `arada_access` / `arada_refresh` cookies.
- **API proxy** — all backend calls go through `/api/proxy/<path>`, which
  attaches the Bearer token server-side.
- **Middleware refresh** — `middleware.ts` refreshes the access token when it
  is within 5 minutes of expiry, and redirects to login when refresh fails.

## Commands
| Command | Purpose |
|---|---|
| `npm run dev` | Dev server |
| `npm run build` | Production build |
| `npm test` | Vitest suite |
| `npm run lint` | ESLint |
| `npm run format` | Prettier |

## Deploy
- **Docker**: `docker build -t arada-frontend . && docker run -p 3000:3000 --env-file .env.local arada-frontend`
- **Vercel**: set `API_URL` + `COOKIE_SECURE=true` in project env vars.
