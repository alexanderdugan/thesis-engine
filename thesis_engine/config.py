import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Optional at import time: research and backtest runs don't need broker credentials.
# AlpacaClient checks for them when it is constructed.
ALPACA_API_KEY = os.getenv("ALPACA_API_KEY", "")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "")
ALPACA_BASE_URL = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "thesis_engine.db"

CONVICTION_LABELS = {
    1: "Speculative",
    2: "Weak edge",
    3: "Moderate",
    4: "High conviction",
    5: "Highest-confidence",
}

# Research signal engine
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
USE_MOCK_EVALUATOR = os.getenv("USE_MOCK_EVALUATOR", "true").lower() == "true"
EDGAR_USER_AGENT = os.getenv("EDGAR_USER_AGENT", "thesis-engine research")
EDGAR_WATCHLIST = [t.strip().upper() for t in os.getenv("EDGAR_WATCHLIST", "").split(",") if t.strip()]
EDGAR_FILING_TYPES = [t.strip().upper() for t in os.getenv("EDGAR_FILING_TYPES", "10-K,10-Q,8-K").split(",") if t.strip()]

RSS_FEEDS = [
    "https://feeds.marketwatch.com/marketwatch/topstories/",
    "https://feeds.content.dowjones.io/public/rss/RSSMarketsMain",
    "https://feeds.bbci.co.uk/news/business/rss.xml",
    "https://www.cnbc.com/id/20910258/device/rss/rss.html",
    "https://feeds.npr.org/1006/rss.xml",
    "https://www.theguardian.com/uk/business/rss",
    "https://www.ft.com/markets?format=rss",
]

FRED_API_KEY = os.getenv("FRED_API_KEY", "")
FRED_SERIES = [
    ("CPIAUCSL", "CPI (All Urban Consumers)"),
    ("FEDFUNDS", "Federal Funds Rate"),
    ("UNRATE",   "Unemployment Rate"),
    ("DGS10",    "10-Year Treasury Yield"),
    ("T10YIE",   "10-Year Breakeven Inflation"),
]

REDDIT_CLIENT_ID     = os.getenv("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET", "")
REDDIT_USER_AGENT    = os.getenv("REDDIT_USER_AGENT", "thesis-engine research")
REDDIT_SUBREDDITS    = [s.strip() for s in os.getenv("REDDIT_SUBREDDITS", "stocks,investing,SecurityAnalysis").split(",") if s.strip()]
