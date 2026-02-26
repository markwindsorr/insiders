"""
Unit tests for the scoring signal functions.

These test the pure math — no RPC or Supabase needed.
Run: python -m tests.test_scorer
"""

from detection.scorer import (
    compute_wallet_age_signal,
    compute_concentration_signal,
    compute_position_size_signal,
    compute_trade_count_signal,
)

passed = 0
failed = 0

def check(name, got, expected, tolerance=0.01):
    global passed, failed
    if abs(got - expected) <= tolerance:
        passed += 1
    else:
        failed += 1
        print(f"  FAIL: {name} — expected {expected}, got {got}")


# --- wallet_age: 0 days gap = 1.0, 30+ days = 0.0 ---

print("wallet_age signal:")
# Same-day deposit and trade → most suspicious
check("same day", compute_wallet_age_signal({
    "first_usdc_deposit_at": "2024-06-01T00:00:00+00:00",
    "first_trade_at": "2024-06-01T12:00:00+00:00",
}), 0.98)

# 30+ day gap → not suspicious
check("old wallet", compute_wallet_age_signal({
    "first_usdc_deposit_at": "2024-01-01T00:00:00+00:00",
    "first_trade_at": "2024-06-01T00:00:00+00:00",
}), 0.0)

# Missing data → neutral
check("missing data", compute_wallet_age_signal({}), 0.5)


# --- concentration: 1 market = 1.0, 10+ = 0.0 ---

print("concentration signal:")
check("1 market", compute_concentration_signal({"unique_markets": 1}), 1.0)
check("5 markets", compute_concentration_signal({"unique_markets": 5}), 0.56)
check("10 markets", compute_concentration_signal({"unique_markets": 10}), 0.0)


# --- position_size: 10x avg = 1.0, at avg = 0.1 ---

print("position_size signal:")
check("10x avg", compute_position_size_signal({"total_volume": 10000}, 1000), 1.0)
check("at avg", compute_position_size_signal({"total_volume": 1000}, 1000), 0.1)
check("below avg", compute_position_size_signal({"total_volume": 0}, 1000), 0.0)


# --- trade_count: 1 trade = 1.0, 20+ = 0.0 ---

print("trade_count signal:")
check("1 trade", compute_trade_count_signal({"total_trades": 1}), 1.0)
check("10 trades", compute_trade_count_signal({"total_trades": 10}), 0.53)
check("20 trades", compute_trade_count_signal({"total_trades": 20}), 0.0)


# --- Summary ---

print(f"\n{passed} passed, {failed} failed")
if failed:
    exit(1)
