# Arishem Technologies OPS-401: Incident Response Runbook

Effective Date: May 1, 2026
Owner: SRE Team

## 1. Severity levels

- **SEV1**: a customer-facing outage, or any confirmed data breach.
- **SEV2**: degraded performance, or an outage affecting a single customer.
- **SEV3**: a problem confined to internal tooling with no customer impact.

## 2. SEV1 response

The on-call engineer must be paged through PagerDuty within 5 minutes of a SEV1
being declared. An incident commander is assigned immediately and owns all decisions
until the incident is closed. The public status page must be updated within 15
minutes, and the Support lead handles all customer communication.

While a SEV1 is active, all production deployments are frozen, including the
scheduled Tuesday and Thursday deployments. The freeze lifts only when the incident
commander closes the incident.

## 3. SEV2 response

Post in the `#eng-incidents` Slack channel and tag `@sre-oncall` within 30 minutes
of noticing the problem. A SEV2 does not page anyone outside working hours.

## 4. SEV3 response

Open a ticket in the OPS project in Jira. SEV3 tickets are triaged within one
business day.

## 5. Data breaches

A confirmed data breach is always a SEV1. In addition to the SEV1 steps, notify
security@arishem.com and the General Counsel immediately. If personal data is
involved, the relevant regulators must be notified within 72 hours of the breach
being confirmed.

## 6. Postmortems

Every SEV1 and SEV2 requires a blameless postmortem, published within 5 business
days of the incident closing. SEV1 postmortems are reviewed by the CTO before
publication.
