# Daily IV walls: one trade per UTC day, V7

Project-specific source, research and reporting: **Parrish Lyon**. Third-party data and library rights remain applicable.

This is a new daily-horizon backtest on BTCUSDT and ETHUSDT. It is not the earlier five-session QQQWave proxy. Each scheduled strategy attempts one entry per UTC calendar day, including weekends, and closes no later than 23:59 UTC that day. Stop/target exits do not permit a second entry. Each market has its own 10,000-USDT account; trade counts are not pooled.

See RESULTS.md, ASSESSMENT.json, and each case's EVERY_TRADE_UTC.csv, EVERY_DAY.csv, PARAMETERS.json and AUDIT.json. The return target is separate from the trade-count target. A test can satisfy 1,000 trades and fail economically.

## Actual IV and daily walls

The source is historical Deribit BTC/ETH DVOL, with archived API JSON and receipts. CSV values are independently reconstructed from the API pages. DVOL is a 30-day forward annualized implied-volatility index measured daily, not a one-day-expiry option chain. It is not realized volatility renamed IV.

At UTC day D:

```
reference = last trade close of D-1
IV = completed D-1 DVOL close
modeled IV availability = D 00:01 UTC
one_day_sigma = IV / 100 / sqrt(365)
upper = reference * exp(upper_multiple * one_day_sigma)
lower = reference * exp(-lower_multiple * one_day_sigma)
```

Scheduled entries occur at 00:02 UTC or, in separately labeled diagnostics, 08:02 UTC. The scheduled primary is chosen before its five-year evaluation. No entry uses D's eventual IV close, high, low or final daily return. Historical-mean walls scale daily sigma by the mean of up to200 prior completed one-day excursions normalized by each day's then-available IV, with at least30 samples. Counts are exported rather than falsely called200 on early days. Another model averages five completed daily IV observations: this is IV smoothing, not a five-day forecast or holding period.

IV supplies a range, not a directional forecast by itself. Scheduled policies separately specify direction from completed returns, IV changes, conditional historical returns or opening movement observed before entry. Long-only and short-only daily round-trip controls are labeled. No unconditional directional edge is presumed.

A separate wall-only test waits for the first completed five-minute rejection/continuation at the frozen daily IV boundary, enters on the following minute, and never reenters. Missing setups are skipped and reported, not invented trades. These are at most one/day, not necessarily exactly one/day.

Neither class reconstructs dealer gamma, strike open interest, proprietary Milk walls or QQQWave MinAvg.

## Periods and selection

Five calendar years: 2021-09-01 to2026-09-01 exclusive, 1,826 days. Separate250 weeks: 2021-11-15 to2026-08-31 exclusive, 1,750 days. They are not equivalent durations.

Development: 2021-05-01 to2021-07-01. Validation: 2021-07-01 to2021-08-25, followed by a purge. Each rule/wall-model's development finalists are risk-tested on validation. The scheduled primary requires00:02 entries and at least90% of validation days traded, maximizing validation log growth minus half daily-equity drawdown. All grids and frozen choices are saved. These pretest windows are short because of actual IV availability. The calendar was already researched: this is not an untouched holdout.

After fixed-run review, an explicitly labeled adaptive extension selects one scheduled policy every seven days from up to126 prior fully matured daily returns, minimum90 initially. The selected account never resets. Independent simulated bank accounts supply lagged ranking statistics, not pooled returns. Exact choices and daily actions are retained. This extension also uses the already-researched calendar.

## Execution and costs

Every position closes by the same day's23:59 open. Frozen absolute stops/targets, completed-bar signals, next-minute entries, gap-through-level skips and stop-first ambiguous-candle handling are enforced. A later target touch cannot repair a stopped loss.

Base assumptions:5bps commission and2bps adverse slippage per side;1% of previous-minute volume maximum; asset-specific quantity/price grids and minimum notional; historical funding; fixed1% maintenance. These are not verified historical account tiers or an order-book/queue-impact model. Account exposure is capped at5x, independent of nominal contract leverage. No150x return multiplier, martingale, duplicate entries, overnight carry or loss clipping. There is no weekly stop circuit in this experiment; daily trade stops and risk sizing do not guarantee a weekly loss cap.

The5-USDT stress interprets the earlier3.6 ETH at2,748.67 example as proportional round-trip commission, not a flat fee at every size. Zero-cost, doubled-cost and entry-delay tests resimulate the compounded account. Zero commission/slippage retains funding and price-grid rounding.

Raw missing marks remain in the source. The simulation uses prior mark close and sourced15-minute bounds where available, otherwise an explicit+/-5% sensitivity envelope. Exposure is flagged per trade. Intrabar drawdown is a conservative bound, not exact tick ordering; daily close-to-close drawdown is separately reported.

## Methodology sources

Official DVOL definition and sqrt(365) conversion:
https://insights.deribit.com/exchange-updates/dvol-deribit-implied-volatility-index/

Official exponential expected-move band calculation:
https://insights.deribit.com/education/expected-move-calculations-and-visual/

These sources define concepts, not this strategy's performance. Results come only from the committed inputs, assumptions and simulations.

## Existing programs unchanged

V7 is offline research. It does not submit orders or change/arm V4. Original45.50%, V4, V5 and V6 artifacts remain unchanged. See USERINSTRUCTIONS.md for reproduction; no profitable live deployment is claimed.
