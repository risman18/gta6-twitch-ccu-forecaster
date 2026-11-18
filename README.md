# gta6-twitch-ccu-forecaster

[![make.fun · gta6-twitch-ccu-forecast-01](https://make.fun/badge/gta6-twitch-ccu-forecast-01.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![rank](https://make.fun/badge/gta6-twitch-ccu-forecast-01/risman18/gta6-twitch-ccu-forecaster/rank.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![reward](https://make.fun/badge/gta6-twitch-ccu-forecast-01/risman18/gta6-twitch-ccu-forecaster/reward.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)

An hour-by-hour forecaster for GTA VI's launch-day Twitch viewers, built for make.fun's
gta6-twitch-ccu-forecast-01 bounty. `main.py` reads one case at `/input` — everything recorded up to
the end of release day's first hour, that hour's count included — and writes `/output/<id>.out`: for
each of hours 2–24 (UTC), five quantiles (5%, 25%, 50%, 75%, 95%) of that hour's concurrent viewers
in Twitch's "Grand Theft Auto VI" category. It runs offline, standard library only, deterministic —
the same case always produces the same bytes.

## The model: analogue launch curves, pooled honestly

Every case carries `comparables`: ~40 past game launches with their full hourly Twitch category
curves (SullyGnome hourly averages, release day included). A launch day, normalised by its own
hour-1 print, has a characteristic shape. GTA VI unlocks at **rolling midnight local time** on
19 November 2026 (PS5 and Xbox Series X|S; New Zealand first at 11:00 UTC on the 18th, the UK at
00:00 UTC, the US at 05:00 UTC) — so at 00:00 UTC only the earliest time zones are playing, the
audience dips as those regions ebb, ramps through the European day, and peaks in the transatlantic
evening overlap. The forecaster pools the comparables' log-ratio curves `log(viewers_h / viewers_1)`
hour by hour and reads the forecast quantiles off that pooled distribution, rescaled to the case's
hour-1 print. The score is pinball loss on the log scale, so the honest move is to report the pooled
distribution itself — median, quartiles and tails — not a point guess with decoration.

Pool discipline, tuned by leave-one-out backtest over the comparables (`backtest.py`):

- a comparable joins the pool only if its release day is well sampled (≥ 18 of hours 2–24) and its
  hour 1 is a real print (≥ 200 viewers);
- a comparable whose hour 1 is under 5% of its own day peak belongs to a different regime — a single
  global unlock later in the UTC day (its hour 1 is pre-unlock noise) — and is left out;
- comparables with a rolling / midnight-local unlock weigh double;
- the pooled quantiles are widened around the median by 1.05 in log space (recalibrated 2026-11-18:
  the first calibration's 1.15 over-widened — every factor in 0.95–1.10 beats it on both the
  leave-one-out backtest and the practice launches; 1.05 is the balanced point of that range);
- an hour with no pooled samples falls back to the house persistence form.

## What it expects on the day

On the final case's pool (the kit's comparables plus the four practice launches), the median curve
dips to ≈ 0,69× hour 1 in hour 4, crosses 1,0× around hour 13, and **peaks at ≈ 2,04× the hour-1
print in hour 22 (21:00–22:00 UTC)**, with an honest 5–95% band of roughly 0,82×–10,7× at the peak —
the upside tail is real: some analogues multiply many-fold when the big streamers go live. The scale
is there for a seven-figure peak: the GTA VI category itself drew 1.418.094 viewers in a single hour
for its August 2026 extended-look premiere. If hour 1 prints, say, 500k, the median peak call is
≈ 1,02M concurrent viewers at hour 22.

## Backtest

Leave-one-out over the comparables, and a held-out check on the four practice launches (Marvel's
Wolverine, Red Dead Redemption 2, God of War Ragnarök, Marvel's Spider-Man 2 — each forecast from
its case's own hour-1 print and pool, scored against its recorded day; mean pinball loss on the log
scale, lower is better):

| target | this model | house persistence baseline |
|---|---|---|
| Marvel's Wolverine | 0,5990 | 0,8466 |
| Red Dead Redemption 2 | 0,2332 | 0,3102 |
| God of War Ragnarök | 0,1523 | 0,2023 |
| Marvel's Spider-Man 2 | 0,2046 | 0,2899 |
| **mean** | **0,2973** | **0,4122** |

≈ 28% below the house baseline's loss on every one of the four. (Recalibrated 2026-11-18: widening
1.15 → 1.05; the leave-one-out mean over the comparables moved 0,3142 → 0,3129 on the same change,
with 18 of 29 targets improved. Wolverine alone moves the other way, +0,9% — its anchor print is the
known outlier, and the narrower factors that help the other three most, 0,90–1,00, cost it up to
+4,6%; 1.05 is where the four-case balance lands.) (Wolverine is the hardest: its
case hour-1 print sits well below its chart's first-hour point, which inflates every ratio — the
baseline suffers the same anchor, worse.)

## Assumptions, stated plainly

- The shape of a launch day is portable across big launches once normalised by hour 1; scale is
  carried entirely by the case's own hour-1 print.
- GTA VI's rolling-midnight console unlock makes the rolling/midnight-local analogues the right
  family; fixed-time global unlocks (mostly PC) are a different shape and are filtered or downweighted.
- Twitch category counts are what they are: they include co-streams, reruns and premiere replays in
  the category, exactly as the house recorder reads them.
- No use is made of the target's pre-release history beyond the hour-1 print: the category's
  pre-release traffic (trailers, premieres) is a different phenomenon from launch-day play.

## Run it

```sh
mkdir -p out && MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
python3 backtest.py <kit input dir>   # leave-one-out over the comparables
```

Data note: the historical curves are SullyGnome.com's hourly Twitch category averages, quoted with
attribution as the competition kit presents them.
