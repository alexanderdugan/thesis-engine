from __future__ import annotations
import json
import logging
import re
import time
from datetime import datetime, timezone, timedelta

import requests
from bs4 import BeautifulSoup

from thesis_engine.config import EDGAR_USER_AGENT, EDGAR_WATCHLIST, EDGAR_FILING_TYPES
from research.adapters.base import Signal, SourceAdapter

logger = logging.getLogger(__name__)

_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
_FILING_INDEX_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession_nodash}/{primary_doc}"
_REQUEST_DELAY = 0.2  # well under SEC's 10 req/sec limit


def _session() -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = EDGAR_USER_AGENT
    s.headers["Accept-Encoding"] = "gzip, deflate"
    return s


def _get(session: requests.Session, url: str) -> requests.Response:
    time.sleep(_REQUEST_DELAY)
    resp = session.get(url, timeout=15)
    resp.raise_for_status()
    return resp


def _build_ticker_cik_map(session: requests.Session) -> dict[str, int]:
    data = _get(session, _TICKERS_URL).json()
    return {v["ticker"].upper(): v["cik_str"] for v in data.values()}


def _extract_mda(html: str) -> str:
    """Extract a ~3000-char excerpt starting from the MD&A section."""
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator=" ", strip=True)
    # Find MD&A section header
    pattern = re.compile(r"management.{0,10}s discussion", re.IGNORECASE)
    match = pattern.search(text)
    if match:
        excerpt = text[match.start(): match.start() + 3000]
    else:
        # Fall back to first 3000 chars of the document body
        excerpt = text[:3000]
    return " ".join(excerpt.split())  # normalise whitespace


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class EdgarAdapter(SourceAdapter):
    def fetch(self) -> list[Signal]:
        if not EDGAR_WATCHLIST:
            logger.warning("EDGAR_WATCHLIST is empty — set EDGAR_WATCHLIST in .env")
            return []
        if not EDGAR_USER_AGENT or EDGAR_USER_AGENT == "thesis-engine research":
            logger.warning("EDGAR_USER_AGENT not configured — SEC may block requests")

        session = _session()
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        signals: list[Signal] = []

        try:
            ticker_cik = _build_ticker_cik_map(session)
        except Exception as e:
            logger.error(f"Failed to fetch SEC ticker→CIK map: {e}")
            return []

        for ticker in EDGAR_WATCHLIST:
            cik = ticker_cik.get(ticker)
            if not cik:
                logger.warning(f"No CIK found for {ticker}")
                continue
            try:
                signals.extend(_fetch_ticker_filings(session, ticker, cik, cutoff))
            except Exception as e:
                logger.error(f"Error fetching EDGAR filings for {ticker}: {e}")

        return signals


def _fetch_ticker_filings(
    session: requests.Session, ticker: str, cik: int, cutoff: datetime
) -> list[Signal]:
    url = _SUBMISSIONS_URL.format(cik=cik)
    data = _get(session, url).json()
    recent = data.get("filings", {}).get("recent", {})

    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    accessions = recent.get("accessionNumber", [])
    primary_docs = recent.get("primaryDocument", [])

    signals: list[Signal] = []
    fetched_at = _now()

    for form, date_str, accession, primary_doc in zip(forms, dates, accessions, primary_docs):
        if form not in EDGAR_FILING_TYPES:
            continue
        try:
            filing_date = datetime.fromisoformat(date_str).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if filing_date < cutoff:
            break  # filings are in reverse-chron order

        accession_nodash = accession.replace("-", "")
        filing_url = _FILING_INDEX_URL.format(
            cik=cik, accession_nodash=accession_nodash, primary_doc=primary_doc
        )

        raw_content = None
        try:
            html = _get(session, filing_url).text
            raw_content = _extract_mda(html)
        except Exception as e:
            logger.warning(f"Could not fetch/parse filing {accession}: {e}")

        company_name = data.get("name", ticker)
        signals.append(Signal(
            source="edgar",
            raw_id=accession,
            ticker=ticker,
            title=f"{company_name} {form} — {date_str}",
            summary=f"{form} filing for {ticker} filed {date_str}",
            url=filing_url,
            timestamp=filing_date.isoformat(),
            raw_content=raw_content,
            metadata={"filing_type": form, "cik": cik, "company": company_name},
            fetched_at=fetched_at,
        ))

    return signals
