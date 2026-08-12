# Arishem Engineering Onboarding

Welcome to the Arishem engineering team! Here is your quick start guide.

## 1. Workstation Setup
- Request access to the `arishem-dev` AWS account via Okta.
- Ensure you have Python 3.10+ installed. We use `uv` for dependency management.
- Generate an SSH key and add it to your GitHub profile.

## 2. Core Repository Structure
- `backend/`: Django REST API. We use PostgreSQL in production and Qdrant for our vector store.
- `frontend/`: React + Vite application.

## 3. Development Workflow
- Branch naming convention: `feature/XYZ-123-short-desc` or `bugfix/XYZ-123-short-desc`.
- All PRs require at least one approving review from a code owner before merging to `main`.
- We deploy to staging automatically when code merges to `main`. Production deployments happen every Tuesday and Thursday at 10 AM PST.

## 4. Contact
For urgent deployment issues, tag `@sre-oncall` in the `#eng-incidents` Slack channel.
