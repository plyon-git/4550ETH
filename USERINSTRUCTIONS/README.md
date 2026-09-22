# 4550ETH user instructions

Project owner: **Parrish Lyon**. Existing ownership and third-party rights notices in [OWNERSHIP.md](../OWNERSHIP.md) continue to apply.

## Start here

**This revision can reproduce historical trades. It cannot initiate live exchange trades.** The current repository contains a deterministic breakout signal and a simulated execution engine, not a trained ML strategy or a live broker connection. An exchange API key does not turn this code into an order-execution service.

| Requested system | Source and reporting status | Live execution |
|---|---|---|
| Original +45.504026% / 52 weeks / 31.531532% net WR / target 4R | Source, configuration, market input, every trade, equity history and independent audit are committed | Not implemented |
| Claimed +60.37% / 52 weeks | Exact source, parameters, WR, RR, model artifacts and ledger remain unrecovered | Not established |
| Claimed +102.02% / 93 weeks | Exact source, parameters, WR, RR, model artifacts and ledger remain unrecovered | Not established |

The earlier description called the two larger returns a balanced two-sleeve result. That description alone does not identify the sleeves, portfolio engine, weights, training procedure, or execution parameters. No different implementation has been relabeled to match those returns.

## Available instructions

- [RUN_OFFLINE.md](RUN_OFFLINE.md): install, verify the original files, reproduce all 222 baseline trades, and rerun the 1.75R/2R/4R comparison.
- [LIVE_TRADING.md](LIVE_TRADING.md): direct answer about initiating live trades, missing components, risk controls and acceptance tests required for a later live release.
- [STRATEGY_RECOVERY.md](STRATEGY_RECOVERY.md): exact evidence needed to preserve the two unrecovered variants without inventing their implementations.

After installation, these commands are runnable from the repository root:

```sh
python USERINSTRUCTIONS/check_installation.py
python reproduce_saved.py
python tools/publish_evidence.py
```

They check files or simulate historical trades. They do not connect to a broker. The original source and saved parameters remain unchanged.

To explicitly ask whether this release supports live trading:

```sh
python USERINSTRUCTIONS/check_installation.py --require-live
```

A valid installation returns exit code **2** with `LIVE_NOT_IMPLEMENTED`. This is a diagnostic, not an order command or a live-mode toggle. A file-check failure instead returns **1**. The diagnostic has no network, exchange SDK, credential input or order-submission code.

## Important distinctions

Backtest reproducibility is not evidence of actual exchange fills or future profitability. The 45.50% number is a historical diagnostic selected after evaluation results were visible, not an untouched holdout. The saved execution assumptions and their limitations are in [EVIDENCE_README.md](../EVIDENCE_README.md).

A configured leverage limit is not account exposure. The original 20x-cap test reached only about 1.817x notional/account equity. Its engine rejects caps above 20x; changing that validation would change the baseline code, not recover a missing high-leverage version.

The repository is public. Do not put exchange API keys, secrets, seed phrases or private account records into files, issues, commits, Actions logs or this chat. No credential is needed for anything this release can run. See [LIVE_TRADING.md](LIVE_TRADING.md#credentials-and-public-repository-hygiene).
