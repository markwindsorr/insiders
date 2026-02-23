from web3 import Web3
from config import POLYGON_RPC_URL
import requests

session = requests.Session()
session.trust_env = False  # bypass system proxy settings

web_three = Web3(Web3.HTTPProvider(POLYGON_RPC_URL, session=session))

print(f"Connected: {web_three.is_connected()}")
print(f"Latest block: {web_three.eth.block_number}")

# Fetch the sample transaction from the assignment
sample_tx = "0x6599fcc58912b6ea1f3fbed5a801b28399097edfac3216fbf3cbbc9763837273"
receipt = web_three.eth.get_transaction_receipt(sample_tx)


print(f"Transaction block: {receipt['blockNumber']}")
print(f"Number of logs: {len(receipt['logs'])}")

# Print the raw logs, these are the events emitted by the contract
for i, log in enumerate(receipt["logs"]):
    print(f"\nLog {i}:")
    print(f"  Contract: {log['address']}")
    print(f"  Topics: {[t.hex() for t in log['topics']]}")