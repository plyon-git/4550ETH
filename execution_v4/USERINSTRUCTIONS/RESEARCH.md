# Research and evidence definitions

## Target and periods

The request is checked separately as **200% compound annual growth** and **200% in every measured rolling 365-day window**, with at least 150 complete weeks and 200 closed trades. A multi-year cumulative gain is not described as a yearly return. These are actively closed long/short strategies, not a passive purchase illustrated with hindsight entries.

All accounts start with 10,000 USDT unless labeled as a capacity stress. Development: 2021-01-04 to 2023-01-02. Validation: 2023-01-02 to 2023-09-25. Purge: one week. Evaluation: **2023-10-02 00:00 UTC to 2026-08-31 00:00 UTC exclusive, 152 complete Monday weeks / 1,064 days**. Zero-activity periods remain in the denominator. ETH/BTC entry filters require a completed price of at least 1,000 USDT; XRP has no such floor. Low-price periods are not deleted from account history.

ETH/BTC data begin January 2020; XRP begins February 2020, after unavailable prelisting data. All end September 1, 2026 exclusive. The shared evaluation dates are unchanged. Source receipts, hashes and gap reports identify the inputs.

## Selection and models

Each rule stage enumerates its grid, ranks development candidates, selects parameters on validation and freezes finalists before that stage's evaluation. Breakout, momentum, pullback, reversal, persistent trend and countertrend families are retained, including rejected configurations. Logistic filters and gradient-boosted directional models record rolling training windows and label-maturity cutoffs. Thirteen-week refits use only fully matured forward labels; numerical JSON predictions are checked against the fitted estimator.

Later families and execution sensitivities were added after earlier results became visible. The calendar also overlaps previous 4550 research. **This is not a globally untouched holdout.** Selecting the best test result across markets or candidates adds hindsight selection, even when each market's primary was chosen on validation. No published result establishes the 200% annual target.

The directional training label is next-open to future fixed-horizon close log return normalized by the known current ATR, clipped during training only. It is a forecast target, not an assumed fill or realized target-hit result. Actual reported returns come from the sequential stop/target/cost simulator. The live decision never reads future labels.

## Execution assumptions

The simulation uses trade candles, historical funding and observed marks where available. Completed-bar signals enter no earlier than the next minute. Positions exit through stop, target, opposite signal, timeout, risk circuit, liquidation or final simulation close. There are no equity resets between model refits, martingale sizing or loss clipping.

Base costs: **5 basis points commission and 2 basis points adverse slippage per side**, at most **1% of previous-minute volume**, and **1% fixed maintenance margin**. Recorded quantity/price/minimum-notional grids are modeling assumptions, not verified historical account filters. Volume participation is not an order-book impact or queue-position model. Same-minute ambiguities use the preserved engine's conservative ordering. Loss circuits can be exceeded by gap/slippage effects.

The live adapter queries actual account fees, grids and leverage brackets and reserves collateral beyond the stop. Real spreads, latency, partial fills, outages and margin rules differ from candle assumptions. No authenticated exchange execution was tested here.

## Sourced archive correction and mark gaps

Each original archive contained **74 zero-volume and zero-trade-count minutes on October 28, 2024** while actual aggregate-trade records show trading. Only those rows were reconstructed from published-checksum verified trade ZIPs. Nonzero observed candles were not replaced. The patch ledger records original prices, rebuilt OHLCV/flow and record counts. Original source identities remain separate. This is an archive defect, not evidence of market closure.

Raw mark-price gaps remain null. In the simulation only, missing open/close marks use the previous mark; high/low use separately sourced 15-minute bounds when present, otherwise an explicitly hypothetical +/-5% envelope. These are modeled gap values, not invented observed marks. Each case's `MARK_GAPS.json` records position exposure and modeled values. Liquidation/drawdown during missing marks is not an exact exchange reconstruction. The raw-tape repair does not fix missing marks.

Development/validation end before the October 2024 defect. Frozen rule selection does not change merely because later candles are corrected. Walk-forward fits after that date are rerun on corrected observations. Earlier exploration and data changes remain disclosed.

## Every reported case

`all_trades_UTC.csv`: every winner/loser, direction, quantity, prices, entry/exit fees, funding, P&L, balances, initial stop/target, realized R, reason, entry time and exit bounds. Entries are simulated minute opens; intraminute fills cannot be assigned invented exact seconds. These are not authenticated live fills.

`weekly_returns.csv`: all complete weeks. `daily_equity.csv`: mark-to-market equity. Monthly/yearly CSVs identify partial calendar periods. `rolling_365_day_returns.csv`: actual daily-boundary 365-day windows. `METRICS.json`: total gain, CAGR, geometric weekly return, drawdown, worst week, losing-week streak, WR, profit factor, exposure and separate target gates.

`INDEPENDENT_AUDIT.json` reconstructs trade P&L, costs, funding, cash balances and every minute's open/close equity. It checks signal timing, nonoverlap, quantity grids and volume limits. Agreement establishes checked arithmetic under assumptions, not an edge. Complete minute equity is included for each directional primary; other cases are regenerable from the saved inputs, source and configuration.

## Reproduce

From `execution_v4/`, install pinned dependencies and place the three repaired release datasets under `data/<SYMBOL>/aligned_repaired.npz`, then:

```sh
python -m pytest -q
python -m research.release --data-root data
```

This reruns the full grids, model training, fixed-finalist evaluation and independent audits. It writes `ASSESSMENT.json`, `ALL_EVALUATION_CASES.csv`, models, configurations and manifests. A successful process exit is not a target pass. `--report-only` replays already supplied cases/prediction arrays using identical data without retuning the grid.

The GitHub workflow also checks the data hashes and compares key results with the separate local reproduction. Source, models and every reported trade are in Git; the larger market inputs are preserved as release assets. Research needs no trading credentials. Code/library/data changes require new identities and a fresh verification record.
