# ETHUSDT +564.37% five-year record

Project-specific owner: **Parrish Lyon**. Frozen original source commit: `2d070ea62f847b944f538fb4a6e9073b109b8549`.

**564.37% is cumulative, not annual.** Period: 2021-09-01 00:00 UTC through 2026-09-01 00:00 UTC exclusive, 1,826 days / 260 complete Monday weeks plus boundary days.

| Metric | Exact archived case |
|---|---:|
| Net cumulative return | 564.36952788% |
| CAGR | 46.04983897% |
| Closed trades | 362 |
| Net win rate | 23.20441989% |
| Initial / final equity | 10000.00 / 66436.95278818 USDT |
| Configured initial target | 5R |
| Maximum holding period | 72 hours |
| Nominal leverage | 30x |
| Planned account risk / exposure cap | 6% / 30x |
| Actual peak exposure | 12.31744314x |
| Conservative modeled drawdown | 57.46762087% |
| Worst full week | -14.90680783% |
| Commission per side | 2.5264744202 bps |

The unverified $5-complete-round-trip commission interpretation at 9,895.212 USDT notional. Both fee cases additionally retain 2bps adverse slippage per side and historical funding. The paths and trade counts differ because costs change account equity and later sizing.

## Files and execution

`EVERY_TRADE_UTC.csv` contains all winners and losers, UTC entry/exit bounds, prices, stop/5R target, quantity, fees, funding, P&L, balances, margin/collateral and IV availability. Annual, monthly, weekly, rolling-year and daily-equity reports are original unchanged records. `PARAMETERS.json` is the original exact configuration.

All original source, candidate policies, 21 fitted ETH models, features, forecasts, IV data, training and historical execution are in `../shared/frozen_v8/`. All 201,104,903 bytes of the historical minute input are in the ordered checksum-verified parts in `../shared/data/`. The published `MINUTE_EQUITY_RECONSTRUCTED.csv.gz` independently reconstructs every evaluation minute from the frozen trades. Original mark gaps remain flagged.

From this folder, after installing Python 3.13:

```sh
python -m pip install -r ../shared/frozen_v8/requirements.txt
python reproduce.py --verify-models --retrain --minute-equity
```

This reconstructs the exact input automatically, verifies the original files, rebuilds every model forecast, retrains original folds without retuning, and matches all ledger fields, daily equity values, metrics and annual returns. Outputs go to the parent `reproduced/` folder, never over the original records. No network is required after dependencies and the complete publication are available.

## Scope retained

This is a hindsight-highlighted historical diagnostic, not an untouched holdout or an authenticated live account. Fees, slippage, margin, collateral and market impact are assumptions. One exposed minute has missing original mark data handled by a disclosed sensitivity bound. A 5R target does not guarantee a 5R realized payoff. The trade count does not meet the earlier 1,000 preference.

Publishing does not arm the V4 live service or implement an online V8 broker integration. The frozen training and historical-execution code is functional; original V4 and earlier research are unchanged. See the parent README and original context for the complete recorded limitations. Third-party rights remain applicable.
