# Phase 2 — Research Signal Engine

## Goal
Add a research layer to the existing thesis-driven paper trading platform. It pulls content from external sources, evaluates each item for **argument/evidence quality** against my tech-growth investing thesis, and surfaces the worth-reading ones on the dashboard.

**Critical design principle: build the architecture WIDE, activate it NARROW.**
Design every interface to be source-agnostic so adding new data sources later is trivial. In this phase, IMPLEMENT and ACTIVATE only the open, no-gatekeeping sources (SEC EDGAR first, RSS second). DESIGN the interface so that Reddit and X slot in later as additional adapters, but do NOT build those yet. Do not build fact-checking yet (but leave a clean seam for it, described below).

Plan the architecture and show it to me BEFORE writing code.

---

## Source roadmap (build order)
- **Adapter #1 — SEC EDGAR (ACTIVE, build now).** Open API, no key. Highest-quality fit: primary-source filings, not secondhand takes. This is the priority adapter.
- **Adapter #2 — Financial news RSS (ACTIVE, build now).** Open RSS feeds, no auth. Good for catalysts and what's being discussed.
- **Adapter #3 — Reddit (DESIGN ONLY, do not build).** Will use PRAW with client ID/secret once credentials are sorted. Leave a stub class implementing the adapter interface, clearly marked TODO/disabled.
- **Adapter #4 — X/Twitter (DESIGN ONLY, do not build).** Documented as a future adapter; API access is restrictive/paid, so it is explicitly deferred.

The whole point of the abstract adapter interface is that #3 and #4 require only writing a new adapter class later — no changes to the evaluator, schema, pipeline, or dashboard.

---

## Architecture

### 1. Signal schema (source-agnostic)
Every data source produces `Signal` records in this uniform shape, stored in the DB:

- `id` (primary key)
- `source` (string, e.g. "edgar", "rss", "reddit", "x") — which adapter produced it
- `raw_id` (string) — original ID from the source (e.g. EDGAR accession number, RSS guid), for dedup
- `ticker` (string, nullable) — associated company if identifiable
- `title` (string)
- `summary` (string, nullable)
- `url` (string) — link back to the original (filing URL, article URL)
- `timestamp` (datetime) — when the source item was published/filed
- `raw_content` (text, **transient**) — content passed to the evaluator. NOT a permanent archive. After evaluation, clear/null it or keep only a short excerpt for display; the `url` is the durable record. (Especially important for any future social sources — never permanently store other users' post bodies.)
- `metadata` (JSON) — source-specific extras (e.g. filing type for EDGAR, feed name for RSS). Do NOT store personal identifiers about content authors.
- `fetched_at` (datetime)

Unique constraint on (`source`, `raw_id`) to prevent duplicates.

### 2. Source adapter interface
An abstract base class `SourceAdapter` with a method like `fetch() -> list[Signal]`.
Every source implements this. Build TWO concrete adapters now (EDGAR, RSS); leave Reddit as a disabled stub.

**`EdgarAdapter` (active):**
- Uses the SEC EDGAR APIs (data.sec.gov / EDGAR full-text search). No API key required.
- SEC requires a descriptive `User-Agent` header identifying the requester (e.g. "thesis-engine research <your-email>"). Put it in config/.env; requests without it get blocked.
- Respect SEC's fair-access rate limit (max ~10 requests/sec; stay well under). Add a small delay between requests.
- Start by pulling recent filings (10-K, 10-Q, 8-K) for a configurable watchlist of tickers, OR recent filings of a given type. For long documents, extract the most relevant sections (e.g. MD&A, business description) rather than dumping the entire filing into the evaluator.
- Map each filing to a `Signal` (ticker, filing type in metadata, filing URL, filing date).

**`RssAdapter` (active):**
- Uses `feedparser`. Configurable list of financial-news RSS feed URLs.
- No auth. Respect basic politeness (don't poll more than a few times a day).
- Extract ticker from title/summary where possible (nullable otherwise).
- Map each entry to a `Signal`.

**`RedditAdapter` (STUB ONLY — do not implement fetching):**
- Create the class implementing `SourceAdapter` but have `fetch()` raise NotImplementedError or return [] with a clear "disabled — pending credentials" log line. This proves the interface is ready for it.

### 3. Evaluator (source-agnostic)
A single `evaluate(signal) -> Evaluation` function that does NOT know or care what source the signal came from. It sends the signal's content to the Anthropic API (model `claude-sonnet-4-6`, `max_tokens` 1000) with a prompt scoring it against the criteria below.

`Evaluation` schema (stored in DB, linked to signal_id):
- `id`, `signal_id` (FK)
- `quality_score` (int, 0-100)
- `has_falsifiable_thesis` (bool)
- `cites_evidence` (bool)
- `acknowledges_risk` (bool)
- `is_business_focused` (bool)
- `central_claim` (string) — the single main factual claim, extracted in plain language. THIS IS THE SEAM for future fact-checking; we only EXTRACT it now, we do NOT verify it.
- `one_line_summary` (string)
- `verdict` (enum: "worth_reading" | "skip")
- `evaluated_at` (datetime)

**Evaluation criteria (put this in the prompt). Note the content may be a SEC filing excerpt, a news article, or (later) a forum post — the criteria apply to whatever the text argues:**

Signals of QUALITY content (raise score):
- Makes a falsifiable claim — a specific thesis with a timeline, not "this will moon"
- Cites real evidence: filings, revenue, product data, contracts, guidance — not vibes
- Acknowledges the bear case / risks (real analysis argues against itself)
- Reasoning is about the BUSINESS and its technology/fundamentals, not stock price or chart patterns
- Relevant to genuine technological growth / disruption (aligns with my thesis)

Red flags (lower score):
- Hype language, emojis, rockets, "can't lose"
- Cites position size as the argument ("YOLO'd my savings")
- Pure technical analysis / chart-reading with no business thesis
- Urgency ("buy before Monday") — real theses don't expire in 48h
- No risks mentioned at all

The prompt must return STRICT JSON only (no markdown, no preamble) matching the Evaluation fields, so it can be parsed directly. Handle parse failures gracefully (log and skip, don't crash the run).

### 4. Pipeline
A single runnable command that: fetches via all *activated* adapters (EDGAR + RSS now) -> dedups against existing signals -> evaluates new signals -> stores both signal and evaluation. Idempotent: re-running shouldn't duplicate or re-evaluate existing signals. The pipeline should iterate over a registry of *enabled* adapters so enabling Reddit later is a one-line change.

### 5. Dashboard
Add a "Research" view to the existing Streamlit dashboard:
- List signals with verdict = "worth_reading", sorted by quality_score desc
- Show: ticker, source, one_line_summary, quality_score, the boolean flags, and a link to the original (filing/article URL)
- Let me filter by ticker and by source

---

## Data handling & API compliance
- **SEC EDGAR:** always send a descriptive User-Agent identifying me; respect the ~10 req/sec fair-access limit with a safety margin. EDGAR data is public domain — fine to use and store, but still don't hammer it.
- **RSS:** poll politely (a few times/day max). Store the evaluation + link; keep only short excerpts of article text, not full reproductions.
- **General:** store evaluations and links, not permanent archives of full third-party content. Evaluate the CONTENT's argument, never profile the author. Never accumulate content into a dataset for training/fine-tuning any model.
- **Future social sources (Reddit/X):** when built, must follow the same rules plus their platform API terms (personal/non-commercial read use, descriptive user agent, rate limits, no permanent storage of others' post bodies, no author profiling).

---

## Constraints
- Single repo, modular folders. Reuse the existing DB and `.env` setup from Phase 1.
- `.env` stays gitignored. Never hardcode credentials or emails.
- Build ONLY the EDGAR and RSS adapters now. Reddit = disabled stub. X = documented, not built. No other sources.
- Do NOT build fact-checking — only extract `central_claim` as the future seam.
- Anthropic API calls use model `claude-sonnet-4-6`, `max_tokens: 1000`.
- Plan first, show me the plan, then build.

## Definition of done
Every morning I can run one command and then open the dashboard to see a ranked list of worth-reading items — recent SEC filings and news — each with an extracted central claim and quality score, instead of digging through filings and headlines myself. Adding Reddit later requires only filling in the stub adapter.
