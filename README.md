# Polymarket Insider Trading Detection

A Python backend pipeline that indexes Polymarket trades from the Polygon blockchain, stores them in Supabase (Postgres), and scores wallets for insider-like behavior.

We define a likely insider as someone who created a new wallet, deposited large amounts, and traded 1-3 markets close to resolution — markets where the outcome could be influenced by a few people.

---

## Key Concepts

| Concept | What it means |
|---|---|
| **OrderFilled event** | On-chain log from Polymarket's CTF Exchange on Polygon. Every trade emits one: who traded, which market, side, size, when. Our primary data source. |
| **USDC.e Transfer** | ERC-20 Transfer event on the bridged USDC contract. First inbound transfer to a wallet = wallet "birth date". |
| **Market resolution** | When a market's outcome is determined. Insiders trade right before this. |
| **Scoring model** | Weighted sum of 5 behavioral signals per wallet, tuned so known insiders score high. |

---

## Architecture

```
Polygon RPC (Alchemy / QuickNode)
        │
        ▼
  Indexers (Python + web3.py)
    ├── trades.py     ← OrderFilled events (backfill + live)
    ├── wallets.py    ← USDC.e Transfer events (first deposit per wallet)
    └── markets.py    ← Market metadata from Polymarket Gamma API
        │
        ▼
  Supabase (PostgreSQL)
    ├── trades    ← every trade: who, what market, side, size, when
    ├── wallets   ← per-wallet profile: age, volume, trade count
    └── markets   ← market question, resolution time, token IDs
        │
        ▼
  Detection Scorer (Python)
    └── 5 weighted signals per wallet → suspicion score 0-100
        Written back to wallets.suspicion_score in Supabase
```

**Pipeline runs sequentially:** trades → markets → wallets → scorer. Each step depends on the previous one.

### Why Supabase?
- Managed Postgres — no infra to maintain, instant setup
- Built-in REST API + Python client (`supabase-py`) for quick integration
- Easy to add real-time subscriptions later for live alerting
- Not locked in — it's just Postgres underneath, can migrate with `pg_dump`

---

## Project Structure

```
insiders/
├── run.py                    ← Orchestrator: runs full pipeline in order
├── config.py                 ← Loads .env, exports constants + contract addresses
├── requirements.txt
├── blockchains-in-this-context.md
│
├── indexer/
│   ├── trades.py             ← Index OrderFilled events from CTF Exchange
│   ├── wallets.py            ← Build wallet profiles + find first USDC deposits
│   └── markets.py            ← Fetch market metadata from Polymarket Gamma API
│
├── detection/
│   └── scorer.py             ← Score wallets 0-100 for insider suspicion
│
├── db/
│   ├── schema.sql            ← PostgreSQL table definitions
│   ├── supabase_client.py    ← Shared Supabase connection singleton
│   ├── web3_client.py        ← Shared Web3/Polygon RPC connection singleton
│   └── abis.py               ← Smart contract ABIs (OrderFilled, Transfer)
│
└── tests/
    ├── test_connection.py    ← Verify Polygon RPC connection
    ├── test_decode_event.py  ← Test OrderFilled event ABI decoding
    └── test_scorer.py        ← Unit tests for scoring signals
```

---

## Database Schema

Three tables in Supabase (Postgres):

**`trades`** — Individual trades from OrderFilled events

| Column | Type | Notes |
|---|---|---|
| tx_hash | text | PK, for deduplication |
| wallet | text | Trader address |
| token_id | text | Outcome token traded |
| side | text | BUY or SELL |
| size | numeric | Amount in USDC |
| block_number | bigint | |
| timestamp | timestamptz | |

**`wallets`** — Per-wallet profiles for scoring

| Column | Type | Notes |
|---|---|---|
| address | text | PK |
| first_usdc_deposit_at | timestamptz | First inbound USDC.e transfer |
| first_trade_at | timestamptz | Derived from trades |
| total_trades | int | |
| total_volume | numeric | |
| unique_markets | int | |
| suspicion_score | numeric | Set by scorer |

**`markets`** — Market metadata from Polymarket

| Column | Type | Notes |
|---|---|---|
| condition_id | text | PK |
| question | text | Market question |
| resolution_time | timestamptz | When outcome was determined |
| token_id_yes | text | |
| token_id_no | text | |

---

## Scoring Model

Each wallet gets a suspicion score from 0-100 based on 5 signals, each normalized 0-1:

| Signal | Weight | What it measures | Suspicious = |
|---|---|---|---|
| **wallet_age** | 0.25 | Days between first USDC deposit and first trade | Same-day deposit+trade (1.0) |
| **entry_timing** | 0.25 | Days before market resolution when wallet traded | 3 or fewer days before (1.0) |
| **concentration** | 0.25 | Number of unique markets traded | Only 1 market (1.0) |
| **position_size** | 0.15 | Volume relative to average trader | 10x+ average (1.0) |
| **trade_count** | 0.10 | Total number of trades | 1-2 trades only (1.0) |

**Formula:**
```
score = (0.25 * wallet_age + 0.25 * entry_timing + 0.25 * concentration + 0.15 * position_size + 0.10 * trade_count) * 100
```

**Why a weighted model and not ML?** We only have 7 confirmed insider wallets — not enough for supervised learning. A transparent weighted model is explainable and auditable. ML can be layered on top once we have more labeled data.

---

## Known Insider Wallets

Used as ground truth to validate the scoring model:

| Label | Address |
|---|---|
| Google d4vd / alpha raccoon | `0xee50a31c3f5a7c77824b12a941a54388a2827ed6` |
| Maduro out / SBet365 | `0x6baf05d193692bb208d616709e27442c910a94c5` |
| Maduro out / unnamed | `0x31a56e9e690c621ed21de08cb559e9524cdb8ed9` |
| Israel-Iran / ricosuave | `0x0afc7ce56285bde1fbe3a75efaffdfc86d6530b2` |
| Trump pardon CZ / gj1 | `0x7f1329ade2ec162c6f8791dad99125e0dc49801c` |
| MicroStrategy / fromagi | `0x976685b6e867a0400085b1273309e84cd0fc627c` |
| DraftKings / flaccidwillie | `0x55ea982cebff271722419595e0659ef297b48d7c` |

The Spotify scraper wallet (`0xc51...`) is a known **non-insider** used as a negative control.

---

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

Dependencies: `web3>=6.0.0`, `supabase>=2.0.0`, `python-dotenv>=1.0.0`

### 2. Configure environment

Create a `.env` file in the project root:

```
POLYGON_RPC_URL=https://polygon-mainnet.g.alchemy.com/v2/YOUR_KEY
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-service-role-key
```

### 3. Set up database

Run the SQL in `db/schema.sql` against your Supabase project to create the `trades`, `wallets`, and `markets` tables.

---

## Usage

### Run the full pipeline

```bash
python run.py
```

This runs: trades → markets → wallets → scorer (stops if any step fails).

### Run with live monitoring

```bash
python run.py --live
```

Runs the full pipeline first (trades → markets → wallets → scorer), then starts the live trade indexer.

**How live mode works:** The live indexer polls the Polygon RPC for the latest block number every 5 seconds. When new blocks appear, it calls `index_range()` on those blocks to fetch and store any new OrderFilled events. It resumes from the last indexed block automatically, so it's safe to restart.

Note: live mode only indexes new trades. To re-score wallets after new trades come in, re-run `python -m detection.scorer` separately.

### Run individual steps

```bash
python -m indexer.trades                     # Index historical trades (default block range)
python -m indexer.trades 81700000 81800000   # Custom block range
python -m indexer.trades --live              # Start live trade indexer

python -m indexer.markets                    # Fetch market metadata from Gamma API
python -m indexer.wallets                    # Build wallet profiles + find first deposits
python -m detection.scorer                   # Score all wallets
```

### Run tests

```bash
python -m tests.test_connection              # Verify Polygon RPC works
python -m tests.test_decode_event            # Test ABI event decoding
python -m tests.test_scorer                  # Unit tests for scoring signals (no RPC needed)
```

---

## Contract Addresses

| Contract | Address | Purpose |
|---|---|---|
| CTF Exchange | `0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E` | Polymarket's main trading contract on Polygon |
| USDC.e | `0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174` | Bridged USDC stablecoin on Polygon |
