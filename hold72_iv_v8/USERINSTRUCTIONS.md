# V8 user instructions

Owner: Parrish Lyon. V8 is research software, not an armed broker strategy.

## Install and reproduce

From `hold72_iv_v8`, use Python 3.13:

```sh
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pytest -q
```

Windows can use `py -3.13 -m venv .venv` and `.\.venv\Scripts\python.exe` for later commands. Native Windows/macOS were not tested. No exchange credentials are needed. Initial installation/data downloads need the Internet; supplied-data research then runs offline.

Get the repaired BTC and ETH inputs from the existing V4 release:
https://github.com/plyon-git/4550ETH/releases/tag/v4-research-20260922

Place each as `data/SYMBOL/aligned_repaired.npz` with these SHA-256 identities:

- ETHUSDT: `b6a9f20924ad42d8ea802404f5640356fc42c6301b98ed64ad161a576c71e46d`
- BTCUSDT: `2f6fc1e9ccb749e3e17793796d72ebd6c12a9c2f7d51e9c7e259cda8f97002a3`

The included context/iv_data contains exact daily DVOL CSV and archived API responses/checksums. input_v7.py is an unchanged source copy; only its historical input verification/load functions are used. Its same-day strategy is not the V8 engine.

```sh
python research.py --symbol ETHUSDT --data data/ETHUSDT/aligned_repaired.npz
python research.py --symbol BTCUSDT --data data/BTCUSDT/aligned_repaired.npz
python learning.py --symbol ETHUSDT --data data/ETHUSDT/aligned_repaired.npz
python learning.py --symbol BTCUSDT --data data/BTCUSDT/aligned_repaired.npz
python sensitivity.py --symbol ETHUSDT --data data/ETHUSDT/aligned_repaired.npz
python finalize.py --verify-reference --zip-out ../IV_Carry_V8_Research.zip
```

Run sequentially on memory-constrained machines. A successful process exit means computation finished, not that the performance goal passed. Do not change hashes or expected returns to make checks pass.

## Grid and evaluation

There are 1,728 fixed-rule development settings per market: reject/break/retest; daily/weekly/combined bands; 0.75/1.25/1.75/2.25 multiples; 15m/1h confirmation; 0.05/0.20 daily-sigma stop buffers; all/trend/long/IV-falling filters; latest/mean-five/historical daily-excursion calibration. Historical daily calibration is also used as an explicit weekly-scale proxy, not a 7D option chain.

Development is 2021-09-01 to 2022-09-01, validation 2022-09-01 to 2023-08-28, separate purged test 2023-09-01 to 2026-09-01, all ends exclusive. Full five-year replay spans 2021-09-01 to 2026-09-01, 1,826 days, and includes the first two selection years. A separate 250-week account spans 2021-11-15 to 2026-08-31, 1,750 days. No globally untouched holdout is claimed: prior project exposure, initial pilot checks and later ML/sizing extensions are disclosed.

The ML primary is predeclared at threshold0.25/risk1%. Threshold0.5/risk4% is highlighted after evaluation, not promoted as the primary. Sizing above it is subsequent sensitivity. Candidate labels and policies overlap and are not independent observations. A rounded arithmetic mean cannot be represented as consistently realized compound annual growth.

## Trade timing and leverage

Signals use completed 15m or 1h bars; entry uses the next minute plus adverse slippage and tick rounding. Stop is determined from known levels/swings, target is 5 times initial actual entry-to-stop distance. Levels remain fixed through the position. Exit is stop, target, account circuit, modeled liquidation, 72h maximum hold or final test boundary. Opposite signals do not force premature exits. No midnight flattening, no equity reset between refits, no averaging down or pyramiding.

There is one open position, 60-minute cooldown after exit, and up to four daily entries, not a daily entry quota. Daily/weekly equity circuits are 8%/15%, with possible overshoot from gaps/funding/slippage. Base costs are 5bps commission and 2bps adverse slippage per side, historical funding, assumed grids and a 1% prior-minute volume cap. These are execution assumptions, not verified historical fee/depth/margin schedules.

Nominal contract leverage remains 30. Initial margin is notional/30. The main model reserves more isolated collateral where necessary for stop distance plus maintenance/buffer/funding reserve. The ledger reports initial margin, total collateral, additional collateral and actual account exposure. A separate case omits extra collateral. The model does not claim an exchange automatically adds collateral or that fixed 1% maintenance equals historical brackets. Current venue/product eligibility and account settings would have to be verified for any live integration.

Daily IV is the prior complete daily DVOL close plus a modeled one-minute publication allowance. DVOL is 30-day-tenor annualized IV observed daily, not a 1D-expiry option chain. Daily sigma uses sqrt(1/365); weekly sigma uses sqrt(7/365). Daily bands anchor to previous close; weekly bands freeze Monday after 00:01 using preceding Sunday close and known IV. These are model outlier ranges, not proprietary gamma/open-interest walls.

## Evidence

Every case includes EVERY_TRADE_UTC.csv, PARAMETERS.json, METRICS.json, INDEPENDENT_AUDIT.json, daily equity and annual/monthly/weekly/rolling-year returns. Intrabar exits have minute bounds, not invented exact tick fills. Independent audit checks first stop/target crossings, fixed 5R, hold limits, quantity/volume limits, fees, funding and cash/equity reconstruction. Drawdown is a conservative intrabar bound; minute-close drawdown is reported separately. Full minute equity can be reconstructed from source, data and the ledger; default exports are daily equity and all trades.

Numerical JSON models include feature order, weights, cutoff and mature-label timestamps. Every 13 weeks, at most 730 prior days of labels are admitted, only after the complete 72h horizon matures. PREDICTIONS.npz preserves numeric features, candidate-policy identities and forecasts; it is not a broker command.

The highlighted ETH diagnostic has one missing-mark minute while exposed. Missing marks use prior observed values and sourced 15m bounds where available, otherwise a disclosed hypothetical +/-5% envelope. Those are sensitivity inputs, not exact observed liquidation history.

V8 has no broker calls. Previous V4 order-execution code is unchanged and not armed with this strategy. A live integration would require identical online features, explicit collateral management, account-specific testing and verified order-state behavior. These simulations do not establish a live profitable strategy.

## Official definitions checked 2026-09-22 UTC

Deribit DVOL: https://insights.deribit.com/exchange-updates/dvol-deribit-implied-volatility-index/
Binance leverage/maintenance: https://www.binance.com/en/support/faq/detail/360033162192
Binance liquidation: https://www.binance.com/en/support/faq/detail/360033525271

These sources support definitions, not certify hypothetical performance. Third-party data/software rights remain with their owners.
