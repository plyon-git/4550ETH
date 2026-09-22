# Daily IV, one trade per UTC day

See [daily_iv_v7](../daily_iv_v7/README.md), its [results](../daily_iv_v7/RESULTS.md), and [reproduction instructions](../daily_iv_v7/USERINSTRUCTIONS.md).

The BTCUSDT and ETHUSDT scheduled cases each complete1,826 historical trades, one on each UTC day of the five-year window, with same-day exits. A distinct conditional wall-only test caps entries at one/day and reports skipped days. This replaces neither the original45.50% baseline nor the existing V4 order service. No V7 live orders are submitted; the return target is not claimed achieved.

Owner of project-specific source and reporting: Parrish Lyon. Third-party rights remain applicable.
