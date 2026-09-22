# Parrish Lyon: frozen +564.37% and +261.62% ETH records

The percentages are **five-year cumulative simulated returns**, not annual gains. Exact frozen source, model weights, data and every trade are published. No parameters were optimized or silently changed for this publication.

| Record | Cumulative return | CAGR | Trades | Net WR | Commission bps/side |
|---|---:|---:|---:|---:|---:|
| [564.37%](ETHUSDT_564.37pct_5Y_20210901-20260901_WR23.20pct_RR5/README.md) | 564.3695% | 46.0498% | 362 | 23.2044% | 2.5264744202 |
| [261.62%](ETHUSDT_261.62pct_5Y_20210901-20260901_WR22.99pct_RR5/README.md) | 261.6175% | 29.3192% | 361 | 22.9917% | 5.0000000000 |

Both retain 2bps slippage per side, funding, 5R initial targets, 72h maximum holds, 6% planned account risk and 30x nominal leverage. The higher return uses an unverified full-round-trip interpretation of the quoted $5 cost. Actual account exposure and all losing years are reported separately. These were hindsight-highlighted diagnostics, not new holdout results.

## Complete contents

Each named case contains exact parameters, every timestamped trade, all annual/monthly/weekly/rolling-year returns, daily equity, minute-equity reconstruction and audit receipts. `shared/frozen_v8` contains the original IV/range logic, candidates, features, model forecasts, training, risk sizing, historical execution, reporting, tests and all 21 fitted ETH model folds. `SOURCE_MAP.json` maps every copied file back to its original repository path and commit.

**The entire 201,104,903-byte historical ETH minute input is directly in Git**, as five ordered parts in `shared/data`. The whole-publication ZIP also contains every part. It is not merely a downloader or an expiring artifact pointer. Prior-price, mark-price and funding observations and the original missing-data markers are preserved.

## Run

From this folder with Python 3.13:

```sh
python -m pip install -r shared/frozen_v8/requirements.txt
python reproduce.py --case both
python reproduce.py --case both --verify-models --retrain --minute-equity
python -m pytest -q shared/frozen_v8/tests
```

The first replay assembles input offline and matches every trade and daily equity value. The full command rebuilds features, recomputes all model forecasts, retrains all original folds without selection changes, and exports the complete minute-equity curves. It writes only `reproduced/`. Native Windows/macOS have not been tested; Linux dependencies are pinned. The install needs package access, but reruns use no credentials, external service or Internet connection once dependencies and data are available.

`PUBLICATION_VERIFICATION.json` records the actual completed rerun. `MANIFEST.json` hashes the publication, including every data part and nested original manifest. Original metadata in `shared/original_context` describes the broader study; some original metadata paths refer to other cases not part of these two records.

## Historical research, not live activation

Source snapshot: `2d070ea62f847b944f538fb4a6e9073b109b8549`. Original strategy folders and V4 live code are unchanged. This publication does not arm V8 or add an online broker integration. The included training and historical-execution programs are functional; the historical gains are not authenticated live fills or guaranteed future returns. Fee, collateral, execution-delay, drawdown, missing-mark and post-evaluation-selection limitations remain explicit. Third-party data and software retain their respective rights.
