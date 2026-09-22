# V8 interrupted-run recovery and 72-hour follow-up

Owner: Parrish Lyon. Original source commit: `4ff2d40b51ce152d34175318a9d1c30184509a60`. No live orders.

**72 hours improves the highlighted ETH account, but the result is not a consistent 45% compound-return system.** The original 4%-risk diagnostic averages +55.83% across five annual periods while compounding at +19.75%. These are different measures.

The full five-year window is 2021-09-01 to 2026-09-01 exclusive. Each account starts at 10,000 USDT. All entry candidates/model weights are fixed from the original V8 run; changing the holding limit does not retrain the 72-hour-label models. This is a matched execution sensitivity, not a new validation exercise.

## Holding-limit comparison

| Hold | Five-year net | CAGR | Mean of five annual returns | Trades | Drawdown bound |
|---|---:|---:|---:|---:|---:|
| 24h | +86.85% | +13.32% | +35.30% | 389 | 53.87% |
| 48h | +70.75% | +11.30% | +41.14% | 373 | 60.68% |
| 72h | +146.25% | +19.75% | +55.83% | 363 | 57.87% |

All three rows have nominal 30x leverage, a 5x account-exposure cap, a 5R initial target, 4% planned risk and extra collateral reserved when required. The 72-hour case is a hindsight-highlighted diagnostic, not the predeclared primary.

## Higher-risk fee sensitivity

The user quoted $5 on 3.6 ETH at 2,748.67, or 9,895.212 USDT notional. Its one-way/round-trip interpretation was not verified. A $5 round-trip commission implies 2.5264744 bps per side; $5 one-way implies 5.0529488 bps per side. Both scenarios additionally retain 2 bps adverse slippage per side. Fees are proportional to each trade notional, not a flat $5 per trade.

| 72h / 6% planned risk / 30x account cap | CAGR | Mean annual | Five-year net | Trades | Drawdown bound |
|---|---:|---:|---:|---:|---:|
| Base 5bps commission per side | +29.32% | +78.22% | +261.62% | 361 | 64.09% |
| $5 one-way equivalent | +29.01% | +77.84% | +257.30% | 361 | 64.21% |
| $5 full-round-trip equivalent | +46.05% | +97.39% | +564.37% | 362 | 57.47% |

**The lower-fee scenario crosses 45% CAGR at +46.05%, but that commission assumption is unverified and its settings were highlighted after evaluation.** Peak actual exposure is 12.317x account equity, not constant 30x. Worst week is -14.91%; 3 of five years are positive. It is not a validated strategy or a performance guarantee.

| Annual period | Original 4%-risk / base cost | 6%-risk / lower assumed fee |
|---|---:|---:|
| Sep 2021 to Aug 2022 | +310.34% | +429.14% |
| Sep 2022 to Aug 2023 | -16.74% | -22.57% |
| Sep 2023 to Aug 2024 | -40.03% | -33.13% |
| Sep 2024 to Aug 2025 | +39.26% | +74.62% |
| Sep 2025 to Aug 2026 | -13.69% | +38.87% |

## Delay and collateral fragility

| Lower-fee, 6%-risk scenario | CAGR | Modeled liquidations |
|---|---:|---:|
| Baseline entry timing | +46.05% | 0 |
| One additional minute delay | +27.48% | 0 |
| Two additional minutes delay | +17.67% | 0 |
| No extra isolated collateral | +30.19% | 34 |

The lower-fee result does not remain above 45% with those extra delays. A 30x initial-margin setting is not sufficient collateral for every wide stop; extra collateral is an explicit model assumption, not a claim the exchange adds it automatically. Model margin/maintenance and remaining mark gaps are not an exchange liquidation certificate.

## Integrity and scope

All 100 original exported cases and 34,154 trade rows were rechecked by separate Pandas cash/annual-return arithmetic. All 1003 original manifest identities and 42 model maturity records passed. Eight reference simulations reproduce every raw trade and daily equity value. Seven new fee/execution sensitivities are independently audited against minute inputs. Existing strategy files, parameters and model weights are unchanged.

Complete timestamped trades, initial levels, 5R target, margin, fees, funding, account equity, holding time and every annual/monthly/weekly return are under `results/`. No winners or losing years are omitted. The highlighted cases have 361-363 trades, below the earlier 1,000-trade preference; relaxing daily entries does not manufacture more independent trades.

Original fixed-policy five-year diagnostics include two selection years. Walk-forward models use matured labels, but the overall calendar and subsequent threshold/risk/fee choices have research exposure. No untouched holdout or live validation is claimed. Daily and weekly boundaries use daily observations of annualized 30-day DVOL, not actual 1D/7D option chains or dealer gamma walls. The original V4 live service remains unchanged and unarmed with V8.

Reproduce from the repository root after obtaining the V4 ETH market input:

```sh
python hold72_iv_v8/followup_72h/recheck.py --data /path/to/ETHUSDT/aligned_repaired.npz
```

No credentials are needed. The supplied source refuses altered baseline identities and unexpected data hashes. All outputs are historical simulations.
