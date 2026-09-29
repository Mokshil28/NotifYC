# NotifYC frontend

Local React + Vite + Tailwind CSS v4 presentation app. This checkout does not
run inside Figma Make. Check whether port 8443 is already in use before starting
another development server.

## Entry points

- `src/main.tsx` mounts `LiveShell` and `App`.
- `src/live-shell.tsx` supplies DeepSpace auth and record providers.
- `src/App.tsx` contains the overview, camera wall and incident view.
- `src/index.css` imports Tailwind v4 and contains the app styles.
- `vite.config.ts` aliases shared code from `../deepspace/src` and proxies API
  and WebSocket requests to the backend on port 5173.
- `public/cv/` contains the camera videos currently used by the UI.

## Commands

Use the tracked pnpm lockfile for frontend dependency installs (`pnpm install`).
Run `pnpm dev` for the frontend, and start the backend separately from
`../deepspace`. `pnpm build` checks the production bundle.

Do not treat hard-coded demo reports in `App.tsx` as fresh CV results.
Generated CV outputs belong under `../outputs/`, which is gitignored.
