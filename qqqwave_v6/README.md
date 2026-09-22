# QQQWave-inspired V6

Project-specific research/software: **Parrish Lyon**. Third-party market data, software and proprietary product rights remain with their owners. No affiliation with or exact replication of QQQWave is claimed.

A transparent, causal version of the visible **200 daily sessions / five forward sessions / weekday matching** architecture. It exports historical high/low/terminal distributions, frozen price levels, separate touch-event counts and sequential stop/target trade tests. It is not a rebranded indicator win-rate or a graph repainted using later prices.

**No tested 65%-annual strategy was established.** [RESULTS.md](RESULTS.md) explains the screenshot's count arithmetic, the new QQQ event results, crypto trades, costs and five-year/250-week evaluations. [ASSESSMENT.json](ASSESSMENT.json) records machine-readable outcomes. Results are simulations, not live fills. Existing 4550/V4/V5 source and data remain unchanged.

## Run the self-contained empirical panel

Install `requirements.txt`, then from this directory:

```sh
python panel.py --daily-input results/QQQ/daily_inputs.csv --out my_qqq_panel
python panel.py --daily-input results/ETHUSDT/daily_inputs.csv --out my_eth_panel
```

The output contains `PANEL.json`, `price_odds.csv` and every matured sample. These are historical snapshots at the last supplied session, not current quotes or live trade recommendations. Future data cannot alter an already defined origin's levels. An empirical 97.37th-percentile target is not a verified 97.37% future probability.

## Reproduce the actual research

```sh
python bootstrap_engine.py
python -m pytest -q
python run.py --data-root ../execution_v4/data --context-root context
python finish.py --verify-reference --zip-out ../QQQWave_V6_Research.zip
```

The minute inputs are the exact V4 repaired ETH/BTC/XRP release datasets, not repeated in this ZIP. The included daily inputs suffice for panel/event reproduction; minute trade tests need the three larger NPZ files. Source hashes and setup are in [docs/USERINSTRUCTIONS.md](docs/USERINSTRUCTIONS.md).

The source is empirical/statistical, not a newly trained neural network or the missing 60.37/102.02 variants. It does not call a broker. The original V4 execution service has not been changed or armed with this unvalidated strategy.
