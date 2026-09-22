# Daily/weekly IV carry research, V8

Owner of project-specific work: **Parrish Lyon**. Third-party data/software rights remain applicable.

A separate 72-hour, 5R, 30x-contract-setting research branch. No previous source or result is replaced. Read RESULTS.md for actual results and the distinction between arithmetic average annual returns and CAGR.

The program tests BTCUSDT and ETHUSDT rejection, continuation and recent-bar retests of daily/weekly IV-derived ranges. It includes historical DVOL, minute futures price/mark/funding inputs, causal features, continuous overnight position accounting, matured walk-forward learning and independently audited ledgers. All positions have a fixed initial 5R target and at most 72 hours holding time. No mandatory daily trade or pyramiding.

**No base-cost tested configuration establishes 45% CAGR. Some subsequent ETH diagnostics have arithmetic annual averages above 45% but three losing years. The 55.83% average case compounds at 19.75% and has a 57.87% drawdown bound. It has 363 trades, below the earlier 1000-trade requirement.**

The nominal 30x setting is not necessarily 30x account exposure. The main model reserves additional isolated collateral where needed and sizes notional from account risk. A separate initial-margin-only scenario reports liquidations without that reserve. This is not an authenticated historical exchange margin reconstruction.

Install requirements.txt, place the hash-pinned V4 BTC/ETH datasets as described in USERINSTRUCTIONS.md, run research.py and learning.py for both markets, sensitivity.py for ETH, tests and finalize.py. Source, models, forecasts, every trade and reporting are preserved. No broker calls are made. V4 live execution and the original 45.50% baseline remain unchanged.
