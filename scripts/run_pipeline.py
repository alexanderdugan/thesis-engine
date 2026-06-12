#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from research.pipeline import run_pipeline

if __name__ == "__main__":
    print("Running research pipeline...")
    stats = run_pipeline()
    print(f"\nDone.")
    print(f"  Fetched : {stats['fetched']}")
    print(f"  New     : {stats['new']}")
    print(f"  Evaluated: {stats['evaluated']}")
    print(f"  Worth reading: {stats['worth_reading']}")
    if stats["errors"]:
        print(f"  Errors  : {stats['errors']}")
