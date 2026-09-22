# V6 user instructions

## Capabilities and limits

V6 is a forward-only empirical forecast and historical execution test. It supplies the source and full evidence for the screenshot-inspired hypotheses. It does not know QQQWave's proprietary `MinAvg`, bear classification, 76-sample construction or tooltip formula. Its `mean_low_proxy` is explicitly a separate arithmetic mean of projected historical lows. It does not reproduce a dealer-position or strike-gamma wall.

No V6 command submits orders. Existing V4 live-execution code is separate and unchanged. Copying these forecast levels into V4 without a parity-tested integration would be a different strategy, not these backtests.

## Install

Use Python 3.13. In the repository or extracted release, open `qqqwave_v6`:

```sh
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python bootstrap_engine.py
python -m pytest -q
```

Windows PowerShell can use `py -3.13 -m venv .venv` and `.\.venv\Scripts\python.exe` instead of `python` for later commands. Linux reproduction was tested; native Windows/macOS deployment was not. No API keys are used. Package installation needs Internet access; all supplied-data computations run offline afterward.

`bootstrap_engine.py` recreates only the versioned V6 engine from a hash-pinned copy of V5. It adds frozen absolute stops and forecast deadlines, preserves V5 source, and exports the exact diff. It refuses changed input/output identities rather than overwriting local modifications silently.

## Replicate the visible architecture on another series

Prepare a CSV whose first column is a timezone-aware UTC session/forecast-origin timestamp, followed by positive valid `open,high,low,close` columns. Include `volume` when available. Use one row per real daily session with at least 201 rows; do not insert weekends into an equity series. For crypto, this implementation uses UTC calendar days. For stocks, five forward aggregations are five actual observed exchange sessions, not five calendar days.

Example using the included QQQ daily history:

```sh
python panel.py --daily-input results/QQQ/daily_inputs.csv \
  --lookback 200 --horizon 5 --matching weekday --scale realized \
  --out my_qqq_panel
```

For ETH:

```sh
python panel.py --daily-input results/ETHUSDT/daily_inputs.csv \
  --lookback 200 --horizon 5 --matching weekday --scale realized \
  --out my_eth_panel
```

`--origin` optionally selects an exact timezone-aware session timestamp already present in the CSV. An unmatched or timezone-naive origin is rejected. Defaults use the last input session, not today's price. The open/high/low/close of the origin's unfinished session never determine its levels; only older completed samples are used. Ensure your input dates represent the actual sessions and available data.

`percent` leaves historical percentage excursions unscaled. `realized` normalizes by each sample's known RV20 and rescales to the current known RV20. `iv_scaled` requires a genuine `iv_daily_sigma` column known at the origin; no RV fallback is silently substituted. The included crypto IV series uses completed Deribit DVOL with a modeled publication allowance. The IV mode is a historical/IV hybrid, not a strike-level options surface.

Output:

- `PANEL.json`: origin, reference, sample count, mean proxies, percentile levels, last matured sample and scope.
- `price_odds.csv`: 101 price levels, integer counts and unadjusted empirical frequencies of historical projected low/high excursions.
- `matured_samples.csv`: every contributing historical sample and its projected low, high and terminal price.

The screenshot's candidate `(count-1)/(total-2)` display adjustment is documented but deliberately not substituted for raw probability. We do not force the denominator to 76 or set future win rate to 97.37%. Under this exact simple weekday rule there are 28 eligible crypto samples and typically 39-40 equity samples. Resolving the vendor's different sample count requires its Data export or documentation.

## Full five-year and 250-week research

The current repository `volatility_v5` and the V4 release contain the previously verified inputs. The V6 ZIP includes a small `context/` copy of the specific DVOL and daily QQQ/SPY inputs; provenance records may refer to additional earlier V5 files not needed by V6.

Download the three large repaired minute datasets from:

https://github.com/plyon-git/4550ETH/releases/tag/v4-research-20260922

Place them as follows, renaming each release filename to `aligned_repaired.npz` within its market directory:

```text
data/ETHUSDT/aligned_repaired.npz
data/BTCUSDT/aligned_repaired.npz
data/XRPUSDT/aligned_repaired.npz
```

Required SHA-256:

| Market | SHA-256 |
|---|---|
| ETHUSDT | b6a9f20924ad42d8ea802404f5640356fc42c6301b98ed64ad161a576c71e46d |
| BTCUSDT | 2f6fc1e9ccb749e3e17793796d72ebd6c12a9c2f7d51e9c7e259cda8f97002a3 |
| XRPUSDT | 43678daef70287657734cf3eb6b6915ffa5df0b24d90d289d8892ee1d5f70859 |

Then run sequentially, keeping peak memory lower than loading all markets at once:

```sh
python run.py --data-root data --context-root context
python finish.py --verify-reference --zip-out ../QQQWave_V6_Research.zip
```

`--symbols` can restrict `run.py` to QQQ/SPY event checks or individual crypto markets. `finish.py` requires all five outputs to produce the complete cross-market assessment; do not call a partial subset complete.

Development is 2020-09-01 to 2021-06-01, validation 2021-06-01 to 2021-08-25, then a purge before evaluation. The five-year interval is 2021-09-01 to 2026-09-01 exclusive, 1,826 days. The separate 250-week interval is 2021-11-15 to 2026-08-31 exclusive, 1,750 days. All period returns and zero-activity intervals remain visible. The dataset predates the screenshot's September 18 reference date; this is not a replay of its precise latest snapshot.

Each surface tests wall rejection, continuation and a direct short-to-projected-low hypothesis. The grids, validation selection, risk settings and fixed final choices are exported. The calendar was already used in earlier research, so no globally untouched holdout is claimed. There is no live or forward-profit certification.

## Event probabilities versus trade results

Touch probability means a future high/low reaches a specified level sometime within the horizon. It does not establish entry availability, stop ordering, terminal direction or profitability. An already-crossed target cannot be counted as a newly available lower short objective. Overlapping five-session forecasts share observations; the every-fifth-origin sensitivity is not a proof of statistical independence.

Crypto simulations use completed five-minute signal bars, next-minute entries, absolute levels fixed before entry, one position per account, quantity/volume limits, fees, funding, and stop-before-target handling of ambiguous bars. A later touch does not retroactively turn a stopped-out trade into a winner. $5 fee scenarios convert the user's example into proportional notional rates; one-way versus round-trip is separately tested. Initial margin is not the account-equity denominator.

QQQ/SPY results are daily forecast-event studies only. They are not live option trades, dealer gamma backtests, or intraday ES executions. The sparse marks in the crypto source are handled using disclosed sensitivity values; exact liquidation during those gaps cannot be established. Execution grids, costs and impact are model assumptions.

## Inspect the complete evidence

Each traded case includes `all_trades_UTC.csv`, `PARAMETERS.json`, `METRICS.json`, `AUDIT.json`, daily equity, all weekly/monthly returns and rolling-year returns. Entries are simulated minute opens; intrabar exits retain minute bounds, not fabricated exact tick timestamps. Full minute equity can be regenerated from the kernel; default files retain daily equity and every trade.

`EVENT_SUMMARIES.json`, per-origin `events_*.csv` and `levels_*.csv` keep forecasting evidence separate from executed trade ledgers. `SCREENSHOT_ANALYSIS.json` preserves the manually transcribed settings and all 25 count/percentage pairs. `MANIFEST.json` binds file identities; `VERIFICATION.json` records audit checks. Exact reproduction verifies arithmetic under assumptions, not future profit.
