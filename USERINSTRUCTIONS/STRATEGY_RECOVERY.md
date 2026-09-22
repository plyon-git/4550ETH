# Recovery status of the 60.37% and 102.02% claims

Owner: Parrish Lyon. Status: **exact source/result packages not recovered**. This is a recovery record, not a result report for either requested variant.

The earlier conversation described +60.37% over 52 weeks and +102.02% over 93 weeks as a balanced two-sleeve result. It also described a maximum four losing weeks and nominal leverage settings giving identical returns under risk-based sizing. These are recovered descriptions of prior assistant claims, not independently verified results. Sleeve definitions, weights, exact periods, WR, RR, model artifacts and executable code have not been identified. The two figures may be different evaluation windows of one configuration; two different algorithms must not be inferred from them.

## Sources inspected in this continuation

The current `main`, `baseline-45-50` and `research/history-recovery` refs were checked. The mounted continuation, V3 research, hyperscalping, preserved baseline, smaller baseline code and observed-history ZIPs were inventoried. A bounded scan of their small source/metadata files found no matching source/result package; isolated matching decimal substrings in unrelated P&L fields were not treated as those returns. Available Library searches were also attempted but did not recover a relevant variant bundle. This does not prove that the missing work never existed.

The historical-data artifact is a dataset, not the missing strategy. The separately archived V3 ML models belong to other experiments and cannot be presented as the learner for these claims. The original 45.50% rule is deterministic and does not use those fitted models.

## Required preservation package

Recover source/configuration and a reproducible result together. At minimum it must identify:

1. Exact commit/source hashes and every entry point required for feature building, training where used, signal generation, sizing, execution and reporting. Include both sleeves, weights and shared portfolio rules.
2. Exact data identity, venue/product, UTC start and exclusive end, warm-up, gaps, filtering when ETH is above 1,000 USDT, and handling of periods below the threshold. Define 52/93 weeks precisely rather than guessing from a label.
3. Every timestamped trade, fills versus simulated time bounds, costs, funding, sizes, reason codes, equity before/after, every daily/weekly/monthly period and the continuous equity series. Preserve losses and zero-activity periods.
4. Recorded net return, geometric weekly return, worst week, losing-week streak, net-of-costs win rate, configured target R by sleeve, realized payoff ratio, drawdown, actual exposure, nominal margin settings and selection/history-exposure limitations.
5. For an ML implementation, exact learner code, model weights, feature order, preprocessing, training/validation windows, label timing, seeds and versions. For a rule-based system, state `model_type: deterministic_rules` and `trained_model_artifacts: not_applicable`; do not invent a learning component.
6. An independent reproduction/audit and an explicit distinction between simulated execution and any separately tested live adapter.

A rounded percentage alone cannot recover an algorithm. Do not search until a different strategy coincidentally rounds to the same number and label it the original.

## Folder naming once the exact package is verified

Use the requested measured fields, populated only from that package:

```text
60.37pct_52w_<startUTC>-<endUTC>_WR-<verified-net-win-rate>_RR-<verified-target-spec>/
102.02pct_93w_<startUTC>-<endUTC>_WR-<verified-net-win-rate>_RR-<verified-target-spec>/
```

These are naming templates, not directories created by this change. Multiple sleeve targets must be encoded explicitly instead of claiming one RR. Each directory should contain `README.md`, configuration, source, data provenance, models when applicable, complete reports/ledgers, reproduction instructions and a manifest. Shared code may be included as an immutable snapshot or an explicitly pinned dependency; a mutable link to `main` is not an exact code archive.

The root [UNRESOLVED_VARIANTS.json](../UNRESOLVED_VARIANTS.json) remains authoritative for the unresolved status. No performance-named folders, made-up win rates, ML weights or fictitious trade ledgers are included in this manual update.
