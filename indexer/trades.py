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
from config import POLYGON_RPC_URL, CTF_EXCHANGE_ADDRESS
from db.supabase_client import supabase
import requests
import json
from datetime import datetime, timezone

# --- Setup ---

session = requests.Session()
session.trust_env = False

w3 = Web3(Web3.HTTPProvider(POLYGON_RPC_URL, session=session))

ORDER_FILLED_ABI = json.loads("""[{
    "anonymous": false,
    "inputs": [
        {"indexed": true, "name": "orderHash", "type": "bytes32"},
        {"indexed": true, "name": "maker", "type": "address"},
        {"indexed": true, "name": "taker", "type": "address"},
        {"indexed": false, "name": "makerAssetId", "type": "uint256"},
        {"indexed": false, "name": "takerAssetId", "type": "uint256"},
        {"indexed": false, "name": "makerAmountFilled", "type": "uint256"},
        {"indexed": false, "name": "takerAmountFilled", "type": "uint256"},
        {"indexed": false, "name": "fee", "type": "uint256"}
    ],
    "name": "OrderFilled",
    "type": "event"
}]""")

contract = w3.eth.contract(
    address=Web3.to_checksum_address(CTF_EXCHANGE_ADDRESS),
    abi=ORDER_FILLED_ABI
)

# --- Core functions ---

def get_block_timestamp(block_number):
    """Get the timestamp of a block as an ISO string."""
    block = w3.eth.get_block(block_number)
    return datetime.fromtimestamp(block["timestamp"], tz=timezone.utc).isoformat()


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
            side = "BUY"

        trades.append({
            "wallet": wallet.lower(),
            "token_id": token_id,
            "side": side,
            "size": size,
            "price": round(min(args["makerAmountFilled"], args["takerAmountFilled"])
                          / max(args["makerAmountFilled"], args["takerAmountFilled"]), 4),
            "tx_hash": log["transactionHash"].hex(),
            "block_number": log["blockNumber"],
            "timestamp": get_block_timestamp(log["blockNumber"])
        })

    return trades


def store_trades(trades):
    """Insert trades into Supabase in batches of 50 to avoid payload limits."""
    if not trades:
        return

    batch_size = 50
    for i in range(0, len(trades), batch_size):
        batch = trades[i:i + batch_size]
        supabase.table("trades").upsert(
            batch,
            on_conflict="tx_hash"
        ).execute()

    print(f"  Stored {len(trades)} trades")


def index_range(from_block, to_block, chunk_size=500):
    """
    Index trades across a large block range.
    Breaks it into chunks because RPC nodes limit how many blocks
    you can scan in one get_logs call (usually 2000-10000).
    """
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


# --- Run it ---

if __name__ == "__main__":
    # Test with a small range around our sample transaction (block 81727268)
    # Just 100 blocks to verify everything works end-to-end
    test_block = 81727268
    index_range(test_block, test_block + 100)