# PLM-Spread

A CLI tool for profiling the real cost of trading on Polymarket's order books. Computes depth-weighted spread curves at multiple size levels, monitors them over time, and alerts when liquidity thins abnormally.

No API key or database required, just one dependancy

---

## The problem with top of book spread

Every Polymarket market has a best bid and a best ask. The difference between them is the raw spread.

The problem is that those best levels might only have $50 sitting at them. If you want to trade $500, your order walks through multiple price levels to fill, and your actual average price ends up worse than the top of book implied.

PLM-Spread simulates walking the book. It computes the volume-weighted average price of filling a target dollar amount on both sides, then takes the difference. That is the effective spread, and it is what trading at that size actually costs you.

---

## How it works

For a given target size, the algorithm walks the ask side level by level, consuming each level's dollar value until the target is filled. It does the same on the bid side. The volume-weighted average price on each side gives you the real fill price, and the difference between them is the effective spread at that depth.

Run this across multiple sizes simultaneously and you get a spread curve. A liquid market has a flat curve: trading $500 costs roughly the same as trading $50. A thin market has a steep curve: cheap at small sizes, expensive at large ones because you have to walk deep into the book to fill.

In watch mode, PLM-Spread maintains a rolling window of historical spreads per depth level and computes a running median. When the current spread exceeds a configurable multiple of that median, it fires an alert. The median is used instead of mean specifically because spread distributions are right-skewed, one anomalous poll can distort a mean-based baseline significantly. The median ignores outliers.

---

## Setup

```bash
git clone https://github.com/noxindeed/PLM-Spread
cd PLM-Spread
python -m venv venv
source venv/bin/activate  # windows: venv\Scripts\activate
pip install -r requirements.txt
```

---

## Usage

### Find a market and get its token ID

```bash
python pmspread.py search "fed rate"
python pmspread.py search "bitcoin" --limit 200
```

Searches active markets by keyword, sorted by 24h volume. Each result shows the market question, volume, liquidity, current prices, and both YES and NO token IDs.

The `--limit` flag controls how many markets are fetched before filtering. Default is 50. If your keyword returns nothing, increase the limit.

### One-shot snapshot

```bash
python pmspread.py snapshot --token <id>
python pmspread.py snapshot --token <id> --depth 100,500,1000
```

Fetches the current order book once, prints the top 5 bids and asks, then the spread curve at each depth level. Exits immediately after.

If a depth level shows `thin`, the book does not have enough liquidity to fill that size right now.

### Live monitoring

```bash
python pmspread.py watch --token <id>
python pmspread.py watch --token <id> --interval 10 --depth 50,200,500
python pmspread.py watch --token <id> --alert-threshold 3.0
```

Polls the order book on a fixed interval and prints a fresh spread curve each time. Runs until Ctrl+C.

Once enough history accumulates (minimum 5 polls), it starts comparing each new spread against the rolling median. If the spread exceeds `threshold * median`, an alert fires:

```
liquidity alert:
  [!] $500: spread 0.0251 = 2.3x median (0.0109)
```

---

## Flags

| Flag | Default | Command |
|---|---|---|
| `--limit N` | 50 | search |
| `--token ID` | required | snapshot, watch |
| `--depth SIZES` | 50,200,500 | snapshot, watch |
| `--interval S` | 30 | watch |
| `--alert-threshold X` | 2.0 | watch |

All flags have short aliases: `-l`, `-t`, `-d`, `-i`, `-a`.

---

## What the numbers mean

Polymarket prices live between 0 and 1. A YES price of 0.70 means the market implies 70% probability. Spreads are in the same units: a spread of 0.01 means the round-trip cost of trading is 1 cent per dollar of exposure.

In a deep liquid market, effective spreads at meaningful sizes sit around 0.001 to 0.005. In thin markets or during low-activity periods they can exceed 0.05, meaning 5% of your position value is lost on entry and exit combined.

The bar column color codes this visually: green below 0.02, yellow between 0.02 and 0.05, red above 0.05.

---

## APIs used

- `gamma-api.polymarket.com/markets` for market search and metadata
- `clob.polymarket.com/book` for live order book data

Both are public. No authentication required.

---

by [noxindeed](https://github.com/noxindeed)