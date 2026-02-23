'''
Config File

Loads our .env files and defines the contract addresses we'll be talking to.

Contract Addresses:

- CTF Exchange: This is polymarket's main trading contract on Polygon. "CTF" stands for
Conditional Token Framework. Every trade on Polymarket goes through this contract and
every trade emits an OrderFilled event. This is the address we'll be watching

- USDC.e: This is the bridged USDC stablecoin on Polygon. When someon funds their Polymarket
wallet, USDC.e gets transferred to their address. We look at the Transfer events on
this contract to find when a wallet was first funded
'''

import os
from dotenv import load_dotenv

load_dotenv()

# Secrets
POLYGON_RPC_URL = os.getenv("POLYGON_RPC_URL")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Contract Addresses (these are fixed, public, on chain facts)
CTF_EXCHANGE_ADDRESS = "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E"
USDC_E_ADDRESS = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
