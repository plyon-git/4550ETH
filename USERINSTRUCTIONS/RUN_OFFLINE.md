# Run the preserved program offline

Owner: Parrish Lyon. These instructions operate on the committed 45.50% baseline and existing target-R comparisons. They do not run the unrecovered 60.37% or 102.02% variants.

## 1. Obtain a clean working copy

Install Git and Python 3.13 for your operating system, then open a terminal:

```sh
git clone https://github.com/plyon-git/4550ETH.git
cd 4550ETH
git branch --show-current
git rev-parse HEAD
```

Use `main`: it contains the complete evidence added after the immutable `baseline-45-50` snapshot. GitHub's **Code > Download ZIP** is an alternative; extract it and open the extracted root folder. You must see `SAVED_DIAGNOSTIC.json`, `reproduce_saved.py`, `data/`, and `v3/`.

Existing clones should first check `git status`. Preserve any local changes before updating. On a clean checkout of `main`, `git pull --ff-only` updates without rewriting history. Do not use `git reset --hard` to discard work.

## 2. Create an isolated Python environment

### macOS or Linux

```sh
python3.13 -m venv .venv
source .venv/bin/activate
python --version
python -m pip install -r USERINSTRUCTIONS/requirements-reproduction.txt
```

### Windows PowerShell

Activation is not required; use the environment's interpreter directly:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -m pip install -r USERINSTRUCTIONS/requirements-reproduction.txt
```

For the commands below, Windows users can substitute `.\.venv\Scripts\python.exe` for `python`. No PowerShell execution-policy change is necessary.

The recorded numerical environment is Python 3.13.5, NumPy 2.3.5, pandas 2.2.3 and Numba 0.65.1 on Linux. These are pinned for reproduction, not claimed to be the newest versions. The baseline imports those three numerical packages. The broader root dependency snapshot includes libraries used by other research; their presence does not mean this baseline trains a model. macOS and Windows instructions have not been executed on native macOS or Windows in this verification.

Initial cloning and package installation need Internet access. Once files and dependencies are installed, the baseline reproduction runs offline. No paid data service, exchange account or API key is used by these commands. Successful installation depends on compatible package wheels and your local platform.

## 3. Check installation before running

```sh
python USERINSTRUCTIONS/check_installation.py
```

Expected: `baseline_files_verified: true`, `live_order_submission: false`, exit code 0. This verifies pinned identities for the original configuration, protocol, source and historical input and checks that the three reference ledgers are present. It does not inspect every optional research file, rerun the simulation, verify a broker account, or certify live readiness.

A `MISSING` entry means a required file is absent. A `HASH_MISMATCH` means it differs from the frozen reference. Do not change a hash to make a check pass. Restore the exact file from the evidence commit or retain modifications as a separately named research version.

`data/aligned_data.npz` must have SHA-256:

```text
cdecadabcd6152bca34bf322c3e140924ec13b51fdfc88e42b8ab650984ed6aa
```

## 4. Reproduce every original trade

```sh
python reproduce_saved.py
```

The program prints JSON and writes to `reproduced/`. Expected verification includes:

```json
{
  "matched": true,
  "trade_rows": 222,
  "minute_equity_rows": 524160,
  "equity_series_checked": 3,
  "weekly_rows": 52
}
```

The full output has additional fields. The original result is 10,000 USDT to 14,550.402603689372 USDT, or +45.5040260369%, from 2025-06-02 00:00 UTC to 2026-06-01 00:00 UTC exclusive. The period contains 364 days. All 222 trades and 52 weekly returns must match, including losing trades. A nonzero process exit or an assertion failure is a failed reproduction, not an acceptable near match to ignore.

`reproduced/REPRODUCTION_VERIFICATION.json` is the verification receipt. `reproduced/breakout_signal.npz` contains historical signal arrays, not ML weights or current buy/sell instructions. `reproduced/breakout_trades.csv.gz` contains simulated trades, not broker fills. Reproduction writes derived output only; it does not edit the baseline strategy or place orders.

## 5. Reproduce the target comparison and independent ledger audit

```sh
python tools/publish_evidence.py
```

This existing script reruns the same strategy with only `target_r` changed to 4.0, 1.75 and 2.0. It writes derived evidence under `results/` and updates `EVIDENCE_SHA256.json`; it does not submit Git commits by itself or rewrite the original strategy. Run in a clean working copy when preserving local research outputs matters.

Expected net returns: 4R +45.504026%; 2R +3.022254%; 1.75R -4.266457%. The 2R promotion gate remains false. No performance-named 2R strategy directory is justified by those results.

| File | What to inspect |
|---|---|
| `results/breakout_trades_timestamped.csv` | All 222 original trades, UTC times and execution-time precision |
| `results/breakout_equity.csv.gz` | Complete minute equity reference |
| `results/EXIT_TARGET_COMPARISON.json` | Aggregate metrics for each target |
| `results/exit_target_all_trades_timestamped.csv` | All 826 trades across the three independent simulations |
| `results/exit_target_monthly_comparison.csv` | Mark-to-market monthly returns, with partial months flagged |
| `results/INDEPENDENT_LEDGER_AUDIT.json` | Cash-flow and minute-equity reconstruction checks |

A minute candle cannot identify the exact second of an intrabar stop or target fill. Use the exported interval/precision fields. Do not represent simulated timestamps as exchange confirmations.

## 6. Run the manual's diagnostic tests

```sh
python -m unittest discover -s USERINSTRUCTIONS -p 'test_*.py' -v
```

These tests cover the installation diagnostic, missing/changed files, path confinement and its unconditional lack of a live mode. They are not strategy-profitability or broker-integration tests.

## Troubleshooting and stopping

**Module not found:** use the interpreter inside the environment where the pinned packages were installed. **Unsupported dependency wheel:** use a supported Python 3.13 installation and check your package manager's error; do not silently switch package versions and claim an exact reproduction. **Missing full data or ledgers:** obtain current `main`, not the old smaller source-only archive. **Leverage above 20 rejected:** expected behavior of the unchanged baseline, not a setting to bypass. **No live signals appear:** expected; this is a finite historical program and exits when finished.

Ctrl+C interrupts an offline run. It cannot cancel or close an exchange position, because this release has no exchange connection. Partial derived output from an interrupted run is not a successful verification. Running it again recomputes the complete result.
