# Phase 3 — Market Data, Real Macro Indicators, Reddit

## Context
Phase 2 built the research signal engine: EDGAR (active) and RSS (active) adapters feed a
source-agnostic `Signal` → `Evaluator` → dashboard pipeline. Reddit was left as a disabled
stub on purpose. The `research/macro/` module analyzes news *headlines* for qualitative
industry impact — it does not pull any actual economic indicators (CPI, rates, unemployment).
This phase closes those gaps and adds price/fundamentals data, which didn't exist before.

**Same principle as Phase 2: plan first, show the plan, then build. Don't touch the trading
(`thesis_engine/`) module — this phase is additive, in `research/` and a new `market_data/`.**

---

## Fix first (existing bug, not new scope)

`RSS_FEEDS` in `thesis_engine/config.py` and `MACRO_FEEDS` in `research/macro/fetcher.py`
include dead endpoints:
- `feeds.reuters.com/*` — Reuters shut down public RSS around 2020; these 404/redirect now.
- `cnbc.com/id/.../device/rss/rss.html` — old-style CNBC RSS, unreliable/likely retired.
- `rsshub.app/apnews/...` — a public shared RssHub instance, not an AP-operated feed; rate-limited
  and goes down often. Don't depend on it for anything that needs to run reliably.

Before building anything new: verify each existing feed URL actually returns entries (`curl` or
`feedparser.parse` and check `.entries`), drop or replace dead ones. Good stable replacements to
check: MarketWatch top stories, Dow Jones public RSS, WSJ markets, Investing.com, Seeking Alpha
market news, and outlet-specific feeds discoverable from each site's own `/rss` page rather than
third-party generators. Log a warning (not a crash) for any feed that returns zero entries so
future breakage is visible instead of silent.

---

## Source/data roadmap (build order)

1. **Yahoo Finance market data (build now)** — prices, fundamentals for watchlist + open positions.
2. **FRED macro indicators (build now)** — real economic time series, separate from the existing
   macro *news* analyzer.
3. **Reddit adapter (build now)** — the Phase 2 stub, actually implemented.
4. **X/Twitter adapter — still deferred.** Do not build. See reasoning below.
5. **TradingView — not a data source, drop from the roadmap entirely.** TradingView has no public
   API for prices/fundamentals/indicators at any price tier; its only APIs are a charting-widget
   library and a broker-integration API. Nothing to integrate here.
6. **LSEG Workspace / S&P Capital IQ — explicitly out of scope.** Both are institutional products
   (LSEG: roughly $1,000–2,500 per user/month or $75k+/year contracts; Capital IQ: five to six
   figures/year, sales-quote only, no self-serve). Not proportionate to this project. Recorded
   here so it isn't re-proposed without a reason the calculus changed (e.g., this becomes a funded
   business).

---

## 1. Yahoo Finance market data

New module, separate from the `research/` signal pipeline — this is numeric price/fundamentals
data, not "evidence to evaluate," so it doesn't belong in the `Signal`/`Evaluator` flow.

**Structure:**
- `market_data/yahoo.py` — thin wrapper around `yfinance`.
- New table `market_snapshots`: `id, ticker, date, open, high, low, close, volume, market_cap,
  pe_ratio, fetched_at`. One row per ticker per day.
- `market_data/watchlist.py` — reuse `EDGAR_WATCHLIST` plus open position symbols (from
  `thesis_engine.database`) as the ticker universe; don't hardcode a second list.
- A `refresh_market_data()` function called from the daily pipeline (`scripts/daily_snapshot.py`
  or a new scheduled entry point) — pulls latest OHLCV + key fundamentals for every ticker in the
  universe, upserts into `market_snapshots`.
- Surface it on the dashboard: a simple price/fundamentals table or sparkline next to each
  position and watchlist ticker, and (optional, later) feed recent price moves into the evaluator
  prompt as context (e.g., "stock is up 22% in 5 days" changes how a bullish post should be
  scored) — don't build that context-injection yet, just leave the data available for it.

**Constraints:**
- `yfinance` is an unofficial, reverse-engineered client — no API key, no SLA, breaks when Yahoo
  changes its site. Wrap every call in try/except, log failures, never let a bad ticker fetch
  crash the pipeline.
- Personal/research use only per Yahoo's terms — this project already stores no third-party
  content for redistribution, so it's consistent with existing data-handling rules; just don't
  build anything that republishes Yahoo data externally.
- Alpaca already provides live trade prices for *open positions*
  (`AlpacaClient.get_latest_prices`) — don't duplicate that. Yahoo's job here is fundamentals and
  broader watchlist coverage Alpaca's free tier doesn't give you (P/E, market cap, sector,
  historical daily bars for tickers you don't hold).

---

## 2. Real macro indicators (FRED)

The existing `research/macro/` module is a *news* pipeline (RSS headlines → Claude industry-impact
analysis). Keep it as-is. Add actual indicator data alongside it, not instead of it.

**Structure:**
- `research/macro/fred.py` — calls the FRED API (`fred.stlouisfed.org`), free, requires a free API
  key (`FRED_API_KEY` in `.env`). No cost, no contract, ~30-second signup.
- Track a small fixed set of series to start, not "as much as possible": CPI (`CPIAUCSL`), Fed
  funds rate (`FEDFUNDS`), unemployment (`UNRATE`), 10-year Treasury yield (`DGS10`), and one or
  two more only if there's a concrete reason. Config list, not hardcoded in the fetch function.
- New table `macro_indicators`: `id, series_id, series_name, date, value, fetched_at`. One row per
  series per observation date; upsert on `(series_id, date)`.
- Rate limit: with an API key, FRED allows 120 req/min — trivially fine for this use, no delay
  logic needed beyond basic error handling.
- Dashboard: a small macro panel — current value + short trend line per tracked series. This is
  numeric ground truth, no LLM involved; keep it separate from the qualitative macro-news panel
  so the two aren't confused.

---

## 3. Reddit adapter (fill in the Phase 2 stub)

Everything about *why* and *how carefully* was already decided in Phase 2 — this just implements it.

- Use PRAW, read-only mode, free non-commercial personal-use tier (100 req/min). Client ID/secret
  in `.env` as `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET` / `REDDIT_USER_AGENT` (descriptive UA,
  same pattern as `EDGAR_USER_AGENT`).
- Target a small fixed subreddit list (config, e.g. `r/stocks`, `r/investing`,
  `r/SecurityAnalysis` — skip `r/wallstreetbets` initially, it's overwhelmingly noise relative to
  the quality bar this evaluator enforces; add it later only if worth-reading rate from the other
  subs turns out too low).
- Pull recent posts (not every comment) mentioning watchlist tickers; map to `Signal(source="reddit", ...)`
  exactly like EDGAR/RSS already do — this is the whole point of the adapter interface being
  built source-agnostic in Phase 2.
- Re-confirm before shipping: per the Phase 2 data-handling rules, don't permanently store post
  bodies (only the short excerpt already truncated after evaluation, same as other sources), don't
  profile authors, and this stays personal/non-commercial — Reddit's $12k/month commercial tier is
  irrelevant here as long as this is a personal tool and not something redistributing Reddit
  content to other users.
- Register in `pipeline.ADAPTER_REGISTRY` — per Phase 2 design this should be close to a one-line
  change. If it isn't, something in the adapter interface leaked source-specific logic into the
  pipeline/evaluator and that's worth fixing before moving on.

---

## 4. X/Twitter — still not building this phase

Two changes since Phase 2 made this worth re-stating rather than silently deferring again:
- The free tier is gone. New developer access is pay-per-use (~$0.005/read, ~$0.015/post),
  no free allocation. Low-volume personal use is now cheap rather than free, not blocked outright.
- Before building, actually read X's current developer agreement for restrictions on using API
  data to power automated trading/investment decisions — this has been a contractual gray area on
  various platforms and needs checking against the current terms, not assumed from prior versions.

Given the direct cost and unresolved ToS question, this stays deferred. Leave a stub adapter (same
pattern as the Reddit stub in Phase 2) so the interface is ready, but do not implement fetching.

---

## Definition of done
- Existing RSS feeds in both `research/adapters/rss.py` and `research/macro/fetcher.py` verified
  live or replaced; dead ones removed.
- Running the daily pipeline also refreshes `market_snapshots` (Yahoo) and `macro_indicators`
  (FRED) with no manual steps.
- Dashboard shows: price/fundamentals per watchlist ticker, a numeric macro-indicator panel
  (separate from the existing macro-news panel), and Reddit signals flowing through the same
  worth-reading list as EDGAR/RSS.
- `ADAPTER_REGISTRY` gains Reddit with no changes required to `Signal`, `Evaluator`, schema, or
  dashboard code outside of what's listed above.
- X adapter remains an unimplemented stub. TradingView, LSEG, and Capital IQ are not referenced
  anywhere in code — only in this doc, as declined.
