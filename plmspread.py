import argparse
import sys
import json
import time
import signal 
from datetime import datetime,timezone
import requests 

CLOB = "https://clob.polymarket.com"
GAMMA = "https://gamma-api.polymarket.com"

#fetching order books for a token
def fetch_book(token_id):
    r = requests.get(f"{CLOB}/book", params={"token_id": token_id}, timeout=10)
    r.raise_for_status()
    return r.json()

#searching for markets (top 50)
def search_markets(query, limit=50):
    r = requests.get(f"{GAMMA}/markets", params={"active":"true", "closed":"false","limit":limit,"order": "volume24hr", "ascending": "false"},timeout=10)
    r.raise_for_status()
    
    q = query.lower()
    out =[]
    for m in r.json():
        question = m.get("question", "")
        if q not in question.lower():
            continue
        
        def parse(field, fallback):
            v = m.get(field,fallback)
            try:
                return json.loads(v) if isinstance(v, str) else v
            except (json.JSONDecodeError, TypeError):
                return []
            
        out.append({
            "question":  question,
            "token_ids": parse("clobTokenIds", "[]"),
            "outcomes":  parse("outcomes", '["YES","NO"]'),
            "prices":    parse("outcomePrices", "[0,0]"),
            "vol24h":    float(m.get("volume24hr") or 0),
            "liq":       float(m.get("liquidityNum") or 0),
            })
    return out

)