# Phase 4 — AI-Assisted Systematic Strategy (LLM Feature Extraction → Ranking → Backtest → Automated Paper Trading)

## Context
Phases 1–3 built a research tool for a human: Alpaca paper trading with a thesis journal, SPY/QQQ
benchmarking, and a source-agnostic `Signal` → `Evaluator` pipeline that scores content as
"worth reading." Phase 4 adds a **systematic strategy** alongside it:

```
EDGAR filings ─► section extraction ─► LLM feature extractor ─┐
SEC XBRL fundamentals ─► point-in-time factors ────────────────┼─► ranking model ─► backtester
Alpaca daily prices ───────────────────────────────────────────┘                      │
                                              (only if go-live gate passes) ◄─────────┘
                                                        │
                                   GitHub Actions ─► Alpaca paper rebalance ─► reports
```

The LLM is a **reader, not a trader**. It turns filing text into fixed numeric features. It never
makes buy/sell decisions. Every feature must be testable against later returns.

**Same principle as Phases 2–3: plan first, show the plan, then build.** Phase 4 is mostly
additive. New code goes in `strategy/`, `research/features/`, `research/backtest/` and
`.github/workflows/`. The existing human-facing pipeline (`research/pipeline.py`, `ClaudeEvaluator`,
dashboard) keeps working unchanged. The only planned change inside `thesis_engine/` is adding
rebalancing to `AlpacaClient` (section 8). Don't refactor the existing buy/journal flow.

Record every non-obvious decision as an ADR in `docs/adr/` (per `docs/agents/domain.md`).

---

## Step 0 — Before writing code

### 0a. Move the repo out of iCloud (user does this)
The repo currently lives in iCloud Drive. iCloud sync corrupts `.git` (duplicate "2" files,
half-synced objects). Move it to a non-synced path such as `~/code/thesis-engine`. GitHub is the
backup.

### 0b. Pre-register go-live criteria (`docs/adr/0001-go-live-criteria.md`)
Write this **before any backtest runs** and commit it. If the criteria are written after the
results are seen, they're worthless. Starting proposal (adjust in the ADR, then freeze):

- **Holdout:** the most recent 18 months of data are locked. Nothing is fit, tuned or even
  looked at on that window until the single final evaluation. Develop on everything before it.
- **Pass requires, on the holdout, net of costs:**
  - excess return vs SPY > 0 **and** information ratio ≥ 0.3
  - max drawdown no worse than SPY's over the same window + 10 percentage points
  - average monthly turnover ≤ 60%
  - the result survives perturbation: ±20% on each key parameter (top-N size, rebalance
    lag, cost assumption) must not flip the sign of excess return
- **LLM features specifically** must add value over the non-LLM baseline (section 5d). If the
  composite with LLM features doesn't beat the composite without them, the LLM features are
  dropped. That's a valid result.
- **If the gate fails:** don't tune until it passes (that's overfitting to the holdout). Write
  up the result, form a new hypothesis in a new ADR, and get a fresh holdout (wait for new data
  to accrue).

### 0c. Fix existing bugs first (not new scope)
1. **`research/adapters/edgar.py::_extract_mda` grabs the table of contents.** The first regex
   match for "Management's Discussion" in most 10-Ks is the TOC entry, so the excerpt (and the
   LLM's input) is mostly the TOC. Fix by skipping matches followed by a page number/short
   line, or by taking the occurrence with the most following prose before the next `Item N`
   header. Add a test using 2–3 real saved filings.
2. **`thesis_engine/config.py` crashes without Alpaca keys** (`os.environ[...]`). Research and
   backtest runs shouldn't need broker credentials. Use `os.getenv` and fail only when the
   Alpaca client is actually constructed.

---

## 1. Universe (point-in-time)

- Start with **S&P 500 historical membership**, not today's members. Using today's list is
  survivorship bias: it silently drops every company that went bankrupt or got removed, which
  inflates backtests.
- Free sources are imperfect (e.g., reconstructing from the Wikipedia constituent-changes table).
  Pick one, document its known gaps in an ADR, and store as `universe_membership(ticker, cik,
  start_date, end_date)`.
- Map tickers to CIKs and handle ticker changes. Key everything internally by **CIK**, not
  ticker.
- Delisted names: confirm whether the price source (section 2) has bars for them. If not,
  record which names are missing. The backtest must treat a missing delisted name as a
  realistic loss (e.g., last price → −100% for bankruptcies, or last price for acquisitions),
  not silently drop it.

## 2. Prices

- Daily bars from **Alpaca's historical data API**, split/dividend-adjusted. Coverage begins
  around 2016; verify actual coverage for the universe, including delisted names, and record
  it in an ADR.
- Table `prices_daily(cik, ticker, date, open, high, low, close, adj_close, volume)`,
  unique on `(cik, date)`.
- Yahoo (`market_data/yahoo.py`) stays for the dashboard. **Don't use yfinance fundamentals
  for backtesting.** It returns current values only, so any historical use is look-ahead.

## 3. EDGAR historical backfill + section extraction

- Backfill 10-K and 10-Q filings for every universe member, 2015 → present, via the
  submissions API and `Archives/`. Respect SEC limits: ≤10 req/s, descriptive
  `EDGAR_USER_AGENT` with a real contact email. Make the backfill resumable (it will take
  hours).
- Extract sections into `filing_sections(accession, cik, form, section, text, char_len,
  extractor_version)`:
  - 10-K: Item 1A (Risk Factors), Item 7 (MD&A)
  - 10-Q: Part II Item 1A (if present), Part I Item 2 (MD&A)
- **Point-in-time timestamp = the filing's `acceptanceDateTime`**, not the period end date.
  A feature becomes usable on the **next trading day's open** after acceptance.
- Storage rule carve-out: the Phase 2 rule "don't permanently store raw content" was about
  third-party content (Reddit, news). SEC filings are public-domain government records, so
  storing section text is fine and necessary for reproducibility. Store it compressed. Note
  this carve-out in an ADR so it isn't mistaken for a policy violation later.
- Log and count extraction failures per form/year. If >10% of filings fail extraction, fix the
  extractor before moving on.

## 4. Fundamentals from SEC XBRL (point-in-time)

- Use `data.sec.gov/api/xbrl/companyfacts/CIK##########.json`. Each fact carries a `filed`
  date. Only use a value on dates after it was filed. Restated values replace old ones only
  from their own `filed` date forward.
- Table `fundamentals_pit(cik, concept, period_end, value, filed, form)`.
- Derived factors (computed as of each rebalance date, using only facts filed before it):
  - **value:** earnings yield (TTM net income / market cap), sales yield (TTM revenue / market cap)
  - **quality:** gross profitability (gross profit / total assets)
  - **growth:** TTM revenue growth YoY
  - **momentum:** 12-month return skipping the most recent month (from prices, not XBRL)
- Concept names vary across companies (e.g., `Revenues` vs
  `RevenueFromContractWithCustomerExcludingAssessedTax`). Keep the mapping in one config
  table and log coverage per concept.

## 5. LLM feature extractor (`research/features/`)

This is the core AI component. It's a new module, separate from `ClaudeEvaluator`: different
question, different output.

### 5a. Fixed, versioned schema (v1)
One row per `(accession, section)` in `llm_features`:

| feature | type | meaning |
|---|---|---|
| `tone` | int −2..+2 | management tone in this section |
| `uncertainty` | float 0..1 | density of hedged/uncertain language |
| `guidance_direction` | int −1/0/+1, nullable | raised / maintained / lowered outlook; null if none stated |
| `new_risk_count` | int | risks present that weren't in the prior same-form filing (risk factors only) |
| `removed_risk_count` | int | risks dropped vs prior filing |
| `risk_severity_change` | int −2..+2 | net change in seriousness of risk disclosures |
| `liquidity_concern` | bool | going-concern, covenant or funding stress language |
| `extraction_confidence` | float 0..1 | model's self-rated confidence (diagnostic only, not a signal) |

Plus provenance on every row: `schema_version`, `prompt_hash`, `model_id`, `extracted_at`.
Changing the prompt or schema = new version. Never overwrite old versions.

Risk-change features need the prior filing's section in the same call (prior + current, asked
to diff).

### 5b. Contamination controls
LLMs have read the future relative to most of the backtest.
- **Mask identity** before sending: strip company name, ticker, product names where feasible,
  exact dates, and fiscal years. The model should see "the Company" and relative time only.
- **Record the model's training cutoff** in config. Report backtest results **separately for
  pre-cutoff and post-cutoff periods**. Pre-cutoff results are labeled "contamination risk." The
  go-live decision weights post-cutoff results.
- `temperature=0`, strict JSON, schema validation on every response. Invalid → retry once →
  log and leave null. Never fill in guessed values.

### 5c. Cost controls
- Model is configurable (`FEATURE_MODEL`). Default to a Haiku-class model, not Sonnet.
- Use the Anthropic **Message Batches API** for backfill (cheaper, async).
- Cache key: `(accession, section, schema_version, model_id)`. A filing is never re-extracted
  unless the version changes.
- `FEATURE_BUDGET_USD` env var: estimate cost from token counts before submitting a batch and
  refuse to run if over budget.
- **Dry run first:** 50 filings, print cost/filing and a sample of outputs for manual review,
  then stop. Scale up only after a human reviews the sample.

### 5d. Non-LLM text baseline (required)
Implement a cheap baseline: **year-over-year textual similarity** of the same section (TF-IDF
cosine between this filing and the prior same-form filing). Low similarity (big changes) has
been documented in academic research to predict weaker future returns. The LLM features have to
beat this baseline to justify their cost. If they don't, that's the finding.

## 6. Ranking model (`strategy/`)

Build in this order. Each step must beat the previous one on the development window, or it
doesn't advance.

1. **Factor composite:** cross-sectional z-score each factor (section 4) at each rebalance
   date, winsorize at ±3, equal-weight average.
2. **+ text baseline** (5d) added to the composite.
3. **+ LLM features** (5a) added to the composite.
4. **ML combiner (optional):** gradient-boosted model (LightGBM) predicting next-month
   cross-sectional return rank. **Walk-forward only**: train on an expanding window, predict the
   next month, roll forward. No random train/test splits, ever. Expect this to overfit. It's
   only kept if it beats step 3 out of sample.

Features from filings are **as-of joined**: on each rebalance date, use the most recent filing
whose next-trading-day-after-acceptance is ≤ that date.

## 7. Backtester (`research/backtest/`)

- Monthly rebalance on the first trading day. Long-only, equal-weight top N (start N=30). No
  shorting, no leverage.
- Costs: 10 bps per side + 5 bps slippage, configurable. Fills at next open after the signal
  date, never the same close that generated the signal.
- Delisting handling per section 1.
- Benchmark: SPY total return.
- Outputs per run (saved to `reports/backtests/<run_id>/`): config, equity curve vs SPY, CAGR,
  excess return, information ratio, max drawdown, monthly turnover, per-year table, pre/post LLM
  cutoff split, and the git commit hash.
- **Look-ahead tests (required, in CI):** synthetic test where a feature is timestamped one day
  in the future must raise or be excluded. A test that shuffles feature dates must destroy
  performance. If shuffled features still "work," there's a leak.
- The holdout window is enforced in code: the backtester refuses to run on it unless called
  with an explicit `--final-holdout` flag, which logs the run permanently.

## 8. Execution: rebalancing in Alpaca

Extend `AlpacaClient` (additive):
- `rebalance_to_targets(weights: dict[str, float], dry_run: bool)`: compute deltas against
  current positions, sell first, then buy. Use notional/fractional orders where Alpaca supports
  them.
- New table `strategy_orders(run_id, symbol, side, notional, status, submitted_at, filled_at,
  filled_avg_price)`. Strategy positions are tagged so they don't mix with thesis-journal
  positions. If mixing can't be avoided cleanly, use a **separate Alpaca paper account** for the
  strategy (preferred) and document this in an ADR.
- Paper only. `paper=True` stays hardcoded. A real-money switch is out of scope for this phase.

## 9. Automation (GitHub Actions)

### Workflows
- **`nightly.yml`** (weekdays, after US market close): ingest new filings → extract sections →
  extract LLM features (incremental, cached) → update prices/fundamentals → run health checks.
- **`rebalance.yml`** (first trading day of month, after open): compute targets → health checks
  → rebalance (only if `TRADING_ENABLED=true` repo variable) → write report.
- **`ci.yml`** (on push): tests, including the look-ahead tests.

### Secrets & state
- Secrets in GitHub encrypted secrets: `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`,
  `ANTHROPIC_API_KEY`, `EDGAR_USER_AGENT`, `FRED_API_KEY`.
- Runners are ephemeral, so the DB doesn't persist between runs by default. Decide the state
  store in an ADR. Options: commit the SQLite DB/parquet files to a dedicated `state` branch
  (fine if it stays well under GitHub's size limits; keep filing text compressed or rebuildable),
  or a free hosted Postgres tier. **Don't rely on Actions cache** as the source of truth: it's
  evictable.

### Health checks and kill switch
Abort the rebalance (no orders) and **open a GitHub Issue labeled `needs-triage`** if any of:
- prices or filings data stale by more than 3 trading days
- >10% of universe missing features on the rebalance date
- any single target weight >10%
- planned turnover >80% in one rebalance
- strategy paper equity down >25% from peak (also sets `TRADING_ENABLED=false`)
- any workflow step errored

Issues are the notification channel. They fit the existing triage workflow
(`docs/agents/issue-tracker.md`).

## 10. Reporting

- After every rebalance, and weekly, commit `reports/live/YYYY-MM-DD.md`: equity vs SPY since
  inception, current holdings and weights, orders placed, the top-ranked names with their main
  feature values, and health-check status.
- Add a **Strategy** page to the Streamlit dashboard reading from these reports plus
  `strategy_orders`. Keep it separate from the thesis-journal views.
- Live paper results are compared against what the backtest predicted for the same period.
  Large divergence = something in the backtest was wrong.

---

## Explicitly out of scope this phase
- Reddit/RSS/X signals as trading inputs (they stay in the human research pipeline)
- Shorting, leverage, options, intraday trading
- Real money
- Reinforcement learning
- An LLM making trade decisions directly

## Milestones (each one gated on the previous)
1. **M0:** repo moved, ADR 0001 committed, bugs in 0c fixed.
2. **M1, data:** universe, prices, EDGAR sections, XBRL fundamentals backfilled, with coverage
   reports.
3. **M2, baselines:** factor composite + text-similarity baseline backtested on the dev window.
4. **M3, LLM features:** dry run reviewed by a human → full extraction → backtested vs M2.
5. **M4, final evaluation:** one run on the holdout with `--final-holdout`. Gate decision
   recorded in an ADR.
6. **M5, automation:** workflows live. `TRADING_ENABLED=true` only if M4 passed. The nightly
   ingestion runs regardless, so data keeps accruing for a future holdout.

## Definition of done
- `nightly.yml` and `rebalance.yml` run unattended for 2 consecutive weeks with no manual steps.
- Every backtest report is reproducible from its stored config + commit hash.
- Look-ahead tests pass in CI.
- ADR 0001 exists, predates the first backtest commit, and the M4 gate decision references it.
- The Phase 1–3 pipeline and dashboard still work unchanged.
