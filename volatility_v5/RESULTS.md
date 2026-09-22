# Volatility V5 results

Owner: Parrish Lyon. Historical simulation; no live orders.

**No tested case meets 65% CAGR plus 200 closed trades.**

3,360 development configurations; 1,104 validation cases; 127 final/stress cases; 42 numerical ML models. These are related experiments, not independent discoveries.

Five calendar years: 2021-09-01 to 2026-09-01 exclusive, 1,826 days. Separate 250 weeks: 2021-11-15 to 2026-08-31, 1,750 days.

## Pre-evaluation selected cases

| Market | Total net | CAGR | Trades | WR | Sep-to-Sep annual returns |
|---|---:|---:|---:|---:|---|
| ETHUSDT | -1.89% | -0.38% | 450 | 38.89% | +20.53%, -6.81%, -6.99%, +25.01%, -24.88% |
| BTCUSDT | -93.46% | -42.05% | 792 | 39.77% | -38.74%, -45.90%, -23.02%, -45.10%, -53.33% |
| XRPUSDT | -14.51% | -3.09% | 371 | 36.93% | +11.14%, -19.98%, +9.29%, -7.47%, -4.94% |
| SPY | -19.59% | -4.27% | 145 | 43.45% | -7.90%, -9.18%, -1.44%, -2.15%, -0.32% |
| QQQ | -17.90% | -3.87% | 168 | 40.48% | -8.09%, -6.09%, -3.25%, -0.35%, -1.34% |

SPY/QQQ are daily-candle diagnostics, not validated ES trades; their selected cases also miss the minimum trade count.

## Best after-cost diagnostic, not the selected primary

BTCUSDT / FINALIST_a16ad2ec145251af_risk0.02: +18.87% cumulative, +3.52% CAGR, 393 trades. Highlighted after seeing results, not a holdout-selected solution.

## Actual IV and methodology

BTC and ETH each have 1,987 continuous daily DVOL observations, 2021-03-24 through 2026-08-31. Use only completed, published IV candles; freeze session bands. RV/range proxies are separately labeled. Rolling prior26-week selection and mature-label ML filters were also evaluated. All trades, levels, available timestamps, models and period returns are retained.

## Fees and the supplied example

3.6 ETH at 2,748.67 equals 9,895.212 notional, or 65.96808 initial margin at150x. Five dollars equals5.05295bps of notional,7.5794% of that margin, but0.05% of a10,000 account. Margin is not account equity. Whether five dollars is one-way or round-trip or includes spread was not verified.

The ETH frozen primary has +6,387.479070 USDT gross price P&L, -6,291.336605 commissions and -285.100389 net funding: -188.957925 net. Gross price P&L already includes fill-price slippage. Its separate no-commission/no-slippage resimulation retains funding and returns+113.16% cumulative /+16.34%CAGR, still below65%. Changing costs changes later sizing/account state; this is not an identical trade path with only a column removed.

## Limits

No proprietary Milk formula, dealer-position archive or exact ES entry sequence was replicated. Missing crypto marks use disclosed sensitivity values rather than invented observed prices. SPY/QQQ daily adverse-ordering assumptions cannot prove intraday fills. No V5 signal was armed for live trading; previous V4 execution and baseline are unchanged. The calendar is previously researched, and later extensions follow earlier results.

Read README.md and docs/METHODOLOGY.md. Every case is in results/, with its specification, trades, timestamps, cost/funding accounting and independent audit.
