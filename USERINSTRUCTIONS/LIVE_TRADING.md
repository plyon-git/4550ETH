# How to initiate live trades: release status and requirements

## Direct answer for the current release

**There is no supported command in this repository that initiates live trades.** `reproduce_saved.py` simulates historical orders; `tools/publish_evidence.py` generates historical evidence. Neither has a broker adapter, API authentication, live market loop, order/fill reconciliation or persistent live positions. The requested 60.37% and 102.02% implementations have not been recovered, so a live command tied to those returns cannot be specified truthfully.

Do not run a made-up `--live` command, replay the CSV as orders, substitute current prices into a historical array, or give the historical research scripts credentials. This manual does not claim the missing machinery is implemented. The read-only `check_installation.py --require-live` diagnostic deliberately returns `LIVE_NOT_IMPLEMENTED`.

## What a later live release must provide

The following is an implementation and acceptance checklist, not runnable functionality in this revision.

### 1. Exact strategy identity and operating venue

Freeze the source, configuration, historical input, model artifact where applicable, and reporting period for the specific variant. For a two-sleeve portfolio, include both sleeves, capital weights, rebalancing, concurrency, netting and shared risk/capacity rules. Confirm the actual account is permitted to trade the selected venue/product in the operator's jurisdiction. A Binance historical dataset does not establish eligibility for Binance derivatives or validate another broker's fills. Do not bypass regional restrictions.

### 2. Current data and strategy parity

Use completed bars on the exact UTC boundaries and a causal warm-up compatible with the tested indicators. Reject stale, duplicated, out-of-order and missing inputs; reconcile reconnects before new entries. Check parity between online feature calculations and saved offline signals. Preserve funding, mark-price treatment and source semantics. A training package must save training windows, label maturity, feature ordering, transformations and weights; a deterministic rule should explicitly identify itself as non-ML.

### 3. Order lifecycle and reconciliation

Implement authentication and an order adapter for the chosen account, instrument and position mode. Fetch current instrument grids, minimum notional, fee tier and margin brackets; do not carry research assumptions into exchange orders without validation. Persist an order intent before submission, with a durable unique client-order identifier. Match acknowledgments, partial fills, cancel/replace events, rejections and final positions to the venue.

An ambiguous order timeout is not proof that nothing executed. Query order status and reconcile fills before resubmitting. Binance specifically documents an HTTP 503 variant for which execution status is unknown and recommends verification before retrying. [1] All retry and restart tests must demonstrate that the same intent cannot create duplicate exposure.

### 4. Risk sizing, collateral and protective exits

Preserve the tested planned-loss budget rather than multiplying account notional by the leverage setting. For a linear instrument, a simplified sizing constraint is:

```text
planned_trade_loss = account_equity * approved_risk_fraction
quantity <= planned_trade_loss / (stop_distance_per_unit + cost_reserve_per_unit)
notional = quantity * entry_price
account_exposure = notional / account_equity
```

The executable size must also obey remaining daily/weekly risk, portfolio-wide gross exposure, instrument grids, liquidity, margin and collateral constraints. This is a design sketch, not a replacement for the saved engine or a calibrated live risk model.

Contract leverage changes required initial collateral; it does not create an edge. Exchange brackets can limit the permitted leverage at a given notional. [2] A very high isolated-leverage setting can liquidate the position before the strategy's stop if allocated collateral is inadequate, even when notional/account equity appears small. The live risk calculation must place the liquidation boundary beyond the stop plus an explicit stress buffer and reserve enough collateral. No stop provides a guarantee against gaps, outages or liquidation.

The current original engine supports a cap of at most 20x and one open position. It does not implement a verified two-sleeve shared account or the claimed 40x/50x/100x/500x variants. Do not remove its validation or copy positions into multiple accounts and call that the same strategy.

Protective orders must match the venue's current order types and position-mode semantics and be reconciled to actual filled quantity. Plan explicitly for a filled entry whose protective order is rejected. Do not assume that killing a local Python process removes an exchange position or its pending orders.

### 5. State, monitoring and shutdown

Persist balances, positions, orders, fills, per-sleeve ownership, signal deduplication, UTC day/week equity bases and circuit states. On restart, reconcile with the venue before allowing entries. Restarting must not reset loss limits or losing-week statistics. Monitor rejected orders, stale data, mismatched quantities, missing protection and risk-limit breaches.

An emergency sequence must stop new entries, reconcile actual exposure, handle entry orders, preserve protection while exposure remains, and use the venue's approved risk-reducing close procedure. Confirm flat positions and no exposure-increasing residual orders before declaring shutdown complete. No such shutdown adapter exists in this revision.

### 6. Staged acceptance before a live launch command is documented

First require a reproduced and independently audited variant. Then require read-only current-data parity, paper or test-environment order-lifecycle tests, duplicate/partial-fill/reconnect tests, collateral and liquidation checks, and explicit operator-approved limits. Test-environment success validates some mechanics, not live fills or expected returns. Any production launch command must belong to that separately reviewed release and identify its exact strategy/configuration, mode, account and risk budget.

This list does not authorize a production launch. **Current status remains NO LIVE LAUNCH COMMAND.**

## Credentials and public repository hygiene

This public repository must not store keys, API secrets, seeds or private account data. Use an appropriate local/managed secret store for a future adapter, separate test and production credentials, and the minimum venue permissions needed; keep withdrawal permissions disabled where supported. No present command needs a key.

A leaked key must be revoked or rotated at its provider. Removing the visible file or adding it to `.gitignore` is not enough, because Git history and other copies can retain it. GitHub documents these exposure limits and recommends revocation/rotation first. [3]

## Sources and scope

These official sources were checked on 2026-09-22 UTC. They inform the missing-component checklist; they do not establish that this repository implements those APIs or that the operator is eligible for the venue.

[1] Binance USD-M Futures General Info, execution-status-unknown handling: https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/general-info

[2] Binance, How to Change an Open Position's Leverage via API, leverage and notional brackets: https://www.binance.com/en/academy/articles/how-to-change-an-open-position-s-leverage-via-api

[3] GitHub, Removing sensitive data from a repository: https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository
