"""
Wallet Indexer (Deliverable 2b)

Finds the first USDC.e deposit for each wallet that appears in our trades table.
This gives us the "wallet age" signal — how long before trading did this wallet exist?

How it works:
1. Query Supabase for all unique wallet addresses from the trades table.
2. For each wallet, query the USDC.e contract's Transfer events where 'to' = that wallet.
3. The earliest Transfer = when the wallet first received funds.
4. Store wallet profile (first deposit, first trade, volume, market count) in the wallets table.

The Transfer event ABI (standard ERC-20):
    event Transfer(address indexed from, address indexed to, uint256 value)
    - topics[0] = event signature hash
    - topics[1] = sender address (indexed)
    - topics[2] = receiver address (indexed)
    - data = amount transferred
"""

from web3 import Web3
from config import USDC_E_ADDRESS
from db.web3_client import w3
from db.abis import TRANSFER_ABI
from db.supabase_client import supabase
from datetime import datetime, timezone

usdc_contract = w3.eth.contract(
    address=Web3.to_checksum_address(USDC_E_ADDRESS),
    abi=TRANSFER_ABI
)


# --- Core functions ---

def get_wallets_from_trades():
    """Get all unique wallets and their basic stats from the trades table."""
    result = supabase.table("trades").select("wallet, size, token_id, timestamp, block_number").execute()
    rows = result.data

    wallets = {}
    for row in rows:
        addr = row["wallet"]
        if addr not in wallets:
            wallets[addr] = {
                "address": addr,
                "total_trades": 0,
                "total_volume": 0,
                "markets": set(),
                "first_trade_at": row["timestamp"],
                "first_block": row["block_number"]
            }

        w = wallets[addr]
        w["total_trades"] += 1
        w["total_volume"] += float(row["size"])
        w["markets"].add(row["token_id"])

        # Track earliest trade
        if row["timestamp"] < w["first_trade_at"]:
            w["first_trade_at"] = row["timestamp"]
            w["first_block"] = row["block_number"]

    return wallets


def find_first_usdc_deposit(wallet_address, before_block):
    """
    Find the first USDC.e Transfer TO this wallet.
    Searches backwards from before_block in chunks.
    Returns an ISO timestamp string, or None if not found.
    """
    chunk_size = 1000
    current = before_block

    # Search backwards up to 10k blocks (~5 hours on Polygon)
    earliest_block = max(0, before_block - 10000)

    while current > earliest_block:
        from_block = max(current - chunk_size, earliest_block)

        try:
            logs = usdc_contract.events.Transfer().get_logs(
                from_block=from_block,
                to_block=current,
                argument_filters={"to": Web3.to_checksum_address(wallet_address)}
            )
        except Exception as e:
            print(f"    Error querying blocks {from_block}-{current}: {e}")
            current = from_block - 1
            continue

        if logs:
            # Get the earliest log in this batch
            earliest_log = min(logs, key=lambda x: x["blockNumber"])
            block = w3.eth.get_block(earliest_log["blockNumber"])
            return datetime.fromtimestamp(block["timestamp"], tz=timezone.utc).isoformat()

        current = from_block - 1

    return None


def index_wallets():
    """Main function: build wallet profiles from trades + USDC.e deposits."""
    print("Fetching wallets from trades table...")
    wallets = get_wallets_from_trades()
    print(f"Found {len(wallets)} unique wallets\n")

    for i, (addr, data) in enumerate(wallets.items()):
        print(f"[{i+1}/{len(wallets)}] Processing {addr[:10]}...")

        # Find first USDC.e deposit
        deposit_time = find_first_usdc_deposit(addr, data["first_block"])
        if deposit_time:
            print(f"    First deposit: {deposit_time}")
        else:
            print(f"    No USDC.e deposit found")

        # Upsert wallet profile into Supabase
        supabase.table("wallets").upsert({
            "address": addr,
            "first_usdc_deposit_at": deposit_time,
            "first_trade_at": data["first_trade_at"],
            "total_trades": data["total_trades"],
            "total_volume": round(data["total_volume"], 2),
            "unique_markets": len(data["markets"])
        }, on_conflict="address").execute()

    print(f"\nDone. Indexed {len(wallets)} wallets.")


# --- Run it ---

if __name__ == "__main__":
    index_wallets()
