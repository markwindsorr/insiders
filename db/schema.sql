
-- Trades from OrderFilled events
CREATE TABLE trades (
    wallet TEXT NOT NULL,
    token_id TEXT NOT NULL,
    side TEXT NOT NULL,
    size NUMERIC NOT NULL,
    tx_hash TEXT NOT NULL PRIMARY KEY,
    block_number BIGINT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_trades_wallet ON trades(wallet);
CREATE INDEX idx_trades_token_id ON trades(token_id);
CREATE INDEX idx_trades_timestamp ON trades(timestamp);

-- Wallet profiles
CREATE TABLE wallets (
    address TEXT PRIMARY KEY,
    first_usdc_deposit_at TIMESTAMPTZ,
    first_trade_at TIMESTAMPTZ,
    total_trades INT DEFAULT 0,
    total_volume NUMERIC DEFAULT 0,
    unique_markets INT DEFAULT 0,
    suspicion_score NUMERIC DEFAULT 0
);

-- Market metadata
CREATE TABLE markets (
    condition_id TEXT PRIMARY KEY,
    question TEXT,
    resolution_time TIMESTAMPTZ,
    token_id_yes TEXT,
    token_id_no TEXT
);

CREATE INDEX idx_markets_resolution ON markets(resolution_time);