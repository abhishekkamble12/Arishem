# Arishem Technologies SEC-301: Information Security Policy

Effective Date: February 1, 2026
Owner: Security Team (security@arishem.com)

## 1. Authentication

Multi-factor authentication is mandatory for every company account, and is enforced
through Okta. Accounts without MFA enrolled are disabled after 7 days.

## 2. Devices

All company laptops must use full-disk encryption. A lost or stolen device must be
reported to security@arishem.com within 1 hour of the loss being noticed, so the
device can be wiped remotely.

## 3. Code review for sensitive services

The general rule in the engineering onboarding guide is one approving review before
merging to `main`. Changes to the `payments/` or `auth/` services are stricter: they
require two approving reviews, and at least one of those must come from the security
team (the `@security-reviewers` group in CODEOWNERS).

## 4. Secrets

Secrets must never be committed to a repository. If a secret is committed or
otherwise exposed, it must be rotated within 24 hours, even if the commit is removed.

## 5. Production database access

Direct access to the production database is permitted only through the bastion host,
with session recording enabled. Each access request must be approved by the Head of
Infrastructure, and approved access expires automatically after 8 hours.

## 6. Training

All full-time employees complete security awareness training once a year. New
full-time hires must complete it within 14 days of their start date. Contractor
requirements are set out in HR-202.
