# Methodology, timing and source boundaries

## Options IV is not a dealer wall

Deribit DVOL is annualized options-derived volatility. V5 converts one-/five-day averages in variance space to daily sigma: `sqrt(mean((DVOL/100)^2))/sqrt(365)`. Bounds are session opening price multiplied by `exp(+/- width*sigma)`. RV20 and average-range sources are explicit price-derived proxies. SPY/VIX and QQQ/VXN separately use a disclosed `sqrt(252)` session convention. These expected-move estimates do not reveal strike-level dealer inventory, prove hard price caps or reconstruct the proprietary Milk formula.

Daily DVOL closes are admitted only after their UTC day finishes plus a one-minute publication allowance. Bands are frozen at00:00 or08:00UTC. At00:00 that allowance deliberately uses an older published candle. Price/range/trend features use preceding sessions only. A current partial session does not require its future completed high, low or close. Source availability timestamps accompany every signal.

Rejection: a completed candle pierces a band and closes back inside toward the anchor. Breakout: a confirmed close outside. Entry is no earlier than the next minute. Targets are a precomputed pivot or R-based price, never future realized extrema. The screenshot motivates a hypothesis around the upper seller/IV region; it supplies neither a full formula nor an as-of historical archive.

## Search and chronological selection

Crypto development:2020-02-01 to2021-06-01. Validation:2021-06-01 to2021-08-25. Evaluation:2021-09-01 to2026-09-01 exclusive. Actual DVOL begins2021-03-24; earlier missing IV was not invented. Development ranks candidates per source; validation chooses risk and finalists; choices are frozen before each stage's test-return computation.

Adaptive: every13weeks, score only preceding26weeks within the development-selected shortlist. Require>=15past trades, positive past net return, no liquidation and <=35% past drawdown. Cash otherwise. Continuous account equity and existing exits persist through selection changes.

Learned: fixed actual-IV rejection setup, rolling730-day training,13-week refits, >=100matured labels and24-hour extra embargo.100 histogram boosting trees, depth3, minleaf30, L2=20, learning rate.04, no early stopping. Available features include price/session position, IV/RV and observed taker flow. Labels are simulated future net R used solely for training after maturity; inference never reads them. Three fixed thresholds are disclosed as diagnostics, not selected after evaluation. Portable numerical trees are compared with fitted-estimator predictions.

The research calendar has been studied before. Adaptive and learned extensions follow earlier fixed-stage results. Local chronological rules do not erase global research exposure, model selection risk or multiple-testing risk.

## Costs and account exposure

Crypto base:10,000USDT start; <=5x notional/account equity;0.5/1/2% planned loss;4%daily and8%weekly circuits;1%prior-minute volume;3entries/day;15-minute cooldown;24-hour timeout;5bps commission and2bps adverse slippage per side; historical funding. Stated price/quantity/minimum-notional grids are assumptions. Losses are never clipped and stops can overshoot.

150x contract leverage is not treated as150x account exposure. Margin and account-equity denominators differ. The user-supplied5-dollar display has not been verified as an actual fee receipt, or as one-way versus round-trip. Zero-commission/slippage diagnostics retain funding and rerun sizing and account state. Gross price P&L in an already costed ledger still includes its fill-price slippage. Do not conflate these measures.

Five calendar years have1,826days;250weeks have1,750days. CAGR, arithmetic average annual returns and worst individual/rolling-year returns are separate. Each ledger is independently reconciled from gross P&L, commissions, funding and marked equity. Every losing/flat period remains.

## Data repair and execution limits

The V4 repair of74 zero-volume minutes per market on2024-10-28 from actual checksum-matching aggregate trades is retained with provenance. Remaining raw mark gaps are NaNs; in simulation only, prior mark close replaces missing open/close, with separately sourced15-minute bounds where available, otherwise an explicit +/-5% sensitivity envelope. These modeled marks are not represented as exchange observations. Historical tiered liquidation, exit capacity, order-book impact and queue position are not fully reconstructed.

SPY/QQQ use actual daily OHLC and previous published VIX/VXN. Entry levels are fixed at session open; limit price must be penetrated by one cent; unknown daily event order is resolved adversely. Targets are credited only when the closing price proves a crossing after entry. Positions are flat at close. This is a conservative screening model, not live or five-minute execution evidence.4x account notional is an assumption;20x is explicitly unverified. No passive multi-year purchase, dividends or overnight financing return is added.

## Primary documentation

- Deribit historical IV API: https://docs.deribit.com/api-reference/market-data/public-get_volatility_index_data
- DVOL definition/launch: https://insights.deribit.com/exchange-updates/deribit-launches-volatility-index/
- CBOE index-volatility historical data: https://www.cboe.com/tradable-products/vix/vix-historical-data
- CME options volatility/scaling: https://www.cmegroup.com/education/courses/introduction-to-options/discover-options-volatility
- Binance futures fee calculation: https://www.binance.com/en-ZA/support/faq/detail/360033544231

Downloaded snapshots carry URL/SHA receipts. Identity checks do not certify every market record's correctness. No proprietary image/indicator is redistributed and no V5 strategy was activated for actual trading.
