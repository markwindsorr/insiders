"""
Insider Detection Scorer 

Scores each wallet 0-100 for insider trading suspicion.

How it works:
1. Pull all wallet profiles from the wallets table in Supabase.
2. Compute 5 signals per wallet, each normalized 0-1:
   - wallet_age:     How new was the wallet when it first traded? (newer = more suspicious)
   - entry_timing:   How close to market resolution did it trade? (closer = more suspicious)
   - concentration:  How few markets did it trade? (fewer = more suspicious)
   - position_size:  How large were its trades relative to others? (bigger = more suspicious)
   - trade_count:    How few total trades? (fewer = more suspicious, insiders don't stick around)
3. Multiply each signal by a weight, sum them, scale to 0-100.
4. Write score back to wallets.suspicion_score in Supabase.

Why these weights?

- Manually tuned against 7 known insider wallets. With only 7 confirmed positives,
  statistical optimization (grid search etc.) would overfit. Manual tuning with
  documented rationale is more honest.

- wallet_age, entry_timing, concentration share top weight (0.25 each) because
  insiders consistently: use fresh wallets, trade right before resolution, and
  only bet on 1-3 markets. These are the three strongest behavioral indicators.

- position_size (0.15) is moderate — insiders bet big, but so do whales.

- trade_count (0.10) is supporting — few trades is suspicious but not definitive.
"""

from db.supabase_client import supabase
from datetime import datetime

# Known insider wallets (our ground truth for validation) 
KNOWN_INSIDERS = {
    "0xee50a31c3f5a7c77824b12a941a54388a2827ed6": "Google d4vd / alpha raccoon",
    "0x6baf05d193692bb208d616709e27442c910a94c5": "Maduro out / SBet365",
    "0x31a56e9e690c621ed21de08cb559e9524cdb8ed9": "Maduro out / unnamed",
    "0x0afc7ce56285bde1fbe3a75efaffdfc86d6530b2": "Israel-Iran / ricosuave",
    "0x7f1329ade2ec162c6f8791dad99125e0dc49801c": "Trump pardon CZ / gj1",
    "0x976685b6e867a0400085b1273309e84cd0fc627c": "MicroStrategy / fromagi",
    "0x55ea982cebff271722419595e0659ef297b48d7c": "DraftKings / flaccidwillie",
}

# Not an insider — smart trader who scraped public data. Use as negative example.
KNOWN_NEGATIVES = {
    "0xc51eedc01790252d571648cb4abd8e9876de5202": "Spotify scraper (not insider)",
}

# Weights (tuned against known insiders) 
WEIGHTS = {
    "wallet_age": 0.25,      # strong — insiders use fresh wallets
    "entry_timing": 0.25,    # strong — insiders trade right before resolution
    "concentration": 0.25,   # strong — insiders only bet on 1-3 markets
    "position_size": 0.15,   # moderate — insiders bet big, but so do whales
    "trade_count": 0.10,     # supporting — few trades is suspicious but not definitive
}


# --- Signal computation ---

def compute_wallet_age_signal(wallet):
    """
    Score 0-1 based on days between first USDC deposit and first trade.
    0 days (same day deposit and trade) = 1.0 (most suspicious)
    30+ days = 0.0 (not suspicious)
    """
    if not wallet.get("first_usdc_deposit_at") or not wallet.get("first_trade_at"):
        return 0.5  # unknown — neutral score

    deposit = datetime.fromisoformat(wallet["first_usdc_deposit_at"])
    trade = datetime.fromisoformat(wallet["first_trade_at"])
    days_gap = abs((trade - deposit).total_seconds()) / 86400  # seconds to days

    # 0 days gap = score 1.0, 30+ days gap = score 0.0
    return max(0, 1 - (days_gap / 30))


def compute_entry_timing_signal(wallet_address, markets_by_token):
    """
    Score 0-1 based on how close to market resolution the wallet traded.
    Trading 3 or fewer days before resolution = 1.0 (most suspicious)
    30+ days before = 0.0 (not suspicious)

    Uses the closest-to-resolution trade as the score (worst case).
    """
    result = supabase.table("trades").select("token_id, timestamp").eq("wallet", wallet_address).execute()
    trades = result.data
    if not trades:
        return 0.5  # no trades found — neutral

    best_signal = 0
    for trade in trades:
        market = markets_by_token.get(trade["token_id"])
        if not market or not market.get("resolution_time"):
            continue

        trade_time = datetime.fromisoformat(trade["timestamp"])
        resolution_time = datetime.fromisoformat(market["resolution_time"])
        days_before = (resolution_time - trade_time).total_seconds() / 86400

        if days_before < 0:
            # Traded after resolution — not relevant
            continue

        # 3 days or less before resolution = 1.0, 30+ days = 0.0
        signal = max(0, 1 - (days_before / 30))
        best_signal = max(best_signal, signal)

    return best_signal


def compute_concentration_signal(wallet):
    """
    Score 0-1 based on number of unique markets traded.
    1 market = 1.0 (most suspicious)
    10+ markets = 0.0 (diversified, not suspicious)
    """
    markets = wallet.get("unique_markets", 1)
    if markets <= 0:
        markets = 1
    return max(0, 1 - ((markets - 1) / 9))


def compute_position_size_signal(wallet, avg_volume):
    """
    Score 0-1 based on total volume relative to average trader.
    10x+ average = 1.0 (whale-sized bets, suspicious)
    At or below average = 0.0
    """
    if avg_volume <= 0:
        return 0
    ratio = wallet.get("total_volume", 0) / avg_volume
    return min(1, ratio / 10)


def compute_trade_count_signal(wallet):
    """
    Score 0-1 based on total number of trades.
    1-2 trades = 1.0 (hit and run, suspicious)
    20+ trades = 0.0 (active trader)
    """
    trades = wallet.get("total_trades", 1)
    return max(0, 1 - ((trades - 1) / 19))


def compute_score(wallet, avg_volume, markets_by_token):
    """Compute overall suspicion score 0-100 for a wallet."""
    signals = {
        "wallet_age": compute_wallet_age_signal(wallet),
        "entry_timing": compute_entry_timing_signal(wallet["address"], markets_by_token),
        "concentration": compute_concentration_signal(wallet),
        "position_size": compute_position_size_signal(wallet, avg_volume),
        "trade_count": compute_trade_count_signal(wallet),
    }

    # Weighted sum
    raw_score = sum(WEIGHTS[name] * value for name, value in signals.items())

    # Scale to 0-100
    score = round(raw_score * 100, 1)

    return score, signals


# --- Main ---

def run_scorer():
    """Score all wallets and output results."""
    print("Fetching wallets from Supabase...")
    result = supabase.table("wallets").select("*").execute()
    wallets = result.data

    if not wallets:
        print("No wallets found. Run indexer/trades.py and indexer/wallets.py first.")
        return

    # Load markets indexed by token_id for entry_timing lookups
    markets_result = supabase.table("markets").select("*").execute()
    markets_by_token = {}
    for m in markets_result.data:
        if m.get("token_id_yes"):
            markets_by_token[m["token_id_yes"]] = m
        if m.get("token_id_no"):
            markets_by_token[m["token_id_no"]] = m

    print(f"Scoring {len(wallets)} wallets ({len(markets_by_token)} market tokens loaded)...\n")

    # Compute average volume for the position_size signal
    volumes = [float(w.get("total_volume", 0)) for w in wallets]
    avg_volume = sum(volumes) / len(volumes) if volumes else 1

    # Score each wallet
    results = []
    for wallet in wallets:
        score, signals = compute_score(wallet, avg_volume, markets_by_token)

        results.append({
            "address": wallet["address"],
            "score": score,
            "signals": signals,
            "total_trades": wallet.get("total_trades", 0),
            "total_volume": round(float(wallet.get("total_volume", 0)), 2),
            "unique_markets": wallet.get("unique_markets", 0),
            "label": KNOWN_INSIDERS.get(wallet["address"],
                     KNOWN_NEGATIVES.get(wallet["address"], ""))
        })

        # Update suspicion_score in Supabase
        supabase.table("wallets").update({
            "suspicion_score": score
        }).eq("address", wallet["address"]).execute()

    # Sort by score descending
    results.sort(key=lambda x: x["score"], reverse=True)

    # --- Print to terminal ---
    print(f"{'Rank':<5} {'Address':<15} {'Score':<7} {'Age':<5} {'Time':<5} {'Conc':<5} {'Size':<5} "
          f"{'Trades':<7} {'Volume':<10} {'Markets':<8} {'Label'}")
    print("-" * 100)

    for i, r in enumerate(results):
        s = r["signals"]
        label = f"  ** {r['label']} **" if r["label"] else ""
        print(f"{i+1:<5} {r['address'][:12]}...  {r['score']:<7} "
              f"{s['wallet_age']:<5.2f} {s['entry_timing']:<5.2f} {s['concentration']:<5.2f} {s['position_size']:<5.2f} "
              f"{r['total_trades']:<7} ${r['total_volume']:<9} {r['unique_markets']:<8}{label}")

    # --- Validation summary ---
    print("\n--- Known Insider Check ---")
    for addr, label in KNOWN_INSIDERS.items():
        match = next((r for r in results if r["address"] == addr), None)
        if match:
            rank = results.index(match) + 1
            print(f"  {label}: score {match['score']}, rank {rank}/{len(results)}")
        else:
            print(f"  {label}: NOT IN DATASET (need to index their trades first)")


# --- Run it ---

if __name__ == "__main__":
    run_scorer()
