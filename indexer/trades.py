"""
Trade Indexer

Pulls OrderFilled events from the Polymarket CTF Exchange contract
and stores them in the Supabase 'trades' table.

How it works:
1. We ask the Polygon node for all logs matching the OrderFilled event
   signature, within a block range (get_logs).
2. web3 decodes each log using the ABI into readable fields.
3. We get the block timestamp (so we know WHEN the trade happened).
4. We insert each trade into Supabase.

get_logs vs get_transaction_receipt:
- get_transaction_receipt: fetches ALL logs for ONE transaction
- get_logs: fetches logs matching a FILTER across MANY blocks
  The filter is: contract address + event signature hash.
  This is how we scan the chain efficiently.
"""

from web3 import Web3
from config import CTF_EXCHANGE_ADDRESS
from db.web3_client import w3
from db.abis import ORDER_FILLED_ABI
from db.supabase_client import supabase
import sys
import time
from datetime import datetime, timezone

contract = w3.eth.contract(
    address=Web3.to_checksum_address(CTF_EXCHANGE_ADDRESS),
    abi=ORDER_FILLED_ABI
)

# --- Core functions ---

_block_ts_cache = {}

def get_block_timestamp(block_number):
    """Get the timestamp of a block as an ISO string. Cached per block."""
    if block_number not in _block_ts_cache:
        block = w3.eth.get_block(block_number)
        _block_ts_cache[block_number] = datetime.fromtimestamp(block["timestamp"], tz=timezone.utc).isoformat()
    return _block_ts_cache[block_number]


def fetch_trades(from_block, to_block):
    """
    Fetch all OrderFilled events between two blocks.
    Returns a list of decoded trade dicts ready for Supabase.
    """
    # This single RPC call gets all OrderFilled events in the range.
    # The node filters by contract address and event signature for us.
    logs = contract.events.OrderFilled().get_logs(
        from_block=from_block,
        to_block=to_block
    )

    trades = []
    for log in logs:
        args = log["args"]

        # Determine which side is USDC (asset ID 0) and which is the token
        if args["takerAssetId"] == 0:
            # Taker paid USDC, maker sold tokens
            wallet = args["taker"]
            token_id = str(args["makerAssetId"])
            size = args["takerAmountFilled"] / 1e6  # USDC has 6 decimals
            side = "BUY"
        else:
            # Maker paid USDC, taker sold tokens
            wallet = args["maker"]
            token_id = str(args["takerAssetId"])
            size = args["makerAmountFilled"] / 1e6
            side = "SELL"

        trades.append({
            "wallet": wallet.lower(),
            "token_id": token_id,
            "side": side,
            "size": size,
            "tx_hash": f"{log['transactionHash'].hex()}_{log['logIndex']}",
            "block_number": log["blockNumber"],
            "timestamp": get_block_timestamp(log["blockNumber"])
        })

    return trades


def store_trades(trades):
    """Insert trades into Supabase in batches."""
    if not trades:
        return

    batch_size = 1000
    for i in range(0, len(trades), batch_size):
        batch = trades[i:i + batch_size]
        supabase.table("trades").upsert(
            batch,
            on_conflict="tx_hash"
        ).execute()

    print(f"  Stored {len(trades)} trades")


def get_last_indexed_block():
    """Check the highest block number already in the trades table."""
    result = supabase.table("trades").select("block_number").order("block_number", desc=True).limit(1).execute()
    if result.data:
        return result.data[0]["block_number"]
    return None


def index_range(from_block, to_block, chunk_size=500):
    """
    Index trades across a large block range.
    Skips blocks already in the database.
    Breaks into chunks because RPC nodes limit get_logs calls.
    """
    # Skip blocks we've already indexed
    last_indexed = get_last_indexed_block()
    if last_indexed and last_indexed >= from_block:
        print(f"Already indexed up to block {last_indexed}, resuming from {last_indexed + 1}")
        from_block = last_indexed + 1

    if from_block > to_block:
        print("Nothing new to index.")
        return 0

    current = from_block
    total = 0

    while current <= to_block:
        chunk_end = min(current + chunk_size - 1, to_block)
        print(f"Scanning blocks {current} - {chunk_end}...")

        trades = fetch_trades(current, chunk_end)
        if trades:
            store_trades(trades)
            total += len(trades)

        current = chunk_end + 1

    print(f"\nDone. Indexed {total} trades total.")
    return total


def run_live(poll_interval=5):
    """
    Continuously index new trades as they appear on-chain.
    Polls for new blocks every poll_interval seconds, then reuses
    index_range() to fetch and store any new OrderFilled events.
    """
    print("Starting live trade indexer...")
    last_block = w3.eth.block_number
    print(f"Starting from block {last_block}")

    while True:
        time.sleep(poll_interval)
        latest = w3.eth.block_number

        if latest > last_block:
            print(f"\nNew blocks: {last_block + 1} → {latest}")
            index_range(last_block + 1, latest)
            last_block = latest


# --- Run it ---

if __name__ == "__main__":
    if "--live" in sys.argv:
        # poll every 5 seconds by default for live
        run_live()
    else:
        # Default: index a meaningful historical range
        # Block 81727268 contains our sample transaction from the assignment
        from_block = int(sys.argv[1]) if len(sys.argv) > 1 else 81727268
        to_block = int(sys.argv[2]) if len(sys.argv) > 2 else from_block + 2000
        index_range(from_block, to_block)