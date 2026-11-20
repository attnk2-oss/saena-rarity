# gta6-trophy-rarity-forecast-01

Offline forecaster for every GTA VI PS5 trophy on Exophase. It reads a case at
`/input/<id>.in` and writes five earn-rate quantiles (0.01..99.99%) to
`/output/<id>.out`.

The model decomposes earn rate as holders / tracked, extrapolates both with a
decaying power law, adds Poisson granularity for small counts, and widens a
logit-space uncertainty band for horizon and refresh risk.

Run with Python 3.13 stdlib:

```sh
MAKEFUN_INPUT_DIR=/input MAKEFUN_OUTPUT_DIR=/output python3 main.py
```

The CLI also accepts input and output directories as arguments (defaults
`/input` and `/output`). Output is deterministic.
