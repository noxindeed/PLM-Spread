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
        
def parse_depths(raw):
    try:
        depths = [float(x.strip()) for x in raw.split(",")]
        if any(d <= 0 for d in depths ):
            raise ValueError
        return sorted(depths)
    except ValueError:
        sys.exit("bad --depth value, expected e.g. 50, 200, 500")
        
def cmd_search(args):
    results = search_markets(args.query, args.limit)
    if not results:
        print(f"nothing matched '{args.query}'")
        return
        print(f"\n{BOLD}{len(results)} markets matching '{args.query}'{RESET}\n")
    for i, m in enumerate(results, 1):
        print(f"{BOLD}{i}. {m['question']}{RESET}")
        print(f"   vol24h=${m['vol24h']:,.0f}  liq=${m['liq']:,.0f}")
        for outcome, tid, price in zip(m["outcomes"], m["token_ids"], m["prices"]):
            p = f"{float(price):.3f}" if price else "n/a"
            print(f"   {CYAN}{outcome}{RESET}  {p}  {YELLOW}{tid}{RESET}")
        print()
    print(f"{DIM}pmspread snapshot --token <id>  or  pmspread watch --token <id>{RESET}\n")

def cmd_snapshot(args):
    depths = parse_depths(args.depths)
    book = fetch_book(args.token)
    curve = spread_curve(book, depths)
    bids = book.get("bids",[])
    asks = book.get("asks",[])
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    
    print(f"\n{BOLD}snapshot{RESET}  {CYAN}{args.token[:24]}...{RESET}  {DIM}{ts}{RESET}")
    print(f"  {len(bids)} bid levels  {len(asks)} ask levels\n")

    print(f"{BOLD}top bids{RESET}")
    for o in sorted(bids, key=lambda x: -float(x["price"]))[:5]:
        print(f"  {float(o['price']):.4f}  x  ${float(o['size']):.2f}")

    print(f"\n{BOLD}top asks{RESET}")
    for o in sorted(asks, key=lambda x: float(x["price"]))[:5]:
        print(f"  {float(o['price']):.4f}  x  ${float(o['size']):.2f}")

    print_curve(curve, depths, "spread curve")
    
def cmd_watch(args):
    depths = parse_depths(args.depth)
    mon = Monitor(depths, threshold=args.threshold)
    n = 0

    def on_sigint(sig, frame):
        print(f"\n{DIM}stopped after {n} polls{RESET}\n")
        sys.exit(0)

    signal.signal(signal.SIGINT, on_sigint)
    print(f"{BOLD}pmspread watch{RESET}  {CYAN}{args.token}{RESET}")
    print(f"interval={args.interval}s  depths={depths}  alert={args.threshold}x\n")

    while True:
        try:
            book = fetch_book(args.token)
            curve = spread_curve(book, depths)
            alerts = mon.update(curve)
            print_curve(curve, depths, datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"))
            if alerts:
                for a in alerts:
                    print(f"{RED}{BOLD}Liquidity alert:{RESET}")
                    for a in alerts:
                        print(f"{RED}  {a}{RESET}")
            n += 1
            time.sleep(args.interval)
        except Exception as e:
            print(f"{RED}http {e}{RESET}", file=sys.stderr)
            time.sleep(args.interval)
        except requests.ConnectionError:
            print(f"{RED}connection lost, retrying in {args.interval}s{RESET}", file=sys.stderr)
            time.sleep(args.interval)
        except Exception as e:
            print(f"{RED}{e}{RESET}", file=sys.stderr)
            raise

def main():
    p = argparse.ArgumentParser(prog="plmspread")
    sub = p.add_subparsers(dest="cmd", required=True)
    
    s = sub.add_parser("search", help="find markets + token IDs")
    s.add_argument("query")
    s.add_argument("--limit", "-l",type=int, default=50, metavar="N", help="max results to return")
    
    sn = sub.add_parser("snapshot", help="fetch order book and spread curve for a token")
    sn.add_argument("--token", "-t", required=True,metavar="ID", help="token ID to fetch")
    sn.add_argument("--depths", "-d", default="50,200,500", metavar="SIZES", help="comma separated list of depth levels to compute spread at")
    
    w = sub.add_parser("watch", help="live polling with alerts")
    w.add_argument("--token", "-t", required=True, metavar="ID")
    w.add_argument("--depth", "-d", default="50,200,500", metavar="SIZES")
    w.add_argument("--interval", "-i", type=int, default=30, metavar="S")
    w.add_argument("--alert-threshold", "-a", type=float, default=2.0,dest="threshold", metavar="X")
    
    args = p.parse_args()

    try:
        {"search": cmd_search, "snapshot": cmd_snapshot, "watch": cmd_watch}[args.cmd](args)
    except requests.HTTPError as e:
        code = e.response.status_code if e.response is not None else "?"
        if code == 404:
            sys.exit("token not found - run 'pmspread search <query>' first")
        sys.exit(f"http error {code}: {e}")
    except requests.ConnectionError:
        sys.exit("can't reach polymarket - check connection")


if __name__ == "__main__":
    main()

            