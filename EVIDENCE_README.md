# Baseline proof and exit-target comparison

Owner of project-specific work: **Parrish Lyon**. See `OWNERSHIP.md`. The original `baseline-45-50` branch and original strategy sources, configuration and parameters are unchanged. This evidence addition supersedes the original README's statement that the market input and full reference ledgers are absent from GitHub.

## Results: change only `target_r`

All cases use exactly the same ETHUSDT input, unchanged engine, 15-minute breakout signal, 192-bar lookback, volume multiplier 1.0, 2.5-ATR stop, 1% planned account risk, execution assumptions and evaluation interval. Only the profit target changes. Each account starts at 10,000 USDT. The simulation is rerun sequentially: exits, subsequent entries, account equity, risk circuits and compounding are recalculated rather than relabeling the original trades.

Evaluation: **2025-06-02 00:00 UTC to 2026-06-01 00:00 UTC, exclusive**, exactly 52 full Monday weeks / 364 days.

| Target | Net return | Geometric weekly | Trades | Net win rate | Worst week | Losing-week streak | Conservative intrabar drawdown |
|---|---:|---:|---:|---:|---:|---:|---:|
| Original 4R | +45.504026% | +0.723825% | 222 | 31.531532% | -3.976384% | 5 | 13.691380% |
| 1.75R | -4.266457% | -0.083814% | 311 | 39.871383% | -3.958450% | 5 | 16.599435% |
| 2R | +3.022254% | +0.057276% | 293 | 36.860068% | -3.958409% | 4 | 19.202136% |

Win rate uses positive trade P&L after simulated fees and funding. The configured target is not the realized average win/loss ratio: those ratios are 2.774979, 1.470280 and 1.741987, respectively. Nominal leverage cap remains 20x, but maximum actual entry notional/account equity is approximately 1.817x in all three cases.

## What supports the original +45.504026%?

```
Starting equity                 10,000.00000000 USDT
Gross realized trading P&L      +6,497.44498000 USDT
Entry and exit commissions      -1,874.03913146 USDT
Net funding paid                   -73.00324485 USDT
Ending equity                  14,550.40260369 USDT
Return = ending / starting - 1 = 45.5040260369%
```

Every original trade is included in `results/breakout_trades_timestamped.csv`, plus the original-format `results/breakout_trades.csv` and `.csv.gz`. The complete 524,160-minute equity reference is in `results/breakout_equity.csv.gz`; daily and weekly summaries are also included. All 826 trades across the three simulations appear in `results/exit_target_all_trades_timestamped.csv` with a target-R field. No losing trades are omitted.

**Timestamp precision:** entry times are simulated minute opens. Stop, target and liquidation fills can only be located within their minute bar; both bar-open and upper-bound timestamps are exported. They are not fabricated exact tick times. The ledger includes signal availability, side, quantity, prices, fees, funding, gross/net P&L, initial stop/target, realized R, exit reason and post-trade balance.

The original recorded metrics reproduce. The independent audit reconstructs every minute's open and close equity from trade cash flows, quantities, mark prices and funding. Local maximum discrepancy was below 4e-11 USDT. These are numerical reconstruction checks under a simulation, not evidence of live fills or future profitability.

## Monthly and annual comparison / conditional publication

`results/exit_target_monthly_comparison.csv` contains mark-to-market calendar-month returns, not only closed-trade P&L. June 2025 is partial; July 2025 through May 2026 are 11 complete months. The 2R case beats 4R in only **4 of those 11 complete months**, or 5 of 12 segments including partial June. Its total return and annualized equivalent are also lower. Therefore **no `4550 (x%gain)` 2R strategy subfolder is created**. Rejected diagnostics remain in shared comparison evidence, not a promoted strategy folder.

A 52-week interval is 364 days. It is not a complete 12-calendar-month or calendar-year YoY test. `exit_target_calendar_year_segments.csv` labels both calendar-year segments as partial. Annualized equivalents in the JSON use 365.2425 days and are explicitly extrapolations, not additional historical observations.

## Reproduce from this repository

Use Python 3.13 with `numpy==2.3.5`, `pandas==2.2.3`, and `numba==0.65.1` (the tested numerical environment).

```sh
python -m pip install numpy==2.3.5 pandas==2.2.3 numba==0.65.1
python reproduce_saved.py
python tools/publish_evidence.py
```

`data/aligned_data.npz` is the exact original input: SHA-256 `cdecadabcd6152bca34bf322c3e140924ec13b51fdfc88e42b8ab650984ed6aa`. The publisher also knows how to recover it byte-for-byte from the previously sourced extended-history artifact. It refuses unexpected input or source hashes. `EVIDENCE_SHA256.json` records saved-file hashes; `INDEPENDENT_LEDGER_AUDIT.json` and `CONDITIONAL_PUBLICATION_GATE.json` record the numerical checks and folder decision.

Source artifact: GitHub Actions run `35677890814`, artifact `10673972607`, `eth-history-observed-with-mark-gaps`. Its extended input hash is `7156e32e9e3813e2ef041ca03e9a30cb9f7246ea3b22e6549e09d2f750e6388c`. Only the original complete 649-day slice is used here. The extended source has explicit missing mark minutes outside that slice; no new extended-period strategy result is claimed.

## Limitations

These are hypothetical historical returns, not actual transactions. Fees of 5 bps per side, 2 bps adverse slippage per side, a 1% prior-minute volume cap and a fixed 1% maintenance-margin approximation are preserved assumptions, not verified account fee tiers, executable depth or historical margin schedules. Historical funding is included. Same-bar ambiguities use the original conservative engine ordering.

The 4R variant was highlighted after evaluation results were known. Its earlier validation segment lost 4.8039%; the calendar period also overlaps previous project research. This is not an untouched holdout or proof of an investable edge. Higher win rate alone does not establish higher expectancy. There is no live order submission, exchange credential, trained learner or autonomous trading platform in this baseline.

The requested **60.37% / 52w** and **102.02% / 93w** variants have not been matched to source, parameters or ledgers in the retrieved material. Their win rates and RR are unverified. They are tracked in `UNRESOLVED_VARIANTS.json`; no performance-named folders or substituted code are invented for them.
