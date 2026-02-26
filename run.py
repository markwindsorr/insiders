"""
Run the full insider detection pipeline in order.

Usage:
    python run.py              # Run all steps
    python run.py --live       # After pipeline, start live indexer
"""

import subprocess
import sys

STEPS = [
    ("Index trades", [sys.executable, "-m", "indexer.trades"]),
    ("Index markets", [sys.executable, "-m", "indexer.markets"]),
    ("Index wallets", [sys.executable, "-m", "indexer.wallets"]),
    ("Score wallets", [sys.executable, "-m", "detection.scorer"]),
]

if __name__ == "__main__":
    for name, cmd in STEPS:
        print(f"\n{'='*60}")
        print(f"  {name}")
        print(f"{'='*60}\n")
        result = subprocess.run(cmd)
        if result.returncode != 0:
            print(f"\n{name} failed (exit code {result.returncode}). Stopping.")
            sys.exit(1)

    if "--live" in sys.argv:
        print(f"\n{'='*60}")
        print(f"  Starting live indexer")
        print(f"{'='*60}\n")
        subprocess.run([sys.executable, "-m", "indexer.trades", "--live"])