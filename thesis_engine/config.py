import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

ALPACA_API_KEY = os.environ["ALPACA_API_KEY"]
ALPACA_SECRET_KEY = os.environ["ALPACA_SECRET_KEY"]
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
EDGAR_USER_AGENT = os.getenv("EDGAR_USER_AGENT", "thesis-engine research")
EDGAR_WATCHLIST = [t.strip().upper() for t in os.getenv("EDGAR_WATCHLIST", "").split(",") if t.strip()]
EDGAR_FILING_TYPES = [t.strip().upper() for t in os.getenv("EDGAR_FILING_TYPES", "10-K,10-Q,8-K").split(",") if t.strip()]

RSS_FEEDS = [
    "https://feeds.reuters.com/reuters/businessNews",
    "https://feeds.marketwatch.com/marketwatch/topstories/",
    "https://www.cnbc.com/id/20910258/device/rss/rss.html",
    "https://feeds.content.dowjones.io/public/rss/RSSMarketsMain",
]
