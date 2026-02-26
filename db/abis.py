"""
Shared ABI definitions for blockchain event decoding.

ABIs (Application Binary Interfaces) tell web3 how to decode
raw hex log data into named fields.
"""

import json

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

TRANSFER_ABI = json.loads("""[{
    "anonymous": false,
    "inputs": [
        {"indexed": true, "name": "from", "type": "address"},
        {"indexed": true, "name": "to", "type": "address"},
        {"indexed": false, "name": "value", "type": "uint256"}
    ],
    "name": "Transfer",
    "type": "event"
}]""")