[![make.fun · gta6-trophy-rarity-forecast-01](https://make.fun/badge/gta6-trophy-rarity-forecast-01.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01)
[![rank](https://make.fun/badge/gta6-trophy-rarity-forecast-01/attnk2-oss/saena-rarity/rank.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01)
[![reward](https://make.fun/badge/gta6-trophy-rarity-forecast-01/attnk2-oss/saena-rarity/reward.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01)

Built for the [gta6-trophy-rarity-forecast-01 bounty](https://make.fun/bounty/gta6-trophy-rarity-forecast-01): forecast how many GTA VI players earn each trophy in week one.

# gta6-trophy-rarity-forecast-01

Offline forecaster for every GTA VI PS5 trophy on Exophase. For each case, it
reads `p*.in` from the input directory and writes a matching `p*.out` JSON file
with five earn-rate quantiles per trophy.

The model forecasts holders divided by tracked players. Tracked growth is fit
in log space against `log1p(hours)`, then damped toward the target. Each
trophy's holder series is fit over its recent tail when enough refresh points
exist; sparse trophies use a rate-dependent slope prior. Forecast uncertainty
is widened in logit space for holder-fit residual error and the target horizon,
producing sorted quantiles clamped to `0.01..99.99` percent. All arithmetic is
local, deterministic Python 3.13 stdlib code.

Run with environment variables:

```sh
MAKEFUN_INPUT_DIR=/input MAKEFUN_OUTPUT_DIR=/output python3 main.py
```

Or pass directories as arguments, with `/input` and `/output` as defaults:

```sh
python3 main.py /input /output
```
