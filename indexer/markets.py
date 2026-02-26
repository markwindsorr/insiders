"""
Market Metadata Indexer

Fetches market metadata (question, resolution time, token IDs) from the
Polymarket Gamma API and stores it in the 'markets' table.

Needed for the entry_timing signal: we need to know WHEN a market resolves
to measure how close to resolution each trade was placed.
"""

import requests
import json
from db.supabase_client import supabase

GAMMA_API = "https://gamma-api.polymarket.com"


def get_token_ids_from_trades():
    """Get all unique token_ids from the trades table."""
    result = supabase.table("trades").select("token_id").execute()
    return list({row["token_id"] for row in result.data})


def fetch_market_for_token(token_id):
    """Query Gamma API for the market containing this token_id."""
    try:
        resp = requests.get(
            f"{GAMMA_API}/markets",
            params={"clob_token_ids": token_id},
            timeout=10
        )
        resp.raise_for_status()
        markets = resp.json()
        if not markets:
            return None

        m = markets[0]
        raw_ids = m.get("clobTokenIds", [])
        clob_ids = json.loads(raw_ids) if isinstance(raw_ids, str) else raw_ids
        return {
            "condition_id": m["conditionId"],
            "question": m.get("question"),
            "resolution_time": m.get("endDate"),
            "token_id_yes": clob_ids[0] if len(clob_ids) > 0 else None,
            "token_id_no": clob_ids[1] if len(clob_ids) > 1 else None,
        }
    except Exception as e:
        print(f"  Error fetching market for token {token_id[:20]}...: {e}")
        return None


def index_markets():
    """Fetch market metadata for all traded tokens, upsert into markets table."""
    print("Fetching unique token_ids from trades table...")
    token_ids = get_token_ids_from_trades()
    print(f"Found {len(token_ids)} unique token_ids\n")

    seen = set()
    stored = 0

    for i, token_id in enumerate(token_ids):
        print(f"[{i+1}/{len(token_ids)}] Looking up token {token_id[:20]}...")
        market = fetch_market_for_token(token_id)
        if not market:
            print("    Not found")
            continue

        cid = market["condition_id"]
        if cid in seen:
            continue
        seen.add(cid)

        supabase.table("markets").upsert(market, on_conflict="condition_id").execute()
        stored += 1
        print(f"    {market['question'][:60]}...")

    print(f"\nDone. Stored {stored} markets.")


if __name__ == "__main__":
    index_markets()
