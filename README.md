# Fireplace.gg Technical

## Insider Trading Detection

We can categorize a 'likely' insider by someone that created a new wallet, suddenly dropped large amounts of money 1-3 related markets close to the markets ending. The market was able to be manipulated (as in a single or few people can influence the outocme of the event).

Some parameters given on the sheet is

- Entry timing
- Traded very few markets
- Minimum Size
- Time between wallet creation and first trade
- Trade concentration

### Our Goal 

To build a system that can classify insider trades on Polymarket historically and in real time. 

### Deliverables

1. System Architecture

2. Code

- Indexing historical and live trades from polymarket via the `OrderFilled` event
- Indexing first USDC.e deposit transactions for wallets on Polymarket
- Storing trades (and other required information) on some database that can be used for the insider detection algorithm
- Algorimth to detect insider trades and optimal parameters and weights for each factor in the model.

---