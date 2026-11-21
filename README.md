[![make.fun · gta6-trophy-rarity-forecast-01](https://make.fun/badge/gta6-trophy-rarity-forecast-01.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01)
[![rank](https://make.fun/badge/gta6-trophy-rarity-forecast-01/attnk2-oss/saena-rarity/rank.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01)
[![reward](https://make.fun/badge/gta6-trophy-rarity-forecast-01/attnk2-oss/saena-rarity/reward.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01)

Built for the [gta6-trophy-rarity-forecast-01 bounty](https://make.fun/bounty/gta6-trophy-rarity-forecast-01): forecast how many GTA VI players earn each trophy in week one.

# Rarity forecast v3

This entry forecasts each GTA VI trophy's earn rate as a refresh-step band around
the newest Exophase observation. Between player-count refreshes, Exophase repeats
its rates, so the latest read is the strongest starting point rather than a
series to extrapolate.

The forecaster detects reads where `players_tracked` changes. From the last
observed step it measures a small, positive log-rate drift and the typical time
between steps. That drift only tilts the last rate for the number of refreshes
expected before the target, with shrinkage and a cap. Uncertainty is a
log-space interval around the resulting median, widening with the square root
of the horizon and bounded at both ends.

## Run

```sh
python3 main.py [IN_DIR] [OUT_DIR]
```

`MAKEFUN_INPUT_DIR` and `MAKEFUN_OUTPUT_DIR` override the optional arguments;
the defaults are `/input` and `/output`. Every `p*.in` case produces a matching
`p*.out` file. Each output contains, in input order, one trophy object with its
`id` and five non-decreasing percent quantiles (`q05`, `q25`, `q50`, `q75`,
`q95`) rounded to four decimals and clamped to `0.01..99.99`.

The implementation uses only the Python standard library, is deterministic, and
performs no network access.
