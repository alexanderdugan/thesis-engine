# ADR 0003: Live kill switch is relative to SPY

Status: Accepted
Date: 2026-11-05
Supersedes: the "Standing kill rule" line in ADR 0001, and the "strategy paper equity down >25%
from peak" health check in Phase 4 §9.

## Context
ADR 0001 set the standing kill rule as "paper equity down >25% from peak". A fixed threshold
ignores the market: in a broad sell-off a long-only, equal-weight portfolio of 30 stocks can fall
25% while doing exactly what it was designed to do, and halting it then measures the market, not
the strategy. The kill switch should catch a strategy that is broken, which shows up as falling
well behind SPY.

This is a risk control on live paper trading, not a backtest pass criterion. It is recorded before
any backtest has run, so changing it doesn't touch the pre-registration in ADR 0001.

## Decision
Live paper trading halts if **either** condition holds on any daily check:

1. **Relative:** the strategy's drawdown from its equity peak exceeds SPY's drawdown over the same
   window (from the date of the strategy's peak to today, SPY total return) by more than
   **10 percentage points**.
   - Example: strategy −28% from peak, SPY −15% over that same window → 13 points worse → halt.
2. **Absolute:** the strategy's drawdown from its equity peak exceeds **40%**, whatever SPY did.
   - Why: a backstop. Being "only" 10 points behind a market that fell 35% is still a loss I
     wouldn't keep automating without a human looking.

On a halt: no orders are placed, `TRADING_ENABLED` is set to `false`, and a GitHub Issue labeled
`needs-triage` is opened (Phase 4 §9). Re-enabling is a manual decision.

## Consequences
- The 10-point margin matches the max-drawdown tolerance in ADR 0001's Gate A, so the live rule
  and the backtest rule measure risk the same way.
- The health check needs SPY total-return prices up to the check date, so it depends on the
  nightly price update being fresh (already a health check in §9).
- All other ADR 0001 criteria are unchanged.
