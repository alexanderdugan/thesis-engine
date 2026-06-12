#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from thesis_engine.database import init_db
from thesis_engine.performance import take_snapshot

if __name__ == "__main__":
    init_db()
    result = take_snapshot()
    if result["status"] == "skipped":
        print(f"Skipped: {result['reason']}")
    else:
        print(f"Snapshot taken for {result['date']}")
        print(f"  Portfolio value: ${result['portfolio_value']:,.2f}")
        if result.get("warning"):
            print(f"\n  ⚠️  WARNING: {result['warning']}")
