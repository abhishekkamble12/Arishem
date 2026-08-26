# Implementation Plan: Frontend Improvements

## Overview

Implement eight targeted frontend improvements to align the Arishem React/TypeScript SPA with verified backend capabilities. Tasks are ordered by dependency: type improvements first (unblock other work), then new API modules, store extensions, component additions, and finally page-level wiring.

## Tasks

- [x] 1. Extend TypeScript types in `src/api/ai.ts`
  - Add `ReasoningStep` interface with all phases: `decomposition | retrieval | synthesis | self_critique | retry_synthesis` and all optional sub-fields
  - Update `QueryResponse` to add `agentic_mode: boolean`, `reasoning_steps: ReasoningStep[]`, and `critique_verdict: string` as first-class typed fields (remove all `(response as any)` casts that access these)
  - Add default-normalisation helper `normaliseQueryResponse(raw: QueryResponse): QueryResponse` that sets `agentic_mode = false`, `reasoning_steps = []`, `critique_verdict = "SKIPPED"` when absent
  - _Requirements: 3.1, 3.2, 3.4_

  - [ ]* 1.1 Write property test for QueryResponse default normalisation
    - **Property 6: QueryResponse type completeness**
    - For any partial QueryResponse missing `agentic_mode`, `reasoning_steps`, or `critique_verdict`, `normaliseQueryResponse` SHALL apply the correct defaults
    - **Validates: Requirements 3.1, 3.4**

- [x] 2. Create `src/api/workspace.ts` and extend `authStore`
  - Create `src/api/workspace.ts` exporting `workspaceApi.listWorkspaces(): Promise<Workspace[]>` calling `GET /auth/workspaces`
  - Add `workspaces: Workspace[]` and `refreshWorkspaces: () => Promise<void>` to `AuthState` interface in `authStore.ts`
  - Implement `refreshWorkspaces` to call `workspaceApi.listWorkspaces()`, update `workspaces`, and ensure `activeWorkspaceId` remains in the refreshed list (defaulting to first if not)
  - Initialise `workspaces` from `user.workspaces` in the store constructor (localStorage hydration)
  - _Requirements: 8.2, 8.3, 8.5_

  - [ ]* 2.1 Write property test for workspace consistency invariant
    - **Property 5: Workspace list consistency after refresh**
    - For any returned workspace array, after `refreshWorkspaces` completes, `activeWorkspaceId` SHALL always be contained in the list
    - **Validates: Requirements 8.1, 8.3**

- [~] 3. Call `refreshWorkspaces` after every successful auth event
  - In `LoginPage.tsx`: call `authStore.refreshWorkspaces()` after `authStore.setAuth(...)` (non-blocking, catch and ignore errors)
  - In `RegisterPage.tsx`: same pattern
  - In `GithubCallbackPage.tsx`: same pattern
  - In any Google OAuth callback: same pattern
  - _Requirements: 8.1, 8.4_

- [x] 4. Extend `client.ts` response interceptor with 503 and 429 handling
  - Add a lightweight toast event bus: export `onToast` (subscribe) and `emitToast` (publish) using browser `EventTarget` or a simple callback array — no new npm dependency
  - In the existing `apiClient.interceptors.response` error handler, add:
    - If `status === 429`: call `emitToast({ type: 'warning', message: 'Rate limit reached — please wait a moment before retrying.' })` then `Promise.reject(error)`
    - If `status === 503`: propagate unchanged (`Promise.reject(error)`) — the error message is read by the caller
  - Do NOT change the existing 401 refresh logic
  - _Requirements: 6.1, 6.3, 6.4_

  - [ ]* 4.1 Write property test for 429 toast uniqueness
    - **Property 2: 429 toast uniqueness**
    - For any single request returning 429, `emitToast` SHALL be called exactly once
    - **Validates: Requirements 6.1, 6.3**

- [ ] 5. Create `Toast` component and wire it into `AuthenticatedLayout`
  - Create `src/components/ui/Toast.tsx`: subscribes to `onToast` events via `useEffect`, renders a fixed-position amber banner, auto-dismisses after 5 seconds using `setTimeout`
  - Render only one Toast at a time (queue or replace on new toast)
  - Use Tailwind classes consistent with the existing dark design system
  - Add `<Toast />` inside `AuthenticatedLayout` in `App.tsx`
  - _Requirements: 6.1, 6.2_

- [x] 6. Create `ConfidenceBadge` component
  - Create `src/components/ui/ConfidenceBadge.tsx` with props `{ confidence?: number; llm_confidence?: number }`
  - Return `null` when both props are `undefined`
  - Render retrieval confidence badge and LLM confidence badge side by side
  - Apply colour classes: green (`bg-emerald-500/10 text-emerald-400`) for ≥ 0.8, amber for ≥ 0.5, red for < 0.5
  - When both values are below 0.5, render a "⚠ Possible out-of-domain response" warning label
  - Display value as `Math.round(value * 100)%`
  - _Requirements: 4.1, 4.2, 4.3, 4.4_

  - [ ]* 6.1 Write property test for ConfidenceBadge colour invariant
    - **Property 4: Confidence badge colour correctness**
    - For any float in [0, 1], the correct colour class SHALL be applied based on thresholds 0.5 and 0.8
    - **Validates: Requirements 4.1, 4.4**

  - [ ]* 6.2 Write property test for ConfidenceBadge null safety
    - **Property 3: ConfidenceBadge null safety**
    - When both `confidence` and `llm_confidence` are `undefined`, `ConfidenceBadge` SHALL render `null` without throwing
    - **Validates: Requirements 4.3**

- [~] 7. Integrate `ConfidenceBadge` into `DashboardPage`
  - Import `ConfidenceBadge` in `DashboardPage.tsx`
  - Replace the inline `llm_confidence` badge block with `<ConfidenceBadge confidence={msg.confidence} llm_confidence={msg.llm_confidence} />`
  - Remove all `(msg as any)` casts for `critique_verdict`, `agentic_mode`, `reasoning_steps` — use the typed `ChatMessage` fields directly (they already exist in `chatStore.ts`)
  - Update `chatStore.askQuestion` to call `normaliseQueryResponse` before mapping to `ChatMessage` to ensure defaults
  - _Requirements: 3.3, 4.1, 4.2_

- [ ] 8. Add file deletion to `UploadPage`
  - Add a file list section to `UploadPage.tsx` (similar to Dashboard's right panel, but simpler) that calls `aiApi.listFiles(activeWorkspaceId)` on mount
  - Show a delete button (Trash2 icon) on each file row, visible only when `user.role === 'editor' || user.role === 'admin'`
  - Implement `handleDeleteFile(s3Key)`: confirm dialog → `aiApi.deleteFile(s3Key)` → re-fetch list on success → show inline error on failure
  - Track `deletingKey` state to disable the delete button for the file currently being deleted
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

  - [ ]* 8.1 Write property test for delete error message fidelity
    - **Property 7: File deletion visibility** (error path)
    - For any API error response containing a `message` or `error` field, the displayed error text SHALL match the backend message
    - **Validates: Requirements 5.4**

- [ ] 9. Handle 503 error in `UploadPage`
  - In `handleSubmit` catch block, add a branch for `code === 503`: read `err.response?.data?.message` and set it as `errorMsg`
  - Ensure the form submit button is re-enabled after a 503 (existing `finally { setLoading(false) }` already handles this)
  - _Requirements: 1.1, 1.2, 1.3_

  - [ ]* 9.1 Write property test for 503 message propagation
    - **Property 1: 503 error message propagation**
    - For any non-empty backend message string in a 503 response, the displayed banner text SHALL equal that string
    - **Validates: Requirements 1.1, 1.3**

- [~] 10. Checkpoint — Ensure all tests pass
  - Run `npx vitest --run` and confirm all unit and property tests pass.
  - Verify TypeScript compilation with `tsc --noEmit` (zero errors, no `any` casts on QueryResponse fields).
  - Ask the user if any questions arise before proceeding.

- [ ] 11. Update `MonitoringPage` — confidence trend and drift timeline
  - Add `ConfidenceTrendChart` as an inline component or separate file in `src/components/ui/ConfidenceTrendChart.tsx`:
    - Accepts `chartData: ChartDataPoint[]` and `avgConfidence: number`
    - Uses Chart.js `Line` (already imported in MonitoringPage) with a horizontal annotation line at y=0.35
    - Colour the threshold annotation line red when `avgConfidence < 0.35`
  - Enhance the existing Drift Events panel in `MonitoringPage` to use a `DriftTimeline` rendering:
    - Show each drift event as a card with: drift score as a percentage, a coloured progress bar, and formatted timestamp
    - Events ordered descending by timestamp (already the case from backend ordering)
  - Ensure the `avg_confidence` KPI card shows `(stats.avg_confidence * 100).toFixed(1) + "%"` with the existing `confidencePct` variable (verify it's already correct and prominently labelled "Avg Retrieval Confidence")
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

  - [ ]* 11.1 Write property test for avg_confidence display formatting
    - **Property 8: Monitoring confidence trend data integrity**
    - For any `avg_confidence` float in [0, 1], the displayed string SHALL equal `(value * 100).toFixed(1) + "%"` 
    - **Validates: Requirements 7.1**

  - [ ]* 11.2 Write property test for drift timeline completeness
    - **Property — Drift timeline event completeness**
    - For any non-empty `DriftEvent[]`, every event's `id` and `drift_score` SHALL appear in the rendered output
    - **Validates: Requirements 7.2**

- [~] 12. Final checkpoint — Ensure all tests pass
  - Run `npx vitest --run` and confirm all tests pass.
  - Run `tsc --noEmit` to confirm zero TypeScript errors.
  - Verify in a running dev server that: 503 banner appears on upload, 429 toast appears from interceptor, workspace switcher renders for multi-workspace users, confidence badge shows under each assistant message, delete buttons appear on UploadPage, and monitoring shows confidence trend chart.
  - Ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP
- Each task references specific requirements for traceability
- Tasks 1–3 establish the type/API/store foundation; all subsequent tasks depend on them
- Task 4 (interceptor) and Task 5 (Toast) are independent of Tasks 6–11 and can be parallelised
- Property tests validate universal correctness properties; unit tests validate specific examples and edge cases
- Install dev dependencies before running tests: `npm install -D vitest @testing-library/react @testing-library/jest-dom fast-check jsdom`

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 1, "tasks": ["1", "4", "6"] },
    { "wave": 2, "tasks": ["2", "5"] },
    { "wave": 3, "tasks": ["3", "7", "8"] },
    { "wave": 4, "tasks": ["9", "10"] },
    { "wave": 5, "tasks": ["11"] },
    { "wave": 6, "tasks": ["12"] }
  ]
}
```
