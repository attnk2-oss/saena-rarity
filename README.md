# gta6-trophy-rarity-forecast-01

Offline forecaster for every GTA VI PS5 trophy on Exophase. It reads a case at
`/input/<id>.in` and writes five earn-rate quantiles (0.01..99.99%) to
`/output/<id>.out` as JSON.

The model decomposes earn rate as holders / tracked. Both the page's tracked
player count and each trophy's holder count are extrapolated to the target with
a decaying power law, with Poisson granularity for small holder counts and a
prior for zero-signal trophies. Quantiles come from a logit-space uncertainty
band combining fit, horizon, and Exophase-refresh risk. Output is deterministic.

Run with Python 3.13 stdlib:

```sh
MAKEFUN_INPUT_DIR=/input MAKEFUN_OUTPUT_DIR=/output python3 main.py
```

Directories may also be passed as arguments (defaults `/input` and `/output`).
