# Arishem Frontend — Ideal Build Plan


---

## 1. Stack

| Layer | Choice | Why |
|---|---|---|
| Framework | Vite + React 18 + TypeScript | Already decided in your README — fast dev, no Next.js overhead needed since no SSR/SEO requirement (it's an authenticated app) |
| State | Zustand | Lightweight, already chosen. Use for auth + active workspace only — not a dumping ground |
| Server state | TanStack Query (React Query) | Critical addition — you don't have this yet. Handles polling (job status), caching, retries, stale-while-revalidate. Don't hand-roll polling with `useEffect` + `setInterval` |
| Routing | React Router v6 | Already decided |
| Styling | Tailwind CSS + shadcn/ui primitives | Fast, consistent, avoids "generic Bootstrap" look if you customize tokens (see Aesthetics) |
| Charts | Recharts | For the monitoring dashboard (latency, confidence trend, drift) |
| Forms | React Hook Form + Zod | Login/register/upload metadata validation |
| Deploy | Vercel | Matches your existing zero-cost stack (Railway backend, Vercel frontend) |

---

## 2. Information Architecture — Pages (7 total)

1. **Login / Register** — single page, tab-toggle between the two, not separate routes. Social OAuth buttons (Google/GitHub) prominent since backend supports it.
2. **Workspace Selector** — shown right after login if user belongs to >1 workspace. Card grid, click to enter. Skip entirely (auto-redirect) if only one workspace — don't force an extra click.
3. **Dashboard (Home)** — the landing page inside a workspace. NOT the monitoring page. Shows: recent files, recent queries, quick "ask a question" bar, ingestion status widget if something's processing.
4. **Documents / Upload** — file list (table: name, type, chunks, status badge, uploaded by, date) + drag-and-drop upload zone. Status badges live-update via polling (PENDING → PROCESSING → SUCCESS/FAILED) using React Query's `refetchInterval`.
5. **Query / Chat** — the core feature. Chat-style interface, not a single search box. Each answer renders with: confidence score (visual, not just a number), cited source chips (clickable → opens source doc preview), and an OOD state that looks intentional ("no strong match" — not an error).
6. **Monitoring Dashboard** — editor/admin only (RBAC-gated route). Charts: query volume over time, avg latency, avg confidence, drift alerts list. This is a big differentiator for recruiters — make it visually the strongest page.
7. **Settings** — workspace members + roles (admin only), API/env info, maybe rate-limit usage indicator per role.

That's it — 7 pages is the right size. Don't add more; a bloated nav hurts a portfolio demo more than it helps.

---

## 3. Core Workflow (how a user actually moves through it)

```
Login/Register → (auto or manual) workspace select → Dashboard
                                                          │
                        ┌─────────────────────────────────┼─────────────────────┐
                        ▼                                 ▼                     ▼
                    Upload doc                       Ask question          Check monitoring
                        │                                 │                     │
              202 Accepted, show                  Chat bubble sent      Charts + drift
              PENDING badge                        → loading state      alerts render
                        │                          → answer streams in
              Poll every 2–3s via                  (or renders at once
              React Query until                     if no streaming)
              SUCCESS/FAILED                             │
                        │                          Confidence badge +
              Toast/notification                   citation chips shown
              on completion
```

Key UX principle: **the async upload must never feel broken**. Since ingestion takes 2–10s (or 30+ min for video), the UI needs an honest, visible state machine — a spinner alone isn't enough. Show the actual status word (Processing → Extracting → Embedding → Done) if your backend can expose sub-stages, or at minimum PENDING/PROCESSING/SUCCESS with a progress-feel (indeterminate bar, not fake percentage).

---

## 4. Query Page — Detailed Behavior (this is the page recruiters will actually interact with)

- **Layout**: chat thread on the left/center (70%), a collapsible right panel (30%) showing "sources used in this answer" with snippet previews.
- **Confidence display**: don't just print "0.73". Use a small horizontal bar or colored dot (red <0.35, yellow 0.35–0.6, green >0.6) — visual confidence is more scannable and shows product thinking.
- **Citations**: each citation is a clickable chip `[SOP-104.pdf]`. Clicking scrolls the right panel to that chunk, highlighting the retrieved snippet.
- **OOD state**: when confidence < 0.35 and backend short-circuits the LLM call, the UI should show this as a distinct message style (muted, not a red error) — e.g. "I couldn't find this in your documents" with a subtle icon, so it reads as expected behavior, not a bug.
- **Empty state**: first time in a workspace with no docs — the query box should be disabled with a nudge: "Upload a document to start asking questions."

---

## 5. Aesthetics & Visual Direction

Your README already says "glassmorphism" — that's a reasonable starting point but it's overused in student projects and can look dated/generic if not restrained. Recommendation:

- **Base**: dark mode default (RAG/AI tools read as more "technical product" in dark mode — Notion AI, Perplexity, etc. all default dark or offer it prominently). Light mode as toggle, not primary.
- **Color system**: one accent color used sparingly (confidence indicators, active states, primary CTA) — not gradient-heavy. A muted indigo/violet or teal reads as "AI product" without being cliché purple-gradient SaaS.
- **Typography**: Inter or Geist for UI text; a monospace font (JetBrains Mono / IBM Plex Mono) for anything technical — S3 keys, confidence scores, latency numbers, JSON snippets in the monitoring page. This mono/sans contrast is what makes technical dashboards look intentional rather than templated.
- **Glassmorphism**: use restrained — one subtle frosted panel (e.g., the query input bar) rather than every card. Overuse is the #1 sign of a template-following build.
- **Density**: this is a technical tool, not a marketing site — favor information density over generous whitespace on the Documents and Monitoring pages. Chat page can breathe more.
- **Micro-interactions**: status badge color transitions (amber→green) when polling resolves, skeleton loaders (not spinners) for file lists and chat history — these small details are what separate "built with Claude in an afternoon" from "thought about UX."

---

## 6. What Makes This "Ideal" for a Recruiter Demo Specifically

1. **Monitoring dashboard must load with real historical data**, not an empty state — seed it with realistic dummy PredictionLogs before a demo/interview so charts aren't blank.
2. **RBAC should be visibly demonstrable** — a role switcher or two seeded test accounts (viewer vs editor) so you can show the upload button being disabled/hidden for viewer role live.
3. **The OOD rejection should be demoable in one click** — have a pre-loaded "ask something unrelated" example so the interviewer sees the cost-saving feature working, not just described in a README.
4. **Loading states everywhere** — nothing should ever show a blank white flash; this alone signals more engineering maturity than most additional features would.

---

## 7. Build Order (so you don't stall)

1. Auth pages + protected routing + Zustand auth store
2. Workspace selector + context provider
3. Documents page (upload + polling list) — this validates your async backend end-to-end early
4. Query/chat page — the core value prop, get this working with real backend before polishing
5. Monitoring dashboard — charts last, since it depends on having real query data flowing already
6. Settings/RBAC UI
7. Pass: dark mode polish, skeleton loaders, empty states, mobile responsiveness (secondary priority — this is a desktop-first tool)

Skip animation libraries (Framer Motion) until steps 1–6 are done — polish after function, not instead of it.