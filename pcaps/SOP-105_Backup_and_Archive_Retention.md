# Arishem Technologies SOP-105: Backup and Archive Retention

Effective Date: April 1, 2026
Owner: Head of Infrastructure

## 1. Purpose

SOP-105 sets retention periods for backups, archives and audit trails. It does not
cover API prediction logs, which are governed separately by SOP-104. Where the two
documents appear to overlap, SOP-104 applies to prediction logs and SOP-105 applies
to everything listed below.

## 2. Database backups

Production PostgreSQL is snapshotted automatically every night. Daily snapshots are
retained for 35 days. On the first day of each month one snapshot is promoted to a
monthly snapshot, and monthly snapshots are retained for 12 months. Snapshots are
encrypted at rest and copied to a second AWS region within 24 hours of being taken.
Restores are tested once per quarter by the infrastructure team.

## 3. Email archives

All corporate email is archived by the mail provider and retained for 7 years from
the date the message was sent. Employees cannot delete messages from the archive,
even when they delete them from their own mailbox.

## 4. Audit trails

Application audit logs, stored in the AuditEvent table, are retained for 1 year.
Security logs collected by the SIEM are retained for 400 days, so that a full
year-on-year comparison is always possible during an investigation.

## 5. Account deletion

When a user asks for their account to be deleted, their personal data must be purged
from production systems within 30 days of the request. Backups containing that data
expire on their normal schedule and are not edited.

## 6. Legal hold

A legal hold suspends every retention period in this document and in SOP-104 for the
data it names. Only the General Counsel (legal@arishem.com) can place or lift a legal
hold. The compliance officer can request a hold but cannot place one.
