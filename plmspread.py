import argparse
import sys
import json
import time
import signal 
from datetime import datetime,timezone
import requests 

CLOB = "https://clob.polymarket.com"
GAMMA = "https://gamma-api.polymarket.com"

def fetch_book(token_id):
    r = requests.get(f"{CLOB}/book", params={"token_id": token_id}, timeout=10)
    r.raise_for_status()
    return r.json()
