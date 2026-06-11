# plan: w4w dashboard vercel demo

deploy a safe dashboard demo to Vercel as `w4w-tooling`. hosted demo must show useful dashboard/rides/routes, fake pushed metrics, and block every OSM mutation path.

## validation

- `cd dashboard && pnpm lint` — lint clean
- `cd dashboard && NEXT_PUBLIC_W4W_DEMO_MODE=1 W4W_DASHBOARD_MODE=demo pnpm build` — production build passes in demo mode
- `cd dashboard && pnpm dev:demo` — local demo pages/API guards work before deploy
- `vercel deploy --prod` or equivalent Vercel project deploy — hosted demo available
- browser checks for `/`, `/rides/<demoRideId>`, `/logs`, `/api/maps/<demoRideId>` — previewable routes

latest validation:
- `pnpm lint` passed
- `NEXT_PUBLIC_W4W_DEMO_MODE=1 W4W_DASHBOARD_MODE=demo pnpm build` passed
- local demo HTTP checks passed: `/`, `/rides/258276934`, `/logs`, `/api/maps/258276934`, missing ride 404
- local mutation checks passed: push/export-yaml/run-batch all 403 in demo
- production deploy passed: `https://w4w-tooling.vercel.app`
- hosted HTTP checks passed: `/`, `/rides/258276934`, `/logs`, `/api/maps/258276934`, missing ride 404
- hosted mutation checks passed: push/export-yaml/run-batch all 403 in demo
- browser tool not available in this thread; Playwright not installed. HTTP + HTML checks used instead.

## constraints

- no OSM OAuth vars/secrets in Vercel demo.
- demo must not call `osm_edit.py`, write YAML, run pipeline, or open iD editor mutation links.
- server guards required; client-only disabled buttons are not enough.
- committed demo artifacts may contain route traces; keep private for now, but avoid adding secrets/tokens.
- fake pushed numbers are demo-only, clearly sourced from demo data/config, not real upload log.
- do not duplicate dashboard code back into `w4w`; `w4w` can link/embed the Vercel demo later.

## context

dashboard now exists in `dashboard/` inside `w4w-tooling`. demo artifacts are in `dashboard/demo-output/output`. current demo mode uses `NEXT_PUBLIC_W4W_DEMO_MODE=1` / `W4W_DASHBOARD_MODE=demo`; mutation APIs already return 403 in demo. Vercel CLI installed. repo not linked to Vercel yet.

## tasks

### 1. demo data + fake metrics

files:
- modify: `dashboard/demo-output/output/*`
- modify: `dashboard/lib/manifest.ts`
- modify: `dashboard/lib/impact.ts`
- modify: `dashboard/app/(review)/page.tsx`
- modify: `dashboard/app/(review)/logs/page.tsx`

done: local demo shows non-zero pushed/impact metrics without a real `output/upload_log.jsonl`

[x] add demo-only fake upload/impact fixture
notes: added `dashboard/demo-output/output/demo_upload_log.jsonl`; demo reads it, local still reads real `output/upload_log.jsonl`

[x] make fake pushed count visible on landing, ride rail, ride detail, logs
notes: visible as 12 sample pushes, 5 touched rides, ride-level partial statuses

[x] label demo metrics as demo/sample data where needed
notes: landing + logs label demo/sample; recent push rail marks demo entries

[x] keep real local mode reading real `output/upload_log.jsonl`
notes: -

### 2. mutation safety hardening

files:
- modify: `dashboard/app/api/rides/[rideId]/push/route.ts`
- modify: `dashboard/app/api/rides/[rideId]/export-yaml/route.ts`
- modify: `dashboard/app/api/run-batch/route.ts`
- modify: `dashboard/app/(review)/rides/[rideId]/ride-review.tsx`
- modify: `dashboard/components/osm-login-pill.tsx`

done: push/export/run-batch/iD links blocked in browser and direct HTTP calls return 403 in demo

[x] audit all mutation entrypoints
notes: include buttons, row links, direct API routes

[x] verify demo guards run before file writes/spawn/token probes
notes: server guards are before body writes/spawn/token probe; local + hosted direct POST returned 403

[x] add/adjust lightweight tests or scripted checks for 403s
notes: curl checks used locally and against hosted prod

### 3. Vercel project config

files:
- modify: `dashboard/vercel.json`
- modify: `dashboard/package.json`
- modify: `dashboard/README.md`
- modify: `.env.example`

done: Vercel project `w4w-tooling` deploys from `dashboard/` root with demo env and Mapbox token

[x] link/create Vercel project named `w4w-tooling`
notes: linked/created `1ar/w4w-tooling`; production alias is `https://w4w-tooling.vercel.app`

[x] configure env vars: `MAPBOX_ACCESS_TOKEN`, demo flags, optional tooling repo URL
notes: production/development env set for Mapbox + demo flags; no OSM vars. no git remote, so repo URL omitted. preview env CLI asked for branch despite all-preview command; `vercel.json` still carries demo flags.

[x] ensure install/build commands work on Vercel
notes: Vercel install/build passed with `pnpm install --frozen-lockfile`, `pnpm build`

[x] document exact deploy command/result URL
notes: `vercel deploy --prod --yes`; production `https://w4w-tooling.vercel.app`; deployment `https://w4w-tooling-6hkjbzjjk-1ar.vercel.app`

### 4. route preview QA

files:
- modify: `dashboard/app/(review)/page.tsx`
- modify: `dashboard/app/(review)/rides/[rideId]/page.tsx`
- modify: `dashboard/app/(review)/logs/page.tsx`
- modify: `dashboard/app/api/maps/[rideId]/route.ts`

done: hosted demo route set renders without blank/500 states

[x] verify `/` landing page
notes: local + hosted 200; route table + fake impact visible

[x] verify `/rides/<demoRideId>`
notes: verified `/rides/258276934` local + hosted 200; iframe route present; proposals table populated

[x] verify `/logs`
notes: local + hosted 200; fake pushed routes visible

[x] verify `/api/maps/<demoRideId>`
notes: local + hosted 200; `__MAPBOX_ACCESS_TOKEN__` count 0, `mapboxgl.accessToken` count 1

[x] verify a missing ride returns sane 404/empty state
notes: local + hosted `/rides/not-a-ride` returned 404

### 5. final deploy report

files:
- modify: `docs/plans/2026-06-09-w4w-dashboard-vercel-demo.md`

done: plan checkboxes updated, deployment URL reported, tests listed

[x] run final `git status` and diff review
notes: `.vercel/` ignored; no secrets printed; dashboard remains uncommitted per instruction

[x] run final validation commands
notes: lint/build/local HTTP/hosted HTTP/API checks passed; browser visual not available

[x] report Vercel URL + remaining limitations
notes: report `https://w4w-tooling.vercel.app`; metrics are demo-only fake fixture

## appendix: raw input

not implementation spec. preserved for intent/history. do not rewrite.

### initial request

````text
we will make it public later, let's first focus on making a demo of the dashboard and deploying it to vercel. you can call it w4w-tooling so that we have w4w-tooling.vercel.app on preview. make sure you can't actually push to OSM from the demo, but we need to make sure the previews and at least some routs can be previewed. we also should be able to "fake" some numbers of how many routes have been pushed. go create a plan, then create a new thread to build it. 
````
