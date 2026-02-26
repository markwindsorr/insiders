## Blockchains in the Context of What We're Building

A blockchain is a database that's append-only and public. That's it at the core. Instead of a Supabase table where you can update/delete rows, a blockchain only lets you add new entries. And anyone can read them.

---

### Blocks

Blocks are batches of transactions. Every ~2 seconds on Polygon, a new block is produced. Each block contains a bunch of transactions that happened in that window. Blocks are numbered sequentially — block 83360407 means 83 million blocks have been produced since Polygon started.

```
Block 81727268          Block 81727269          Block 81727270
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│ tx 0x6599f...   │     │ tx 0xabc...     │     │ tx 0x123...     │
│ tx 0x1234...    │     │ tx 0xdef...     │     │                 │
│ tx 0x5678...    │     │                 │     │                 │
│ timestamp: ...  │     │ timestamp: ...  │     │ timestamp: ...  │
└────────┬────────┘     └────────┬────────┘     └────────┬────────┘
         │                       │                       │
         └───────────────────────┴───────────────────────┘
                    Linked together (the "chain")
```

A block's actual data structure (what `w3.eth.get_block()` returns):

```python
{
    "number": 81727268,              # Sequential block number
    "timestamp": 1717200000,         # Unix timestamp (seconds since 1970)
    "hash": "0xabc123...",           # This block's unique hash
    "parentHash": "0xdef456...",     # Previous block's hash (the "chain" link)
    "transactions": [                # List of transaction hashes in this block
        "0x6599fcc5...",
        "0x1234abcd...",
    ],
    "gasUsed": 12345678,             # Total computation used by all txs
}
```

The `parentHash` is what makes it a chain — each block points to the previous one. You can't alter block 100 without breaking block 101's parentHash, which breaks 102, etc. That's the immutability guarantee.

---

### Transactions

A transaction is someone doing something — sending money, placing a trade, deploying a contract. Our sample transaction `0x6599f...` was someone executing a trade on Polymarket. One transaction can trigger multiple things — that's why it produced 9 event logs.

What a transaction looks like (what `w3.eth.get_transaction()` returns):

```python
{
    "hash": "0x6599fcc5...",         # Unique ID for this transaction
    "from": "0x7f13...",             # The wallet that initiated it (and paid gas)
    "to": "0x4bFb41d5...",           # The contract being called (CTF Exchange)
    "value": 0,                      # ETH/MATIC sent (0 for contract calls)
    "input": "0xa9059cbb...",        # Encoded function call data (which function + args)
    "blockNumber": 81727268,
    "gasPrice": 30000000000,         # Price per unit of computation
}
```

Key things:
- `from` is always a wallet (a person). Only wallets can initiate transactions.
- `to` is the contract being called. For Polymarket trades, this is the CTF Exchange.
- `input` is the encoded function call. The first 4 bytes are the function selector (which function to call), the rest are the encoded arguments. We don't need to decode this directly — we read the events instead.
- `value` is for sending native currency (MATIC on Polygon). Token transfers (like USDC) happen through contract calls, not through `value`.

---

### Transaction Receipts

After a transaction executes, the blockchain produces a receipt. This is the record of what actually happened — did it succeed? What events were emitted? How much gas was used?

```python
receipt = w3.eth.get_transaction_receipt("0x6599fcc5...")
{
    "transactionHash": "0x6599fcc5...",
    "status": 1,                     # 1 = success, 0 = reverted (failed)
    "blockNumber": 81727268,
    "gasUsed": 234567,               # Actual computation consumed
    "logs": [                        # THE IMPORTANT PART — event logs
        { ... },  # Log 0
        { ... },  # Log 1
        ...       # Up to 9 logs for this transaction
    ]
}
```

The `logs` array is where our data lives. Each log is an event emitted by a smart contract during this transaction's execution.

---

### Events and Logs (Our Primary Data Source)

Events/logs are how contracts announce what happened. When the CTF Exchange executes a trade, it writes a log entry (the OrderFilled event) into the transaction receipt. These logs are permanent and public.

A raw log looks like this:

```python
{
    "address": "0x4bFb41d5...",      # Which contract emitted this event
    "topics": [
        "0xd0a08e8c...",            # topics[0]: event signature hash
        "0x1234abcd...",            # topics[1]: first indexed param (orderHash)
        "0x7f130000...",            # topics[2]: second indexed param (maker)
        "0xee500000...",            # topics[3]: third indexed param (taker)
    ],
    "data": "0x00000000...",         # Non-indexed params, ABI-encoded
    "blockNumber": 81727268,
    "transactionHash": "0x6599fcc5...",
    "logIndex": 3,                   # Position within this transaction's logs
}
```

**Topics vs Data — how events are structured:**

In Solidity (the smart contract language), an event declaration looks like:

```solidity
event OrderFilled(
    bytes32 indexed orderHash,    // → topics[1]
    address indexed maker,        // → topics[2]
    address indexed taker,        // → topics[3]
    uint256 makerAssetId,         // → packed in data
    uint256 takerAssetId,         // → packed in data
    uint256 makerAmountFilled,    // → packed in data
    uint256 takerAmountFilled,    // → packed in data
    uint256 fee                   // → packed in data
);
```

- `topics[0]` is always the keccak256 hash of the event signature. This is how we filter for specific events — OrderFilled's signature always hashes to `0xd0a08e8c...`
- `topics[1-3]` are the `indexed` parameters (max 3). These are stored separately so you can filter on them efficiently. That's why `get_logs` can filter by maker or taker address.
- `data` contains everything else, packed together in 32-byte chunks using ABI encoding.

**The ABI is the decoder ring.** The raw log is just hex bytes. The ABI (Application Binary Interface) tells web3.py how to decode those bytes back into named fields with proper types. Without the ABI, `data` is just `0x000000000000...`. With it, web3 can tell you `makerAmountFilled = 5000000` (which is 5 USDC, since USDC has 6 decimal places).

This is why `db/abis.py` exists — it contains the ABI definitions that let us decode OrderFilled and Transfer events.

---

### How `get_logs` Works (What Our Indexer Does)

There are two ways to read events from the blockchain:

1. **`get_transaction_receipt(tx_hash)`** — Get ALL logs for ONE specific transaction. You need to already know the transaction hash. Used in our tests.

2. **`get_logs(filter)`** — Get all logs matching a filter across MANY blocks. The filter specifies: which contract address, which event signature, and which block range. This is what our indexer uses.

```python
# What our indexer does under the hood:
logs = w3.eth.get_logs({
    "address": "0x4bFb41d5...",           # Only from CTF Exchange
    "topics": ["0xd0a08e8c..."],          # Only OrderFilled events
    "fromBlock": 81727268,
    "toBlock": 81727768,                  # 500 block range (RPC limit)
})
```

The RPC node scans its copy of the blockchain and returns every matching log. We chunk into 500-block ranges because RPC providers limit how many blocks you can scan per call.

web3.py wraps this nicely — `contract.events.OrderFilled().get_logs()` builds the filter and decodes the results automatically using the ABI.

---

### Addresses, Wallets, and Contracts

Everything on the blockchain has an address — a 42-character hex string starting with `0x`.

```
Wallet:   0xee50a31c3f5a7c77824b12a941a54388a2827ed6
Contract: 0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E
```

- **Wallets** are controlled by a private key. Whoever has the private key can sign transactions from that address. Creating a wallet is free and instant — just generate a random private key and derive the address. This is why insiders can make fresh wallets trivially.
- **Contracts** are code deployed to an address. Once deployed, the code can't change. The CTF Exchange contract lives at its address forever, running the same logic.

You can't tell from an address alone whether it's a wallet or a contract. But you can check: contracts have code stored at their address (`w3.eth.get_code(address)` returns non-empty bytes), wallets don't.

---

### ERC-20 Tokens (USDC.e)

ERC-20 is a standard interface that all fungible tokens on Ethereum/Polygon follow. USDC.e, the bridged USDC stablecoin, is an ERC-20 token.

The standard defines a `Transfer` event:

```solidity
event Transfer(
    address indexed from,    // → topics[1]: sender
    address indexed to,      // → topics[2]: receiver
    uint256 value            // → data: amount transferred
);
```

Every time USDC.e moves between addresses, this event is emitted. We use this to find when a wallet first received USDC — their "birth date" for our wallet_age signal.

```
USDC.e contract: 0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174
```

USDC has 6 decimal places. So a `value` of `5000000` in the Transfer event = 5.00 USDC. This is different from ETH/MATIC which have 18 decimals. Always divide by `10^decimals` to get the human-readable amount.

---

### How a Polymarket Trade Works On-Chain

When someone places a trade on Polymarket, here's what happens at the blockchain level:

```
1. User submits order through Polymarket's UI/API
        │
        ▼
2. Polymarket's matching engine pairs maker + taker off-chain
        │
        ▼
3. Matched order submitted as a transaction to the CTF Exchange contract
        │
        ▼
4. CTF Exchange contract executes:
   a. Verify signatures (maker and taker both agreed to this trade)
   b. Transfer USDC from buyer to seller
   c. Transfer outcome tokens from seller to buyer
   d. Emit OrderFilled event with all details
        │
        ▼
5. Transaction included in next Polygon block (~2 seconds)
        │
        ▼
6. Our indexer picks up the OrderFilled event via get_logs
```

**What are outcome tokens?** Each Polymarket market has two tokens: YES and NO. If you think "Will X happen?" is yes, you buy YES tokens. Each token is identified by a `token_id` (a large number). If the market resolves YES, each YES token is worth $1, NO tokens worth $0.

The `makerAssetId` and `takerAssetId` in the OrderFilled event tell us which side each party was on. If one side's asset ID is `0`, that's USDC (they paid cash). The other side is the outcome token. This is how `trades.py` determines BUY vs SELL:

```python
if args["takerAssetId"] == 0:
    # Taker paid USDC → they're buying outcome tokens
    wallet = args["taker"]
    side = "BUY"
else:
    # Maker paid USDC → they're selling outcome tokens
    wallet = args["maker"]
    side = "SELL"
```

---

### Why This Matters for Insider Detection

Every trade on Polymarket is a public, permanent, timestamped record on Polygon. The trader can create an anonymous wallet, but they can't hide the trade itself. We can see:

- Exactly when they traded (block timestamp)
- How much they spent (amounts in the event)
- Which market they bet on (token ID)
- When they first received USDC (first Transfer event to their wallet)

The insiders know this, which is why they use fresh wallets — but the trading pattern still gives them away. That's what our scoring algorithm catches.

---

### The RPC Node

We can't read the blockchain directly — it's a distributed network of thousands of computers. The RPC node (Alchemy, Ankr, QuickNode) is a server that maintains a copy of the full blockchain and lets us query it via HTTP using the JSON-RPC protocol.

```
Our Python code  ──HTTP POST──>  RPC Node (e.g. Alchemy, Ankr)  ──reads──>  Polygon Blockchain
     │                                    │
     │  "give me all OrderFilled          │  Scans its local copy
     │   events in blocks                 │  of the blockchain
     │   81727268 to 81727768"            │
     │                                    │
     │  <── JSON response ────────────────┘
     │  [decoded event logs]
```

Different providers (Alchemy, Ankr, QuickNode) are just different servers holding the same data. They differ in rate limits, pricing, and reliability. The `POLYGON_RPC_URL` in our `.env` points to whichever provider we're using.

`db/web3_client.py` creates a single shared connection to the RPC node. All our indexer modules import `w3` from there instead of creating their own connections.
