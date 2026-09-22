# QQQWave-inspired V6: visible parameters and five-year evidence

Owner: Parrish Lyon. This is new empirical-range research, not proprietary QQQWave replication or a live trading recommendation.

**The high-touch forecasting structure is reproducible. No tested strategy reaches 65% CAGR or a 65% arithmetic mean annual return with 200 trades.**

## What the screenshot establishes

QQQ, one-day aggregation, 200 daily aggregations, five forward aggregations, Weekday Matching selected and HL Matching unselected. Reference 721.45001; MinAvg 715.69, 0.7983935% below reference. The displayed 97.37% does not establish profitable trades without the event, denominator, stop and payoff definitions.

All 25 visible count rows match `max(1%,100*(count-1)/(76-2))` to displayed precision. For example 24/76 is 31.5789%, but `(24-1)/74` is the shown 31.08%. This is a numerical fit, not documented vendor source. The tooltip may use a different calculation; 74/76 happens to round to 97.37%, but its denominator is not shown.

The IV column is present but empty in the screenshot. We cannot tell from that whether option IV drives the graph. Historical excursion distributions, option-derived IV and strike-position walls are separately identified, not conflated.

## New model

At each origin use the previous close and only 200 prior observed sessions. A historical five-session sample is eligible only after all five sessions finish. Match origin weekdays when selected. Calculate historical maximum highs, minimum lows and terminal returns relative to that sample's reference; normalize by its known RV20 and rescale using current known RV20. Test raw-percent and actual-DVOL-scaled variants separately.

The `mean_low_proxy` is an arithmetic mean of projected lows, not the vendor's unknown MinAvg. A separate 97.3684th-percentile low target tests the high-touch hypothesis. Under the specified weekday rule this uses 28 crypto samples or approximately 39-40 equity samples, not an invented 76.

## Five-session event results

| Market | Forecast origins | Lower-level touch | Terminal below level | Already at/below at origin open | Touch when target actually below open |
|---|---:|---:|---:|---:|---:|
| ETHUSDT | 1822 | 93.91% | 46.32% | 0 | 93.91% |
| BTCUSDT | 1822 | 93.74% | 45.06% | 0 | 93.74% |
| XRPUSDT | 1822 | 94.73% | 47.69% | 0 | 94.73% |
| QQQ | 1250 | 95.52% | 50.88% | 922 | 82.93% |
| SPY | 1250 | 95.60% | 50.48% | 910 | 83.82% |

These are forecast-event denominators, not executed trades. The QQQ lower level is touched in 95.52% of windows, but 922/1,250 already open at or below it; only 328 are valid lower short targets. Among those 328, 272 touch, or 82.93%. Its unconditional terminal-below frequency is 50.88%. The fixed screenshot percentage offset, a different diagnostic, is touched in 69.76% of QQQ windows, not a test of unknown vendor conditioning.

## Fixed high-touch trade test: same 200/5/weekday/realized parameters

Short after the first completed five-minute bar only when the fixed low target remains below the executable entry; use the projected upper-90th-percentile stop. Exit at stop, target, risk circuit or fixed five-day forecast deadline. One open position per account, 1% planned account risk, up to 5x exposure, previous-volume and order-grid limits. An eventual touch after a stop does not restore the losing trade.

| Market | Trades | Net win rate | Five-year net | CAGR | Mean of five annual returns |
|---|---:|---:|---:|---:|---:|
| ETHUSDT | 1250 | 84.96% | -11.81% | -2.48% | -2.45% |
| BTCUSDT | 1278 | 79.26% | -21.03% | -4.61% | -4.59% |
| XRPUSDT | 1275 | 88.24% | +7.56% | +1.47% | +1.51% |

ETH averaged a 3.76 USDT net winner versus 27.53 USDT net loser. At those observed payoffs the break-even win rate is 87.98%, above the actual 84.96%. 1166 trades exited at target, but 104 of those still lost after the modeled fill/cost/funding arithmetic. This is why a high event hit rate alone is insufficient.

## Validation-selected primaries

| Market | Five-year net | CAGR | Trades | Net WR | Worst week | Longest losing-week streak | Five annual returns |
|---|---:|---:|---:|---:|---:|---:|---|
| ETHUSDT | -22.72% | -5.02% | 1250 | 84.96% | -3.83% | 5 | +2.93%, -7.85%, -12.31%, -3.77%, -3.44% |
| BTCUSDT | -45.13% | -11.31% | 978 | 38.75% | -4.98% | 10 | -21.73%, -17.36%, +22.22%, -3.44%, -28.12% |
| XRPUSDT | -7.57% | -1.56% | 1376 | 66.64% | -0.90% | 5 | -0.83%, -1.96%, -1.99%, -0.18%, -2.83% |

These primaries use different validation-selected families and risk settings; they are not the fixed 1% screenshot tests above. The five calendar years are 2021-09-01 through 2026-09-01 exclusive, 1,826 days. A separate 250-week account run spans 2021-11-15 through 2026-08-31. These durations are not equivalent.

## Execution-cost check, using the supplied example

3.6 ETH at 2,748.67 equals 9,895.212 USDT notional. Initial margin at 150x is 65.96808 USDT. Five dollars is 5.05295 basis points of notional, 7.5794% of initial margin, or 0.05% of a 10,000-USDT account. Which denominator matters depends on the question. The screenshot/user example does not verify whether $5 is one-way, round-trip or includes slippage.

| ETH selected primary scenario | Five-year net | CAGR | Net WR |
|---|---:|---:|---:|
| no_fee_no_slippage | +5.40% | +1.06% | 93.28% |
| user5usd_round_trip | -13.88% | -2.94% | 89.52% |
| user5usd_one_way | -22.90% | -5.07% | 84.88% |
| double_cost | -42.50% | -10.48% | 69.75% |

The two $5 scenarios preserve 2bps adverse slippage per side and translate $5 at the quoted notional into a proportional fee; they do not charge a flat $5 on every differently sized trade. Zero-fee/zero-slippage retains historical funding and price-grid rounding. All scenarios rerun the sequential account; they are not a post-hoc fee-column subtraction.

## Audit and scope

1088 development configurations; 192 validation settings; 22 finalists/fixed diagnostics; 18 stresses; 3 separate 250-week runs. All 43 trade/equity audits passed. Across separate simulations there are 44,923 exported trade rows. These are related experiments, not independent discoveries or one combined portfolio.

Every case retains timestamped trades, absolute initial levels and expiry, fees/funding, daily equity, weekly/monthly/rolling-year returns, source configuration and independent reconciliation. Minute-equity series can be regenerated; the default export is daily equity plus full trade records. QQQ/SPY results are event-only daily diagnostics, not five-minute ES executions. No broker calls or live V6 orders were made.

Actual BTC/ETH DVOL is options-derived; our IV variant uses it to scale historical excursions and is explicitly a hybrid. Historical RV is not renamed IV. Raw option strikes, OI, dealer inventory and the proprietary Milk/QQQWave formula were not supplied or replicated. Prior periods were researched before; this is not a globally untouched holdout.

## Source definitions

Deribit DVOL methodology: https://insights.deribit.com/exchange-updates/dvol-deribit-implied-volatility-index/

CME option position/volume concentrations by strike and expiry: https://www.cmegroup.com/education/courses/tools-for-option-analysis/cmed-qs-open-interest-heatmap

Visible parameters come from the user-supplied image. See SCREENSHOT_ANALYSIS.json for exact transcribed rows, arithmetic and unknowns. See docs/USERINSTRUCTIONS.md for portable snapshots and reproductions.
