# Architecture and design decisions

```
 Browser ──HTTPS──> Static host (Vercel or Netlify)       React + Vite + Tailwind app (frontend/)
    │
    └────HTTPS + Bearer token──> Render web service        Flask API (backend/ + defect_analysis/)
                                      │
                                      └──TLS──> TiDB Cloud (MySQL-compatible database)
```

The frontend is a static build. It talks to the API only through `frontend/src/lib/api.js`, using the address in `VITE_API_URL`.

## Decisions

| Area | Decision | Why | Trade-off |
|---|---|---|---|
| Sign-in | JWT (HS256) sent as a Bearer token, 8-hour life | Works across two domains with no cookie or CSRF setup | Stored in `sessionStorage`, so an injected script could read it. See "Token safety" below |
| Session control | Each user has a `token_version` inside the token. Changing a password, disabling, rejecting or changing the role of a user bumps it | Ends stolen or old sessions immediately without a token blocklist | One version per user, so "sign out everywhere" is all or nothing |
| Passwords | Werkzeug scrypt hashes, at least 10 characters with a letter and a number, no username inside, common passwords refused | Slow hashing and sensible rules without annoying users | No breach-list check |
| Registration | Anyone can request an account as QC Engineer, Line Supervisor or Quality Manager. It stays **pending** until an IT Administrator approves it. IT Administrator can never be self-selected | Open sign-up must not give anyone access to quality data | Administrators must watch the pending list. There is no email notification yet |
| Brute force | 5 wrong passwords lock an account for 15 minutes. Sign-in and registration are also limited per IP address (in memory) | Stops password guessing | The IP limit is per server process. Use a proxy or WAF limit for stronger protection |
| Access control | Permissions per role live in `defect_analysis/config.py`. **Every API route checks them on the server.** The React menu is built from the permission list the server returns, so it only hides links | A hidden link is not security | Adding a role means editing one file |
| Last admin | The system refuses to disable, demote or reject the last active IT Administrator, or your own account | Prevents locking everyone out | None |
| Production guard | With `APP_ENV=production` the app refuses to start without a 32+ character `SECRET_KEY` and explicit `CORS_ORIGINS` | Unsafe settings fail loudly | None |
| CORS | Only the origins in `CORS_ORIGINS` may call `/api/*` | A random website cannot use a signed-in visitor's browser to call your API | Must be updated if the frontend URL changes |
| UI framework | Tailwind CSS 4 with hand-written components, Vite, React Router | Small bundle, full control of the look, no large component library to learn | Fewer ready-made widgets than Material UI |
| Navigation | A fixed sidebar on large screens and a slide-in drawer with a top bar on phones. Items come from `frontend/src/lib/nav.js` and the user's permissions | One place to edit, role-aware, keyboard friendly (skip link, Escape closes the drawer) | Pages not yet moved open in the classic page |
| Charts | Chart.js, loaded only when the dashboard opens | Keeps the sign-in page light | None |
| Hosting | Render (API) + TiDB Cloud (database) + Vercel or Netlify (frontend) | All have free tiers, and TiDB is MySQL-compatible, matching your report | See "Free-tier limits" in `DEPLOYMENT.md` |

## Token safety
The token is kept in `sessionStorage`, not `localStorage`, so it disappears when the tab closes. The app loads no third-party scripts (only Google Fonts CSS), tokens expire after 8 hours, and a password change ends old sessions. For a stricter setup, serve the frontend and API from one domain and move the token into an `HttpOnly` cookie with CSRF protection.

## What is not done yet
- Email verification, forgotten-password emails and two-factor sign-in. An administrator can reset a password instead.
- Database migrations (Alembic). Adding a column to an existing database needs the tables recreated or a manual `ALTER TABLE`.
- Refresh tokens, a central rate limiter, and a screen for the audit log (it is written to the `audit_log` table).
- Moving the remaining pages into the new app: alerts, corrective actions, thresholds, reports, dataset prediction, what-changed and similar periods. They work in the classic page served by the API at its root address.
- A free Render service has a temporary disk. The two prediction models are rebuilt at deploy or start, but anything written while the service runs is lost when it restarts.
