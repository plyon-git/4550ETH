# V8: daily/weekly IV, overnight carry, 72h, 5R, 30x

Owner: Parrish Lyon. Hypothetical historical executions, not authenticated live fills.

**No base-cost case established CAGR above 45%. Some arithmetic averages exceed 45% because one strong year offsets several losing years.**

## Matched ETH holding-limit comparison

Same fixed 5R target, threshold 0.5, 4% planned risk, 5x account exposure cap and 30x nominal contract setting with a collateral reserve. Models and entry candidates are unchanged; account paths are rerun. This is a hindsight-highlighted diagnostic, not the predeclared primary.

| Hold | Five-year net | CAGR | Mean annual return | Trades | Drawdown bound |
|---|---:|---:|---:|---:|---:|
| 24h | +86.85% | +13.32% | +35.30% | 389 | 53.87% |
| 48h | +70.75% | +11.30% | +41.14% | 373 | 60.68% |
| 72h | +146.25% | +19.75% | +55.83% | 363 | 57.87% |

## Five annual periods

| Period | Net return |
|---|---:|
| Sep 2021 to Aug 2022 | +310.34% |
| Sep 2022 to Aug 2023 | -16.74% |
| Sep 2023 to Aug 2024 | -40.03% |
| Sep 2024 to Aug 2025 | +39.26% |
| Sep 2025 to Aug 2026 | -13.69% |

Arithmetic mean +55.83% is not CAGR +19.75%. Three years lose. Net WR 23.69%; worst week -14.82%; longest losing streak 7 weeks. 150 of 363 trades cross midnight. This falls short of the earlier 1000-trade requirement.

## Selected primaries

| Study | Market | CAGR | Five-year net | Trades |
|---|---|---:|---:|---:|
| Validation-selected fixed primary | BTCUSDT | +1.57% | +8.10% | 201 |
| Validation-selected fixed primary | ETHUSDT | -0.17% | -0.83% | 243 |
| Walk-forward primary | BTCUSDT | -7.86% | -33.59% | 586 |
| Walk-forward primary | ETHUSDT | -6.45% | -28.35% | 681 |

Subsequent ETH sizing raised the highest after-cost CAGR to +29.32%, with mean annual +78.22%, 361 trades and 64.09% drawdown. It uses 6% planned risk and a 30x account cap; actual peak exposure is 10.070x. Only 2 years are positive. Not a validated or selected primary.

## Fragility checks on ETH 4%-risk diagnostic

| Scenario | CAGR | Five-year net | Modeled liquidations |
|---|---:|---:|---:|
| 30x_no_extra_collateral | +11.06% | +68.94% | 38 |
| zero_cost | +55.09% | +796.95% | 0 |
| double_cost | -1.78% | -8.58% | 0 |
| delay2m | -4.75% | -21.58% | 0 |

Base costs: 5bps commission and 2bps adverse slippage per side, funding, grids and 1% prior-minute volume cap. Zero cost retains funding and grids. Two additional minutes of entry delay make the highlighted case negative. No robust live edge is established.

## Method and verification

Daily ranges freeze after previous daily DVOL close plus a modeled one-minute publication allowance. Weekly ranges freeze Monday after 00:01 using the preceding Sunday close and known IV. Use sqrt(1/365) and sqrt(7/365) scaling. These are model range estimates, not dealer gamma walls or separate 1D/7D-tenor options histories.

Rejection, break and recent-bar retest signals use completed 15m/1h bars and next-minute entries. Stops are known before entry; targets are five times initial price risk and do not repaint. Maximum hold is 72 hours from entry, not midnight. No averaging down or pyramiding.

Development Sep2021-Aug2022 and validation Sep2022-Aug28 2023 precede a purged three-year test. Full five-year diagnostics include those selection years. ML refits every 13 weeks using at most 730 prior days of fully matured candidate labels. Labels overlap. Prior project exposure and subsequent extensions are disclosed.

Initial margin is notional/30. Additional isolated collateral is reserved when needed for the planned stop plus maintenance/funding/buffer. That is a model allocation, not a claim the exchange automatically adds margin. Exact account brackets and margin/latency must be verified separately.

All 100 case audits passed. 42 saved models have mature training labels. Every trade, daily equity and annual/monthly/weekly/rolling-year result is retained. Independent checks reconstruct cash, margin quantities and daily equity, and reject missed earlier stop/target crossings. Intraminute timestamps are bounds; mark gaps use disclosed sensitivity values, not invented observations.

The original 45.50% program and V4 live service remain unchanged. V8 is not armed for live orders. Read USERINSTRUCTIONS.md and ASSESSMENT.json.
