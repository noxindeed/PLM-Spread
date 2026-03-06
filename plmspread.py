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
'''
sidenote: the search filter is a simple substring match so it may return some false negatives
if anyone is reading this, i reccommend using a more specific OR a direct copy pasted query
to avoid such errors. also, the search is case insensitive so you can use any case you want.
'''
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

#compute volume weighted average price of filling
def weighted_fill(levels,target):
    if target <= 0:
        return None
    rem = target 
    cost = shares = 0.0
    for price,size in levels:
        c = price * size
        if c >=rem:
            shares += rem/price
            cost += rem
            rem = 0
            break
        cost += c
        shares += size
        rem -= c
    if rem > 0 or shares ==0:
        return None
    return cost/shares

def spread_at(book,size):
    bids = sorted([(float(o["price"]),float(o["size"])) for o in book.get("bids",[])], reverse=True)
    asks = sorted([(float(o["price"]),float(o["size"])) for o in book.get("asks",[])])

    wa = weighted_fill(asks,size)
    wb = weighted_fill(bids,size)
    if wa is None or wb is None:
        return None 
    
    bb = bids[0][0] if bids else None
    ba = asks[0][0] if asks else None
    
    return {
        "avg_ask": wa,
        "avg_bid": wb,
        "eff": wa-wb,
        "raw": (bb,ba) if bb and ba else None,
        "bid": bb,
        "ask" : aa,
        
        }