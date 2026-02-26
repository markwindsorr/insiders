"""
Shared Web3 client for connecting to Polygon.

All modules that need blockchain access import w3 from here
instead of each creating their own connection.
"""

from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
from config import POLYGON_RPC_URL
import requests

session = requests.Session()
session.trust_env = False

w3 = Web3(Web3.HTTPProvider(POLYGON_RPC_URL, session=session))
w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)  # required for Polygon (POA chain)