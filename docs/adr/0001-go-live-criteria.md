# ADR 0001: Go-live criteria

Status: Accepted
Date: 2026-11-05

## Context
Before any backtest runs, define what result allows the strategy to trade automatically in
paper, and what result would count as real evidence later. Written and committed before any
results exist, so the criteria can't be fit to them.

Two known limits shape this:
1. **Short windows are noisy.** Over ~2 years of monthly returns, the standard error of an
   annualized information ratio is roughly ±0.7. A holdout alone can't prove skill. It can only
   catch strategies that are clearly broken.
2. **LLM contamination.** The feature-extraction model was trained on data that likely overlaps
   most of any recent holdout. Identity masking reduces this but doesn't remove it. The only
   fully clean test is live paper trading after go-live.

So there are two gates: a backtest gate that permits paper automation (low stakes), and a live
gate that counts as actual evidence.

## Decision

### Gate A: backtest → permission to paper trade automatically
**Holdout:** the most recent 24 months of available data at the time M4 runs. Not fit, tuned or
viewed until one final run with `--final-holdout`.

Development window (everything before the holdout), net of costs:
- Information ratio vs SPY ≥ 0.4
  - Why: the dev window is long (~8 years), so this is the strongest statistical evidence
    available. It's also where overfitting happens, so it's necessary but not sufficient.

Holdout, net of costs:
- Excess return vs SPY > 0 **and** information ratio ≥ 0.2
  - Why: given the noise, this only screens out strategies that fall apart out of sample. It
    isn't proof.
- Max drawdown ≤ SPY's max drawdown over the same window + 10 percentage points
  - Why: a 30-stock portfolio will be more volatile than the index. More than 10 points worse
    means risk I wouldn't accept.
- Still positive excess return with trading costs doubled
  - Why: cost assumptions are guesses. An edge that disappears at 2× costs is a cost-model
    artifact.
- Average monthly turnover ≤ 60%
  - Why: above this, the costs and the "edge" start to look like the same thing.

Robustness (both windows):
- ±20% changes to top-N, rebalance lag and cost assumptions don't flip the sign of excess return
  - Why: a real effect shouldn't depend on one exact parameter setting.

LLM features:
- Kept only if the composite with them beats the composite without them (factors + text
  similarity) on the dev window **and** doesn't do worse on the holdout. Otherwise they're
  dropped and the strategy runs without them.
  - Why: the LLM is the expensive part. It has to earn its place.

Multiple testing:
- Every backtest run is logged. The final report states how many strategy variants were tried.
  - Why: try 50 variants and one will look great by chance. The count is part of the evidence.

### Gate B: live paper → counts as evidence
After **12 months** of automated paper trading:
- Excess return vs SPY > 0, **and** live results fall within the range the backtest predicted
  for that period.
  - Why: this is the only test with no look-ahead and no LLM contamination.
- If live results fall well outside the backtest's range in either direction, investigate before
  trusting anything. A big divergence means the backtest was wrong somewhere.

Standing kill rule (both gates): paper equity down >25% from peak halts trading and opens an
issue (see Phase 4 §9).

### If a gate fails
No tuning against the holdout. Record the result in a new ADR, form a new hypothesis, and wait for
fresh data before re-testing. A failed gate is a valid result, not a bug to fix.

## Consequences
- **Passing Gate A** means the strategy is allowed to trade in paper. It does not mean it works.
- **Passing Gate B** is the first point where claims of "it works" are allowed, in portfolio
  write-ups or anywhere else.
- Real money is out of scope regardless. Revisiting that requires a new ADR, at minimum after
  Gate B.
- Nightly data ingestion keeps running whatever the outcome, so a fresh holdout accumulates for
  future hypotheses.
