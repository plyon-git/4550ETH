# Run the daily IV test

From daily_iv_v7, use Python3.13:

```sh
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pytest -q
```

Windows can use `py -3.13 -m venv .venv` and `.\.venv\Scripts\python.exe` for subsequent commands. Native Windows/macOS was not verified. The tested numerical packages are pinned in requirements.txt. No exchange keys are needed.

The context/iv_data directory holds archived daily DVOL and receipts. Minute trade/mark/funding inputs are unchanged V4 repaired assets:

https://github.com/plyon-git/4550ETH/releases/tag/v4-research-20260922

Place/rename the downloaded assets to:

```
data/BTCUSDT/aligned_repaired.npz
data/ETHUSDT/aligned_repaired.npz
```

Required SHA-256:

| Market | SHA-256 |
|---|---|
| BTCUSDT | 2f6fc1e9ccb749e3e17793796d72ebd6c12a9c2f7d51e9c7e259cda8f97002a3 |
| ETHUSDT | b6a9f20924ad42d8ea802404f5640356fc42c6301b98ed64ad161a576c71e46d |

Run fixed policies, stresses and separate250-week accounts, then the explicitly later adaptive extension:

```sh
python research.py --data-root data
python adaptive.py --data-root data
python finalize.py --zip-out ../Daily_IV_V7.zip
```

Markets run sequentially. EVERY_DAY.csv includes each calendar day and skip reason. EVERY_TRADE_UTC.csv includes every completed trade, IV reading/availability, frozen stops and targets, UTC time bounds, fees, funding, size, account balance and P&L. Intrabar exits retain minute intervals, not invented exact exchange-fill seconds. Losing trades are not omitted.

PROTOCOL.json, DEVELOPMENT.json, VALIDATION.json and FROZEN.json record selection. adaptive_research/SELECTION_JOURNAL.json identifies each decision, last matured outcome and policy. Its NPZ preserves the ranking inputs and frozen daily actions. Account equity remains continuous at switches.

Audits reconstruct daily cash and independently locate the first stop/target crossing. Tests perturb future prices/IV, enforce one daily entry and same-day exit, reject missing IV rather than use an RV fallback, and detect ledger corruption. These checks validate stated arithmetic/timing, not every exchange archive or live profitability.

ASSESSMENT.json separates trade-count, CAGR, average-annual-return and five-positive-year conditions. Process success is not a return-target pass. Initial capital is10,000 USDT per market, not pooled and not a150x fully margined account.

Everything here is historical/offline. Existing V4 execution has its own manual. The new daily policies have not been wired into it. Do not replay a historical ledger as real orders or use end-of-day outcomes for a current decision.
