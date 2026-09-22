# 4550ETH V4: live execution and reproducible multi-market research

Project-specific software and work: **Parrish Lyon**. The original `v3/` 45.50% diagnostic, its data, and its immutable baseline branch are not replaced. Third-party software and exchange data retain their respective rights.

## Actual capabilities and evidence

A Python order-execution service for Binance USD-M perpetuals with separate `testnet` and `live` modes. It submits signed market orders, places exchange-held stops and targets, reconciles fills and positions, persists SQLite state, manages collateral and loss budgets, and refits portable numerical ML models on a causal schedule. Live mode is implemented, not an indicator or disabled stub.

**Implementation is not production certification.** No authenticated exchange orders or funded-account tests were performed while preparing this release. Automated execution tests use a simulated exchange transport; historical tests use actual market archives. The adapter requires a permitted, verified Binance USD-M account. It is not an adapter for Binance.US spot, Coinbase or Kraken. Do not bypass venue or jurisdiction restrictions.

**The 200% annualized / rolling-year objective was not established.** Inspect `ASSESSMENT.json` and `ALL_EVALUATION_CASES.csv`; cumulative gain is not annual return. The evaluation spans 152 complete weeks, 2023-10-02 00:00 UTC through 2026-08-31 00:00 UTC exclusive. Every tested finalist's losing trades and failed gates are retained. The calendar was previously explored; later extensions are not a globally untouched holdout.

## Start

From the repository root:

```sh
cd execution_v4
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-test.txt
python -m pytest -q
python -m trader --help
```

The complete [live execution manual](USERINSTRUCTIONS/LIVE_TRADING.md) includes Windows setup, actual demo/production commands, credentials, data seeding, monitoring, flattening, reconciliation and ML refits. Read the account and risk requirements before production use. Never paste API keys into GitHub or chat.

## Source architecture

| Source | Function |
|---|---|
| `trader/exchange.py` | HMAC-signed REST requests, grids, time/rate controls, no blind mutation retry |
| `trader/runtime.py` | Persistent intents, signals, partial fills, protective exits, recovery and exits |
| `trader/store.py` | SQLite WAL, single writer, read-only monitoring, fills/income/equity/risk journals |
| `trader/risk.py` | Account loss budgets, volume/exposure limits, collateral and margin brackets |
| `trader/strategy.py` | Shared causal completed-bar rule features and availability times |
| `trader/learning.py` | Portable logistic filter, mature labels and numerical parity |
| `trader/directional.py` | Price/order-flow gradient-boosted return model and numerical JSON trees |
| `trader/refit.py` | Thirteen-week causal refits with atomic immutable model publication |
| `trader/history.py` | SHA-pinned public-history seeding, without account access or risk reset |
| `research/` | Fixed search grids, validation selection, walk-forward training, independent audits |
| `evidence_repaired/` | Every timestamped trade, period returns, continuous equity and target gates |
| `configs/` | Exact ETHUSDT, BTCUSDT and XRPUSDT rule/ML research settings |

One process owns one symbol and one dedicated single-asset, one-way account. It does not silently change hedge mode, adopt manual positions, or coordinate multiple independent bots on one shared account. Separate databases do not provide portfolio-wide coordination.

A nominal leverage request up to 500 does not force that account exposure or imply venue support. Executable leverage is bounded by the current account bracket, available margin and stop/liquidation buffer. This is REST-based completed-bar execution, not colocated millisecond trading. There is no martingale, loss clipping, withdrawal endpoint, or hidden live-performance lockout. Risk and consistency faults stop entries because uncertain order state can create duplicate exposure.

## Reproduction and durable data

The release assets include three repaired public-market datasets. Place each `aligned_repaired.npz` under `data/ETHUSDT/`, `data/BTCUSDT/`, or `data/XRPUSDT/`, preserving its provenance and checking the hashes in the manual. Large market inputs are release assets rather than oversized Git blobs. Source, model weights and reporting evidence are committed directly.

```sh
python -m research.release --data-root data
```

This runs the entire defined search, refits models using mature labels, exports all finalists and creates configurations. It never connects to a trading account. A zero process exit means stages completed, not that the return objective passed. [Research instructions](USERINSTRUCTIONS/RESEARCH.md) explain the periods, raw-tape repair, remaining mark gaps, costs, capacity and limitations.
