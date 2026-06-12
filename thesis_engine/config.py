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
