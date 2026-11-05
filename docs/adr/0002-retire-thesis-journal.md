# ADR 0002: Retire the thesis journal account; strategy uses the sole paper account

Status: Accepted
Date: 2026-11-05

## Context
Phases 1–3 used the Alpaca paper account for human-judgment trades logged in the thesis journal.
Phase 4 §8 preferred a separate paper account for the systematic strategy, to keep the two from
mixing.

## Decision
The thesis journal's trading use is retired. Discretionary trades need human judgment, which
doesn't fit an automated system. The systematic strategy uses the single existing paper account.
The paper account is reset before strategy go-live, so no old positions mix into strategy
performance.

The journal code and dashboard views stay in the repo, unused, until removing them is
worthwhile.

## Consequences
- No second Alpaca account needed. This supersedes the "separate account" preference in Phase 4 §8.
- Strategy performance tracking starts from a clean account.
- If a human-vs-algorithm comparison is wanted later, it needs its own account at that point.
