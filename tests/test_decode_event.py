"""
ABI = Application Binary Interface

The ABI tells web3 how to decode raw hex log data into named fields.
For the OrderFilled event:
  - topics[0] = event signature hash (always d0a08e8c...)
  - topics[1] = orderHash (bytes32) — unique order ID
  - topics[2] = maker address — the wallet that placed the resting order
  - topics[3] = taker address — the wallet that filled against it
  - data = packed encoding of: makerAssetId, takerAssetId,
           makerAmountFilled, takerAmountFilled, fee

The 'indexed' keyword in Solidity puts values in topics (max 3).
Everything else gets encoded in the data field.
"""

from web3 import Web3
from config import POLYGON_RPC_URL, CTF_EXCHANGE_ADDRESS
import requests
import json

session = requests.Session()
session.trust_env = False

web_three = Web3(Web3.HTTPProvider(POLYGON_RPC_URL, session=session))

# This is the ABI for just the OrderFilled event.
# It's derived from the Solidity event definition in Trading.sol.
# web3 uses this to know how to unpack the hex data.
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

# Create a contract object — this gives us event decoding capabilities
contract = web_three.eth.contract(
    address=Web3.to_checksum_address(CTF_EXCHANGE_ADDRESS),
    abi=ORDER_FILLED_ABI
)

# Fetch the sample transaction
sample_tx = "0x6599fcc58912b6ea1f3fbed5a801b28399097edfac3216fbf3cbbc9763837273"
receipt = web_three.eth.get_transaction_receipt(sample_tx)

# Decode only the OrderFilled events from the receipt
# process_receipt filters logs by contract address and event signature,
# then decodes them using the ABI
events = contract.events.OrderFilled().process_receipt(receipt)

print(f"Found {len(events)} OrderFilled events\n")

for i, event in enumerate(events):
    args = event["args"]
    print(f"Trade {i + 1}:")
    print(f"  Order Hash:    {args['orderHash'].hex()}")
    print(f"  Maker:         {args['maker']}")
    print(f"  Taker:         {args['taker']}")
    print(f"  Maker Asset:   {args['makerAssetId']}")
    print(f"  Taker Asset:   {args['takerAssetId']}")
    print(f"  Maker Amount:  {args['makerAmountFilled']}")
    print(f"  Taker Amount:  {args['takerAmountFilled']}")
    print(f"  Fee:           {args['fee']}")
    print()