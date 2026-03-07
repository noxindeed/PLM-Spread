import argparse
import sys
import json
import time
import signal 
from datetime import datetime,timezone
import requests 
from collections import deque

CLOB = "https://clob.polymarket.com"
GAMMA = "https://gamma-api.polymarket.com"

RESET  = "\033[0m"
BOLD   = "\033[1m"
RED    = "\033[91m"
YELLOW = "\033[93m"
GREEN  = "\033[92m"
CYAN   = "\033[96m"
DIM    = "\033[2m"

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
        "raw": ba - bb if bb and ba else None,
        "bid": bb,
        "ask" : ba,
        
        }
def spread_curve(book, depths):
    return {d: spread_at(book, d) for d in depths}

#anamoly detection to catch liquidity shocks 
class Monitor:
    def __init__(self,depths, window=20,threshold=2.0):
        self.threshold = threshold
        self.hist={d: deque(maxlen=window) for d in depths}
        
    def update(self,curve):
        alerts=[]
        for size, r in curve.items():
            if r is None:
                continue 
            s = r["eff"]
            h = self.hist[size]
            if h is None:
                continue
            if len(h)>=5:
                med = sorted(h)[len(h)//2]
                if med >0 and s>self.threshold*med:
                    alerts.append(
                        f"  [!] ${size:.0f}: spread {s:.4f} = {s/med:.1f}x median ({med:.4f})"
                        )
            h.append(s)
        return alerts    
                    

#bar func for display and also the table printer
def bar(spread, cap=0.10, w=20):
    n = int(min(spread/cap,1.0)*w)
    col = GREEN if spread <0.02 else YELLOW if spread <0.05 else RED
    return col + "█"*n + DIM + "░"*(w-n)+RESET

def print_curve(curve, depths , ts):
    print(f"\n{BOLD}{CYAN}{ts}{RESET}")
    print(f"  {'Depth':>8}  {'Bid':>8}  {'Ask':>8}  {'Eff Spread':>11}  {'Raw':>8}  Bar")
    print("  " + "-" * 64)
    for d in depths:
        r = curve.get(d)
        if r is None:
            print(f"  {d:>8.0f}  {'--':>8}  {'--':>8}  {'thin':>11}")
            continue
        print(
            f"  {d:>8.0f}  {r['bid']:>8.4f}  {r['ask']:>8.4f}"
            f"  {r['eff']:>11.4f}  {r['raw'] or 0:>8.4f}  {bar(r['eff'])}"
        )
        
