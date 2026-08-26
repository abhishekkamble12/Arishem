# Requirements Document

## Introduction

This document captures the functional requirements for eight frontend improvements to the Arishem RAG platform. The improvements align the React 18 + TypeScript frontend with verified backend capabilities, closing gaps in error handling, type fidelity, UI transparency, and monitoring visualisation.

---

## Glossary

- **System**: The Arishem frontend React application.
- **UploadPage**: The `/upload` route (`UploadPage.tsx`), accessible to `editor` and `admin` roles.
- **DashboardPage**: The `/` route (`DashboardPage.tsx`), the main chat and file-management view.
- **MonitoringPage**: The `/monitoring` route (`MonitoringPage.tsx`), accessible to `editor` and `admin` roles.
- **Navbar**: The persistent top navigation bar component (`Navbar.tsx`).
- **authStore**: The Zustand store (`authStore.ts`) managing authentication state.
- **chatStore**: The Zustand store (`chatStore.ts`) managing chat messages and file state.
- **workspaceApi**: A new API module (`src/api/workspace.ts`) wrapping `GET /auth/workspaces`.
- **QueryResponse**: The TypeScript interface in `src/api/ai.ts` representing the `/ai/query` response.
- **ConfidenceBadge**: A new component rendering retrieval and LLM confidence scores under each assistant message.
- **WorkspaceSwitcher**: A dropdown component inside the Navbar for switching active workspaces.
- **DriftTimeline**: A visualisation component within MonitoringPage listing recent drift events.
- **ConfidenceTrendChart**: A Chart.js line chart within MonitoringPage showing per-day average confidence.
- **Toast**: A transient UI notification that auto-dismisses.
- **Retrieval confidence**: The `confidence` field on `QueryResponse`, representing the Qdrant similarity score.
- **LLM confidence**: The `llm_confidence` field on `QueryResponse`, the model's self-assessed confidence.
- **503 backpressure**: The HTTP 503 response the backend returns when the ingestion queue depth exceeds 50 jobs.
- **429 rate-limit**: The HTTP 429 response the backend returns when a user exceeds role-based throttle.

---

## Requirements

### Requirement 1: 503 Queue-Full Error Handling on Upload

**User Story:** As an editor or admin, I want to see a clear message when the ingestion system is too busy, so that I know to try again later rather than assuming my upload failed.

#### Acceptance Criteria

1. WHEN the backend returns HTTP 503 during a file upload, THE System SHALL display the `message` field from the response body as the error text in the UploadPage error banner.
2. WHEN a 503 error is displayed, THE System SHALL keep the upload form enabled so the user can retry without refreshing the page.
3. WHEN the backend returns HTTP 503 during a file upload, THE System SHALL NOT display a generic fallback error message that omits the backend's explanation.

---

### Requirement 2: Workspace Switcher in Navbar

**User Story:** As a user who belongs to multiple workspaces, I want to switch between them from the navigation bar, so that I can query different knowledge bases without logging out.

#### Acceptance Criteria

1. WHEN the authenticated user belongs to more than one workspace, THE Navbar SHALL render a WorkspaceSwitcher dropdown listing all workspaces by name.
2. WHEN a user selects a workspace from the WorkspaceSwitcher, THE authStore SHALL update `activeWorkspaceId` to the selected workspace's id.
3. WHEN the active workspace changes, THE chatStore SHALL re-fetch the file list for the new workspace.
4. WHEN the authenticated user belongs to only one workspace, THE Navbar SHALL NOT render the WorkspaceSwitcher dropdown.
5. WHEN workspace data is not yet loaded, THE WorkspaceSwitcher SHALL NOT crash or render broken UI.

---

### Requirement 3: Complete `QueryResponse` TypeScript Type

**User Story:** As a developer, I want the `QueryResponse` interface to match the actual backend response, so that I can access agentic fields without unsafe `any` casts.

#### Acceptance Criteria

1. THE `QueryResponse` interface in `src/api/ai.ts` SHALL include `agentic_mode: boolean`, `reasoning_steps: ReasoningStep[]`, and `critique_verdict: string` as first-class typed fields.
2. THE `ReasoningStep` interface SHALL be exported from `src/api/ai.ts` and define all known phases: `decomposition`, `retrieval`, `synthesis`, `self_critique`, and `retry_synthesis`.
3. WHEN the `chatStore` maps a `QueryResponse` to a `ChatMessage`, THE mapping SHALL use typed field access (`response.agentic_mode`, `response.reasoning_steps`, `response.critique_verdict`) without casting to `any`.
4. WHEN the backend returns `agentic_mode`, `reasoning_steps`, or `critique_verdict` as absent or null, THE System SHALL default them to `false`, `[]`, and `"SKIPPED"` respectively.

---

### Requirement 4: Confidence Indicator in Chat

**User Story:** As a viewer or editor querying the knowledge base, I want to see a visual confidence indicator for each answer, so that I can gauge how reliable the response is.

#### Acceptance Criteria

1. WHEN an assistant message contains `llm_confidence` or `confidence`, THE DashboardPage SHALL render a `ConfidenceBadge` component beneath the answer text showing the confidence as a percentage.
2. WHEN `llm_confidence` is below 0.5 AND `confidence` is below 0.5, THE ConfidenceBadge SHALL include a visual warning indicator to signal a possible out-of-domain response.
3. WHEN both `confidence` and `llm_confidence` are undefined, THE ConfidenceBadge SHALL render nothing without throwing an error.
4. THE ConfidenceBadge SHALL use green styling for values ≥ 0.8, amber for values ≥ 0.5 and < 0.8, and red for values < 0.5.

---

### Requirement 5: File Deletion in UploadPage

**User Story:** As an editor or admin, I want to delete ingested files from the UploadPage, so that I can manage the knowledge base without navigating to the Dashboard.

#### Acceptance Criteria

1. WHEN the authenticated user has `editor` or `admin` role, THE UploadPage SHALL render a delete button for each file in the ingested file list.
2. WHEN a delete button is clicked, THE System SHALL prompt the user for confirmation before calling `DELETE /ai/files/delete`.
3. WHEN a file is successfully deleted, THE System SHALL refresh the file list and display a success indicator.
4. IF the delete request fails, THEN THE System SHALL display the error message from the response and NOT remove the file from the displayed list.
5. WHEN a delete operation is in progress, THE System SHALL disable the delete button for that specific file to prevent duplicate requests.

---

### Requirement 6: Rate-Limit Feedback (429)

**User Story:** As any authenticated user, I want to see a friendly message when I hit the rate limit, so that I understand why my request failed and know I should wait.

#### Acceptance Criteria

1. WHEN any API request returns HTTP 429, THE System SHALL display a Toast notification with the message "Rate limit reached — please wait a moment before retrying."
2. WHEN a 429 Toast is displayed, THE System SHALL auto-dismiss it after 5 seconds.
3. WHEN a single API request returns HTTP 429, THE System SHALL display exactly one Toast notification (no duplicates).
4. THE 429 Toast handling SHALL be implemented in the `client.ts` response interceptor so that all pages benefit without per-page code.

---

### Requirement 7: Monitoring Page Improvements

**User Story:** As an admin or editor, I want the monitoring dashboard to show average confidence trends and drift event details, so that I can track retrieval quality over time.

#### Acceptance Criteria

1. THE MonitoringPage SHALL display `avg_confidence` as a percentage (value × 100, rounded to one decimal place) in the KPI card, styled with green/amber/red colour coding.
2. WHEN `recent_drifts` contains one or more events, THE MonitoringPage SHALL render a `DriftTimeline` component showing each event's score and timestamp in descending chronological order.
3. WHEN `recent_drifts` is empty, THE MonitoringPage SHALL display a "No Drift Detected" empty state in the drift section.
4. THE MonitoringPage SHALL render a `ConfidenceTrendChart` line chart using the per-day query data available in `chart_data`, annotated to show the 0.35 drift-threshold line.
5. WHEN `avg_confidence` drops below 0.35, THE drift threshold line on the ConfidenceTrendChart SHALL be rendered in red.

---

### Requirement 8: Workspace Refresh After Login

**User Story:** As a user, I want my workspace list to be refreshed from the server after I log in, so that newly added workspaces appear without requiring a page reload.

#### Acceptance Criteria

1. WHEN a user successfully authenticates (login, register, or OAuth callback), THE authStore SHALL call `GET /auth/workspaces` to fetch the latest workspace list.
2. THE authStore SHALL expose a `refreshWorkspaces` action that calls `workspaceApi.listWorkspaces()` and updates `authStore.workspaces`.
3. WHEN `refreshWorkspaces` completes successfully, THE authStore SHALL update `activeWorkspaceId` to remain valid — if the current id is not in the refreshed list, it SHALL default to the first workspace in the list.
4. IF the `GET /auth/workspaces` call fails during or after login, THE System SHALL NOT block the user from proceeding — the workspace list from the login response SHALL be used as a fallback.
5. THE `src/api/workspace.ts` module SHALL export `workspaceApi.listWorkspaces()` which calls `GET /auth/workspaces` and returns a `Workspace[]`.
