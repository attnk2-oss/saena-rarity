# gta6-trophy-rarity-forecast-01 entry

Forecasts, for every GTA VI PS5 trophy on Exophase, five quantiles of its
earn rate at the case's target, from the case's history alone (offline).

`main.py` reads `/input/<id>.in`, writes `/output/<id>.out`.

Model: decompose rate = holders / tracked, power-law extrapolation with a
decaying exponent on both, Poisson granularity for thin counts, and a
logit-space sigma floored so one Exophase refresh cannot blow the band.

Run: MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
