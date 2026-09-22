# Volatility V5: IV-derived walls, range averages and causal filters

Owner of project-specific work: **Parrish Lyon**. Third-party data, libraries and indicator rights remain with their respective owners.

**This is a separate research branch. No tested case established 65% CAGR plus 200 completed trades. No V5 signals were armed for live orders.** The original45.50% strategy and V4 production order adapter are unchanged. This project tests new hypotheses; it does not relabel old returns or reproduce a proprietary indicator from a screenshot.

## What was actually tested

Actual Deribit daily BTC/ETH DVOL; explicit RV20 and average-range proxies; fixed UTC session bands; completed5/15-minute wall rejection and breakout triggers; prior-trend filters; actual-minute price/funding simulation; prior26-week adaptive selection; mature-label learned taker-flow filters. Additional SPY/VIX and QQQ/VXN daily-candle diagnostics broaden the test but are not ES5-minute or broker-fill validation.

Evaluation: five calendar years, 2021-09-01 to2026-09-01 exclusive, 1,826 days. Separate250weeks, 2021-11-15 to2026-08-31, 1,750 days. Inactivity remains in the denominator. CAGR, arithmetic average annual return, individual anniversary years, rolling years and trade count are separate reported measures.

Read [RESULTS.md](RESULTS.md), [ASSESSMENT.json](ASSESSMENT.json), [ALL_RESULTS.csv](ALL_RESULTS.csv) and every case's files under `results/`. The best observed case is not retroactively made the frozen primary. Zero-cost sensitivities are labeled and are not promoted as executable returns.

## Reproduction

Use Python3.13 and `requirements.txt`. Download the three `*_aligned_repaired.npz` market inputs from the repository release `v4-research-20260922`; place each at `data/ETHUSDT/aligned_repaired.npz`, `data/BTCUSDT/aligned_repaired.npz`, `data/XRPUSDT/aligned_repaired.npz`. `source/research.py` enforces their exact SHA-256 identities. Small IV and equity snapshots and their URL/hash receipts are included in this release and Git tree.

From this folder:

```sh
python -m venv .venv
# Activate the environment for your operating system.
python -m pip install -r requirements.txt
python -m pytest -q tests
python run_all.py
```

Run sequentially; concurrent full-minute jobs can exceed available memory. A successful process means calculations finished, not that the target passed. Individual stages:

```sh
python source/research.py --symbol ETHUSDT
python source/adaptive.py --symbol ETHUSDT
python source/meta_filter.py --symbol ETHUSDT
python source/equity_research.py
python source/assemble.py
```

The separate V5 kernel is generated once by `bootstrap_engine.py` from the SHA-pinned original simulator and then committed. Both original-source and resulting-kernel hashes are checked. It adds absolute pivot targets without editing the original V4 kernel.

## Files and scope

`source/` contains all band calculations, chronological selection, numerical ML inference, simulation, audit and reporting code. `tests/` checks feature-prefix invariance, future perturbations, actual-IV timestamps, missing-IV rejection, signal/entry timing, stop-first ordering, numerical ML parity and period accounting. `results/*/META/models/` contains numerical trees, not executable pickles. Every trade and loss is retained.

These are hypothetical historical results. Missing mark prices use explicit modeled values; historical liquidation tiers, queue position and depth remain incomplete. SPY/QQQ daily timing cannot prove intraday execution. Models are not automatically connected to the existing live runtime. Earlier and current research use an exposed calendar, so they are not globally untouched holdouts. See [docs/METHODOLOGY.md](docs/METHODOLOGY.md).
