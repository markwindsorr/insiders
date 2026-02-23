# Polymarket Insider Trading Detection — Plan

## Context

Build a backend pipeline that indexes Polymarket trades from the Polygon blockchain, stores them in Supabase, and scores wallets for insider-like behavior. No frontend — just scripts, a detection engine, and clear architecture decisions we can defend to the CTO.

---

## Key Concepts

| Concept | What it means |
|---|---|
| **OrderFilled event** | On-chain log from Polymarket's CTF Exchange on Polygon. Every trade: who, which market, side, size, price, when. Our primary data source. |
| **USDC.e Transfer** | ERC-20 Transfer on `0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174`. First inbound transfer to a wallet = wallet "birth date". |
| **Market resolution** | When a market's outcome is determined. Insiders trade right before this. |
| **Scoring model** | Weighted sum of signals per wallet. Tuned so known insiders score high. |

---

## Architecture

```
Polygon RPC (Alchemy / QuickNode)
        |
        v
  Event Indexer (Python + web3.py)
    - OrderFilled events (backfill + live)
    - USDC.e Transfer events (first deposit per wallet)
        |
        v
  Supabase (PostgreSQL)
    - trades, wallets, markets tables
    - Row-level security off for backend-only access
    - Use supabase-py client for inserts/queries
        |
        v
  Detection Algorithm (Python)
    - Compute per-wallet signals
    - Weighted scoring → suspicion score 0–100
    - Output: ranked flagged wallets
```

### Why Supabase?
- Managed Postgres — no infra to maintain, instant setup
- Built-in REST API + Python client (`supabase-py`) for quick integration
- Easy to add real-time subscriptions later if we want live alerting
- Free tier is enough for this scope
- If CTO asks: "It's just Postgres underneath, so we're not locked in. We can migrate to self-hosted Postgres or any other provider with a pg_dump."

---

## Database Schema

### `trades`
| Column | Type | Notes |
|---|---|---|
| id | uuid (default) | PK |
| wallet | text | Trader address |
| token_id | text | Outcome token traded |
| market_id | text | Condition ID / market identifier |
| side | text | BUY/SELL |
| size | numeric | Amount in USDC |
| price | numeric | Price paid per token |
| tx_hash | text | Unique, for dedup |
| block_number | bigint | |
| timestamp | timestamptz | |

### `wallets`
| Column | Type | Notes |
|---|---|---|
| address | text | PK |
| first_usdc_deposit_at | timestamptz | First inbound USDC.e transfer |
| first_trade_at | timestamptz | Derived from trades |
| total_trades | int | |
| total_volume | numeric | |
| unique_markets | int | |
| suspicion_score | numeric | Computed by detection algo |

### `markets`
| Column | Type | Notes |
|---|---|---|
| condition_id | text | PK |
| question | text | Market question |
| resolution_time | timestamptz | When it resolved |
| outcome | text | YES/NO/null if unresolved |
| token_id_yes | text | |
| token_id_no | text | |

---

## Scoring Signals (all normalized 0–1)

1. **Wallet age** — Days between first USDC deposit and first trade. Newer = more suspicious.
2. **Entry timing** — How close to market resolution they traded. Closer = more suspicious.
3. **Trade concentration** — Number of unique markets traded. Fewer = more suspicious.
4. **Position size** — Trade volume relative to market average. Bigger = more suspicious.
5. **Win rate** — Win rate on concentrated bets. High win + few markets = suspicious.

**Score** = `w1*age + w2*timing + w3*concentration + w4*size + w5*win_rate`

Weights tuned against the 8 known insider wallets (positives) vs. sampled normal wallets (negatives).

### Why a weighted scoring model and not ML?
- We only have ~8 confirmed positives — not enough for supervised ML
- A transparent weighted model is explainable to the CTO and auditable
- We can always layer ML on top later once we have more labeled data

---

## Implementation Steps

### 1. Project setup
- Python project, `web3.py`, `supabase-py`
- Supabase project with the three tables above
- Polygon RPC endpoint (Alchemy free tier)

### 2. Indexer — OrderFilled events
- Get CTF Exchange contract address + ABI
- Backfill: query logs in block ranges, parse, upsert into `trades`
- Live: poll every ~15s for new blocks

### 3. Indexer — USDC.e first deposits
- For each unique wallet in `trades`, query USDC.e Transfer logs where `to = wallet`
- Find the earliest one, store in `wallets.first_usdc_deposit_at`

### 4. Market metadata
- Use Polymarket API / subgraph to get resolution times and token-to-market mappings
- Store in `markets` table

### 5. Detection algorithm
- Query Supabase, compute 5 signals per wallet
- Apply weighted formula
- Validate: all 8 known insiders should score in top tier
- Output ranked list as CSV/JSON

### 6. Live detection (stretch)
- Continuous polling loop: index new trades → re-score affected wallets → flag new suspects

---

## Known Insider Wallets (Test Cases)

| Label | Address |
|---|---|
| Google d4vd / alpha raccoon | `0xee50a31c3f5a7c77824b12a941a54388a2827ed6` |
| Maduro out / SBet365 | `0x6baf05d193692bb208d616709e27442c910a94c5` |
| Maduro out / unnamed | `0x31a56e9e690c621ed21de08cb559e9524cdb8ed9` |
| Israel-Iran / ricosuave | `0x0afc7ce56285bde1fbe3a75efaffdfc86d6530b2` |
| Trump pardon CZ / gj1 | `0x7f1329ade2ec162c6f8791dad99125e0dc49801c` |
| MicroStrategy / fromagi | `0x976685b6e867a0400085b1273309e84cd0fc627c` |
| DraftKings / flaccidwillie | `0x55ea982cebff271722419595e0659ef297b48d7c` |

(The Spotify wallet `0xc51...` is noted as "not insider, just smart" — use as a negative example.)

---

## Priority Order

1. **Indexer + Supabase storage** — the foundation, most of the work
2. **Schema + data quality** — clean deduped data, correct timestamps
3. **Scoring model** — simple, explainable, catches the known insiders
4. **Live mode** — last, proves the concept extends to real-time
