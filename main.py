#!/usr/bin/env python3
"""btc-cent-forecast-01: forecast BTC's USD price 240 minutes ahead.

Approach (chosen on out-of-sample evidence, not on the 6 practice cases):
  forecast = 0.70 * median(last 3 closes) + 0.30 * EWMA60(last 1440 closes)

Why:
  - BTC 4h ahead is near-unpredictable, so the honest baseline is the last
    price (persistence). Any edge must be small, real and robust.
  - The median of the last 3 closes kills microstructure noise and the
    occasional one-minute spike of the single Orca pool this price comes
    from, without lagging the way a longer median does.
  - A 60-minute-halflife EWMA over the last 24h pulls the guess slightly
    toward where the price has actually been trading recently; a 0.30 weight
    is small enough that a hard trend does not drag the guess far from the
    last price.
  - Mean reversion toward 12h/24h/72h averages and trend extrapolation were
    tested and rejected: they help in one regime and lose badly in another
    (e.g. 24h mean reversion w=0.3: -9% in the Nov 7-11 window but +9% over
    the full 3-week window). Drift extrapolation lost in every window.

Validation (Binance BTC/USDT 1-minute closes, 2026-10-20..2026-11-11,
115 checkpoints 4h apart, forecast from the 4320 closes before each
checkpoint, scored against the close 240 min later):
  - persistence MAE:  40974.23 cents
  - this model MAE:   39558.63 cents  (-3.45% vs persistence),
    consistent in both halves of the window
    (1st half -3.39%, 2nd half -3.50%) and in the most recent window
    (Nov 7-11: -6.22%).
  - On the 6 sealed practice cases the model scores worse than persistence
    (6 cases are far too few to distinguish forecasters; the 115-checkpoint
    evidence above is what the choice rests on).

Deterministic: pure arithmetic on the input, no randomness, no time, no
network. Two runs on the same case write byte-identical output. Fast: a
single pass over 4320 prices, well under the 8-second cap.

Input:  $MAKEFUN_INPUT_DIR (else /input)  holding <id>.in case files.
Output: $MAKEFUN_OUTPUT_DIR (else /output) holding <id>.out files, one
        {"forecasts": [{"case": <id>, "price": <number>}]} per case.
"""

import json
import os
import statistics
import sys

INPUT_DIR = os.environ.get("MAKEFUN_INPUT_DIR", "/input")
OUTPUT_DIR = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")

MIN_PRICE = 0.00001
MAX_PRICE = 9_999_999.99999

# Tuned on 115 out-of-sample checkpoints (see module docstring / README):
EWMA_HALFLIFE_MIN = 60.0   # halflife of the EWMA, in minutes
EWMA_WINDOW_MIN = 1440     # EWMA is computed over the last 24h of closes
MEDIAN_WINDOW = 3          # median of the last 3 closes
EWMA_WEIGHT = 0.30         # weight on the EWMA; 0.70 on the recent median


def ewma(prices, halflife):
    """Exponentially weighted moving average, oldest to newest."""
    alpha = 1.0 - 0.5 ** (1.0 / halflife)
    value = prices[0]
    for price in prices[1:]:
        value = alpha * price + (1.0 - alpha) * value
    return value


def forecast(prices):
    """One price guess for the close 240 minutes after the last close."""
    if not prices:
        raise ValueError("empty price series")
    recent = prices[-MEDIAN_WINDOW:]
    base = statistics.median(recent)
    window = prices[-EWMA_WINDOW_MIN:]
    trend_level = ewma(window, EWMA_HALFLIFE_MIN)
    guess = (1.0 - EWMA_WEIGHT) * base + EWMA_WEIGHT * trend_level
    if guess != guess or guess in (float("inf"), float("-inf")):
        raise ValueError("non-finite forecast")
    # Keep the guess on the price grid (5 decimals) and inside the scorer's
    # (0, 10_000_000) bounds.
    guess = min(MAX_PRICE, max(MIN_PRICE, guess))
    return round(guess, 5)


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    names = sorted(f for f in os.listdir(INPUT_DIR) if f.endswith(".in"))
    if not names:
        print("no .in case files found in %s" % INPUT_DIR, file=sys.stderr)
        return 1
    for name in names:
        case_id = name[: -len(".in")]
        with open(os.path.join(INPUT_DIR, name), "r", encoding="utf-8") as fh:
            case = json.load(fh)
        markets = case.get("markets")
        if not isinstance(markets, list) or len(markets) != 1:
            raise ValueError("%s does not hold exactly one market" % name)
        prices = markets[0].get("prices")
        if not isinstance(prices, list) or not prices:
            raise ValueError("%s has no prices" % name)
        out = {"forecasts": [{"case": case_id, "price": forecast(prices)}]}
        with open(
            os.path.join(OUTPUT_DIR, case_id + ".out"), "w", encoding="utf-8"
        ) as fh:
            fh.write(json.dumps(out) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
