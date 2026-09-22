# V7: one daily IV-based trade on BTC and ETH

Project owner: Parrish Lyon. Historical simulation, not real account fills.

**Both scheduled primaries complete 1,826 trades: one trade on every UTC day of five calendar years. Each market independently exceeds 1,000 trades. No position is carried into the next day.**

Actual daily BTC/ETH DVOL is scaled to a one-day range using sqrt(365). A five-reading IV average is smoothing, not a five-day forecast. These are IV-derived range boundaries, not option-strike dealer walls.

## Five-year scheduled daily results

| Market | Trades | Skipped days | Five-year net | CAGR | Net WR | Worst full week | Longest losing-week streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| BTCUSDT | 1826 | 0 | -88.00% | -34.56% | 49.84% | -11.78% | 15 |
| ETHUSDT | 1826 | 0 | -75.77% | -24.69% | 46.28% | -8.32% | 10 |

Evaluation: 2021-09-01 to 2026-09-01 exclusive, 1,826 days. Each account begins with 10,000 USDT. Enter once at 00:02; stop, target or 23:59 scheduled exit; no second entry after an early exit.

BTC selected opening-movement continuation with historical mean one-day IV-normalized walls. ETH selected seven-day directional momentum with a five-observation mean of daily IV. Both use 2% planned equity risk and a 5x exposure cap, not 150x account exposure. These settings were selected on the pretest validation window; that window is short and the full calendar has prior project exposure.

## Five successive annual returns

| Market | Sep2021-Aug2022 | Sep2022-Aug2023 | Sep2023-Aug2024 | Sep2024-Aug2025 | Sep2025-Aug2026 | Arithmetic annual average |
|---|---:|---:|---:|---:|---:|---:|
| BTCUSDT | +23.18% | -67.06% | -40.08% | -35.17% | -23.84% | -28.59% |
| ETHUSDT | -16.21% | -32.22% | -31.21% | -18.90% | -23.51% | -24.41% |

## Separate 250-week accounts

| Market | Days / trades | Net return | CAGR |
|---|---:|---:|---:|
| BTCUSDT | 1750 / 1750 | -87.13% | -34.81% |
| ETHUSDT | 1750 / 1750 | -73.46% | -24.18% |

250 weeks is 1,750 days, from 2021-11-15 to 2026-08-31 exclusive. It is not five calendar years. These are separate account reruns, not a suffix cut out of the five-year account.

## Wait for the wall: at most one entry per day

| Market | Completed trades | No-trade days | CAGR | Net WR |
|---|---:|---:|---:|---:|
| BTCUSDT | 1628 | 198 | -30.29% | 46.68% |
| ETHUSDT | 1352 | 474 | -54.68% | 32.25% |

These are separate conditional rejection tests. Both exceed 1,000 trades, but do not pretend to enter on every day. All skipped days and their reason codes are exported.

## Additional prior-only adaptive selection

This extension was specified after viewing the fixed-policy results. Every seven UTC days, choose using at most126 prior fully matured daily returns, not current/future outcomes. Account equity does not reset. This is not a fresh untouched holdout.

| Market | Trades | CAGR | Five-year net |
|---|---:|---:|---:|
| BTCUSDT | 1826 | -24.27% | -75.09% |
| ETHUSDT | 1826 | -21.82% | -70.79% |

## Cost controls

Base case: 5bps commission plus2bps adverse fill slippage per side, actual historical funding, prior-volume cap, order-grid assumptions and fixed1% maintenance. Costs are neither omitted nor blamed without a comparison.

| Market | Zero-fee/zero-slippage CAGR | User $5 round-trip equivalent CAGR |
|---|---:|---:|
| BTCUSDT | +5.34% | -22.87% |
| ETHUSDT | -0.42% | -17.02% |

The $5 case uses the quoted 9,895.212-USDT notional to derive a proportional round-trip commission and retains2bps slippage per side. Zero fees/slippage retains funding and price-grid rounding. Every case resimulates the compounded account.

**No tested daily case meets 65% CAGR or65% arithmetic average annual return with1,000 trades.**

## Evidence and limits

All 42 published case audits passed, covering 75,683 trade rows across separate simulations. Maximum independently reconstructed daily-equity discrepancy: 9e-11 USDT. Every trade has timestamps, initial IV/walls, size, fees, funding, P&L and a same-day exit. Every calendar day, including no-trade days, is present.

The audits separately locate the earliest stop/target crossing in minute OHLC, verify IV availability before entry, prohibit duplicate daily entries and reconstruct account cash. Intraminute timestamps are bounded, not fabricated exact fills. Mark gaps, fee/impact/margin assumptions and prior research exposure remain limitations. The intrabar drawdown is a conservative bound; daily drawdown is also reported.

This addition is research only. Existing live-execution code and all original strategy/report folders remain unchanged. It does not establish a live profitable strategy. Read README.md and USERINSTRUCTIONS.md for definitions, exact inputs and reproduction.
