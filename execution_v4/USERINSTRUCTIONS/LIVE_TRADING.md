# User manual: actual live execution

Owner: **Parrish Lyon**. This manual applies to `execution_v4/`, not the original `reproduce_saved.py` backtest. Production mode can submit real orders. No profitable outcome, account eligibility or production certification is implied.

## 1. Account and deployment

The adapter is for a verified, permitted **Binance USD-M perpetual** account with **single-asset USDT margin** and **one-way position mode**. Binance.US spot keys and other venues are incompatible. Confirm product and jurisdiction eligibility before funding or using production credentials. Do not evade venue restrictions.

Use one dedicated account, one symbol and one writer. Start flat without foreign regular or conditional orders. The service does not coordinate independent bots sharing one account or adopt manual positions. It configures isolated margin for its symbol and selects leverage within the exchange bracket and stop/collateral limits at entry; it does not automatically switch account-wide position mode.

An always-on computer/server needs Python 3.13, permitted API connectivity, a synchronized clock, persistent local disk and monitoring. Tests ran on Linux. Native macOS/Windows deployments and authenticated demo/production trading were not exercised in this verification.

## 2. Install

```sh
git clone --branch execution-v4 https://github.com/plyon-git/4550ETH.git
cd 4550ETH/execution_v4
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-test.txt
python -m pytest -q
python -m trader --help
```

Windows PowerShell uses the environment interpreter directly, without changing execution policy:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-test.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m trader --help
```

Substitute that interpreter for `python` below on Windows. Pin the supplied dependencies for numerical reproduction; upgrading them requires revalidation.

## 3. Choose and inspect a configuration

`configs/ETHUSDT_directional.json`, `BTCUSDT_directional.json`, and `XRPUSDT_directional.json` contain each market's validation-selected ML settings and a SHA-pinned model. `_rule.json` files contain rule alternatives. Inclusion is not a recommendation: several lose heavily in the evaluation.

Inspect `strategy`, `execution` and `backtest_ref`. `risk_fraction` is planned account-equity loss, not margin allocation. `exposure_cap` bounds notional/account equity. `requested_contract_leverage` determines collateral, not a multiplication of capital. The actual setting may be reduced for venue brackets, available margin or liquidation distance. Below-minimum orders are skipped, not rounded up beyond risk limits.

Changing thresholds, risk, exits, warm-up or model parameters means the published backtest no longer describes that configuration. The state database binds to a specific account, mode, symbol and configuration. Never delete it to bypass loss limits or reuse it for another strategy.

The released directional configurations enable `auto_refit: true`: a 13-week schedule, completed bars and mature labels only. Each new numerical model is saved atomically under the state directory with a hash and journal entry. The initial model is the last evaluation-fold fit, not future-dated. With refitting disabled, an expired model stops entries; it is not silently replaced with an untrained rule.

## 4. Download and seed matching history

Obtain the chosen repaired dataset from the repository's V4 release assets. Extract/place it at `data/SYMBOL/aligned_repaired.npz`. Verify SHA-256:

| Market | SHA-256 |
|---|---|
| ETHUSDT | `b6a9f20924ad42d8ea802404f5640356fc42c6301b98ed64ad161a576c71e46d` |
| BTCUSDT | `2f6fc1e9ccb749e3e17793796d72ebd6c12a9c2f7d51e9c7e259cda8f97002a3` |
| XRPUSDT | `43678daef70287657734cf3eb6b6915ffa5df0b24d90d289d8892ee1d5f70859` |

Seed a new production-market cache without accessing an account:

```sh
python -m trader seed-history \
  --config configs/ETHUSDT_directional.json \
  --data data/ETHUSDT/aligned_repaired.npz \
  --sha256 b6a9f20924ad42d8ea802404f5640356fc42c6301b98ed64ad161a576c71e46d \
  --state state/eth-live.sqlite
```

The command requires the actual input hash, continuous nonfuture data, matching bootstrap start and an unbound database. It does not reset private live state. Startup then retrieves missing completed bars. Gaps or unexpected completed-bar revisions halt entries.

Demo and production history can differ. Do not seed production candles into a demo cache and disable revision checks when they conflict. Mechanical demo testing requires its own compatible config/history and is not the published production-history backtest. Separate accounts, modes and databases explicitly.

## 5. Credentials stay local

Use only trading/read permissions needed, disable withdrawal permissions where supported, and apply an IP allowlist. Keep separate demo and production keys. No research workflow needs exchange secrets. Never commit private account exports or keys.

Environment names:

```text
BINANCE_TESTNET_API_KEY
BINANCE_TESTNET_API_SECRET
BINANCE_LIVE_API_KEY
BINANCE_LIVE_API_SECRET
```

In Bash (run `bash` first from zsh), enter values without literal secrets in shell history:

```sh
read -r -s -p 'Demo API key: ' BINANCE_TESTNET_API_KEY; echo
read -r -s -p 'Demo API secret: ' BINANCE_TESTNET_API_SECRET; echo
export BINANCE_TESTNET_API_KEY BINANCE_TESTNET_API_SECRET
```

Use the analogous LIVE variable names for production. A managed local secret store is preferable for a service. Protect the host: privileged local processes may read environment variables. Revoke/rotate exposed keys at their provider; deleting the current Git file does not remove history, clones or caches. [3]

## 6. Read-only account checks and public observation

```sh
python -m trader check --config configs/ETHUSDT_directional.json --mode testnet
```

`check` reads account capability, current fees/brackets, position mode, positions and orders. It does not recover or submit orders. A successful read is not proof that entry plus both protections will be accepted. Keep its private output out of Git.

Public observation requires no key:

```sh
python -m trader observe --config configs/ETHUSDT_directional.json \
  --state state/eth-observe.sqlite --mode live
```

It computes a completed-bar decision from the pinned model, without orders or account binding. It does not establish forward profitability. Do not share its database with a running writer. A production-history seed can be used for an observation-only cache too.

## 7. Actual demo execution

```sh
python -m trader run --config configs/ETHUSDT_directional.json \
  --state state/eth-demo.sqlite --mode testnet
```

This sends actual demo orders, not local fake fills, when a fresh qualifying signal occurs. It requires demo keys, collateral and matching available demo history. Demo history/liquidity can differ materially from production. `--once` runs one cycle and can place an order; it is not a preview.

Exercise entry, partial fill, protective exits, interruption, reconnect, export, flatten and restart in the account. Compare local records against the venue. Automated mocked tests do not replace this account-specific integration test.

## 8. Actual production launch

After eligibility, integration testing and an explicit personal risk decision, set production variables and use the separately seeded production database:

```sh
python -m trader run \
  --config configs/ETHUSDT_directional.json \
  --state state/eth-live.sqlite \
  --mode live \
  --live-confirmation I_ACCEPT_REAL_ORDERS \
  --confirm-venue-eligibility
```

This command can send signed real market orders to `https://fapi.binance.com`. Demo mode uses `https://demo-fapi.binance.com`. [1][2] The two arguments acknowledge real effects and eligibility; they are not a permanent block or a performance gate. **No 200%-CAGR strategy is certified by this release.**

Do not run multiple writers with different database paths on one account. The OS lock protects one state file, not every account process on every machine. Use persistent local storage, not a shared network filesystem. Retain the same state and model files across restarts.

## 9. Monitor, export, stop and flatten

Read-only status and export can run alongside the writer:

```sh
python -m trader status --state state/eth-live.sqlite
python -m trader export --state state/eth-live.sqlite --out private_exports/eth
```

Inspect heartbeat, halt reason, pending intents, position, daily/weekly bases and venue-held stops/targets. Runtime exports contain private actual fills; research CSVs contain simulated trades. SQLite/WAL/SHM files and exports must remain private. Use coordinated/SQLite backups, not an incomplete copy of an active database.

**Ctrl+C stops the local service, not the exchange position.** Accepted server-held stops/targets remain. Stop the writer before another process issues mutations. To close only the position owned by this state:

```sh
python -m trader flatten \
  --config configs/ETHUSDT_directional.json --state state/eth-live.sqlite \
  --mode live --live-confirmation I_ACCEPT_REAL_ORDERS --confirm-venue-eligibility
```

The service uses reduce-only market closes, confirms flat state and cleans owned protection. It refuses unowned positions. Confirm actual flatness at the venue. If APIs are unavailable, use the venue's permitted interface; no local program guarantees a close during an exchange outage.

## 10. Fault reconciliation, not blind retry

Some timeout/503 responses mean an order may have executed. The adapter retains its durable client ID and queries that intent rather than issuing a duplicate. [2] Unresolved status halts entries. Do not clear state, blindly resubmit, or assume no response means no execution.

After reconciling actual orders/fills/positions with the journal:

```sh
python -m trader resume \
  --config configs/ETHUSDT_directional.json --state state/eth-live.sqlite \
  --mode live --live-confirmation I_ACCEPT_REAL_ORDERS --confirm-venue-eligibility \
  --confirm-reconciled
```

Then restart `run`. Resume preserves loss bases and locks. A genuinely unexecuted unknown intent can be resolved using `resolve-intent`, exact `--client-id`, and `--confirm-no-execution I_VERIFIED_NO_EXECUTION`, with the same production acknowledgments. This is an operator declaration after reviewing venue history. The command also requires a flat account, no open orders and no matching venue order. It retains the intent tombstone and entry halt, rather than retrying automatically.

The fill/income journal uses overlapping read windows and record deduplication for late reports. Gaps beyond available history halt rather than silently dropping records. Account transfers require external-cash-flow/risk reconciliation. A process restart does not erase day/week losses.

## 11. Manual learning and automatic refits

Directional models use actual taker volume, trade counts and price features on one-hour bars. The training window is 1,095 days, with 13-week refits. Every forward label matures before its cutoff. JSON contains numerical tree weights and is checked against the fitted estimator; executable pickle is not loaded.

A separate manual research fit:

```sh
python -m trader train --config configs/ETHUSDT_directional.json \
  --data data/ETHUSDT/aligned_repaired.npz \
  --cutoff 2026-09-01T00:00:00Z --horizon-bars 4 \
  --out models/manual-eth-20260901.json
```

The command prints its SHA-256. That fit is a different model, not the historical 152-week result. Cutoffs must be timezone-aware, nonfuture and covered by supplied data. Changes need a separately reviewed config and state migration, not identity-check removal while positions are open.

## Scope and sources

Real fills differ from candle assumptions through latency, fees, depth, collateral and outages. Stops are not guaranteed fill prices. This release supports one-way isolated linear USDT contracts and REST polling, not all order types, all venues or colocated HFT. Remaining historical mark gaps are documented in RESEARCH.md. Automated tests did not access a funded or authenticated demo account.

Official documentation checked 2026-09-22 UTC:

[1] Binance Trade API, market/conditional orders and order/fill queries: https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/trade

[2] Binance General Info, production/demo hosts and unknown execution status: https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/general-info

[3] GitHub sensitive-data guidance: https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository
