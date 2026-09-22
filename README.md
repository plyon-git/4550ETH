# 4550ETH

Owner: **Parrish Lyon**. See [OWNERSHIP.md](OWNERSHIP.md).

This repository preserves the exact ETHUSDT fixed-family breakout diagnostic that returned **+45.5040%** in its recorded 52-week evaluation. It is not the shock-continuation primary. The original `v3/engine.py`, `v3/signals.py`, and `reproduce_saved.py` are preserved byte for byte. New research must remain separate from this baseline.

## Exact strategy

`breakout|tf=15|window=192,volume=1.0|risk=0.01|rr=4.0|trail=0.0`

A completed 15-minute close above the previous 192 bars' high or below their low, with volume above its 64-bar rolling median. Stop distance is 2.5 times the clipped 32-span EWMA true-range fraction. Planned account risk is 1%, target is 4R, no trailing stop. Positions may close on opposite signals, account-risk circuits, or the 48-hour timeout. Earliest entry is the next minute open.

## Recorded evaluation, not a performance promise

| Metric | Value |
|---|---:|
| Evaluation start UTC | 2025-06-02 00:00 |
| Evaluation end UTC, exclusive | 2026-06-01 00:00 |
| Complete weeks | 52 |
| Starting equity, USDT | 10,000 |
| Ending equity, USDT | 14,550.402603689372 |
| Total net return | +45.504026% |
| Geometric weekly return | +0.723825% |
| Worst week | -3.976384% |
| Longest losing-week streak | 5 |
| Trades | 222 |
| Nominal leverage cap | 20x |
| Maximum actual notional/account-equity ratio | 1.817029x |

Five basis points commission and two basis points adverse slippage per side, observed historical funding, 1% of prior-minute volume participation, a 0.001 ETH quantity step, 0.01 USDT price tick, 20 USDT minimum notional, and fixed 1% maintenance-margin assumptions are inherited unchanged. These are not verified account-specific fees or historical margin tiers. Stops and volume participation do not establish order-book execution or capacity.

**This diagnostic was highlighted after its evaluation result was known. It is hindsight-selected, not a new untouched holdout. Its earlier validation segment lost 4.8039%.** This is not a demonstrated profitable full-account 20x strategy. The target results from earlier research remain failed. There is no order-submission adapter and no API credential is required.

## Files and reproduction

`SAVED_DIAGNOSTIC.json` holds the exact parameters and original metrics. `PROTOCOL.json` preserves the previous research protocol. `results/breakout_weeks.csv` contains the original 52 weekly returns. The Python source is directly browsable under `v3/`.

The original large market input and compressed trade/equity reference ledgers are deliberately not copied into this public Git tree. Use the complete `ETH_Breakout_Diagnostic_Saved.zip` already supplied to the owner and saved in the owner's ChatGPT Library. Extract its `data/aligned_data.npz`, `results/breakout_trades.csv.gz`, and `results/breakout_equity.csv.gz` to the matching paths here. The original source and input SHA-256 identities are recorded in `SAVED_DIAGNOSTIC.json`.

```sh
python -m venv .venv
# Activate .venv for your operating system.
pip install -r requirements.txt
python reproduce_saved.py
```

A zero reproduction exit code means that the original trades, three minute-equity series, weekly returns, and metrics match. It does not mean that a trading target is met. New optimization will be documented separately, without rewriting the baseline history.
