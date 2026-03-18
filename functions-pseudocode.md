# Trades Indexer

Here we can either start running the pipeline live or a block range

We'll look at historical first, where we supply a from_block to a to_block range. We can use our own block numbers or default to block on assignment

### index_range

Takes in a from_block number, to_block number and a chunk size defaults to 500.

Index trades across a block range, skips blocks already in the database. Breaks into chunks because RPC nodes limit get_logs calls

1. get last_index:

Here we look up our highest block number that already exists in the trades table in supabase.

If it exists and its created than the beginning range. We print

.....





