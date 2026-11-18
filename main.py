"""gta6-twitch-ccu-forecast-01 entry: an analogue-curve forecaster for GTA VI's launch-day Twitch viewers.

Model (fit entirely from the case file at run time; standard library only, no network, deterministic):

  Every case carries `comparables`: ~40 past game launches with their full hourly Twitch category curves
  (SullyGnome hourly averages, release day included). A launch day, normalised by its own hour-1 print,
  has a characteristic shape: for a console game that unlocks at rolling midnight local time, hour 1 UTC
  catches only the earliest time zones, the audience ramps as Europe and then the Americas unlock and
  wake, peaks in the 17:00-22:00 UTC overlap, and ebbs after. This program pools the comparables'
  log-ratio curves log(viewers_h / viewers_1), hour by hour, and reads the forecast quantiles off that
  pooled distribution, rescaled to the target case's hour-1 print:

    q_tau(h) = p1 * exp( Q_tau( { log(v_c,h / v_c,1) } ) ),   h = 2..24

  Pool discipline, tuned by leave-one-out backtest over the comparables and checked against the four
  practice launches (see backtest.py and README.md):

  - a comparable joins the pool only if its release day is well sampled (>= 18 of hours 2..24 present)
    and its hour 1 is a real print (>= 200 viewers);
  - a comparable whose hour 1 is under 5% of its own day peak is a different regime (a single global
    unlock later in the UTC day, e.g. a PC unlock at 17:00 UTC: its hour 1 is pre-unlock noise) and is
    left out — GTA VI is a rolling-midnight console launch, like the practice cases;
  - comparables whose unlock text describes a rolling / midnight-local unlock weigh double;
  - the pooled quantiles are widened around the median by a factor 1.15 in log space (the backtest's
    calibration: raw pooled quantiles run slightly narrow for a launch this size);
  - an hour with no pooled samples falls back to the house persistence form p1 * exp(z_tau * 0.15 *
    sqrt(h - 1)).

  The score is pinball loss on the log scale, so the median curve is the pooled median log-ratio and
  the bands are the pooled 5/25/75/95 log-ratio quantiles: the numbers below are the forecaster's
  honest beliefs, not a point guess with decoration.

How the grader runs it: `python3 -P -s /bot/main.py` (PYTHONHASHSEED=0) in python:3.13-slim, standard
library only. -P keeps this file's directory OFF sys.path, so the sys.path line below puts it back
first. Outside the grader's container, MAKEFUN_INPUT_DIR and MAKEFUN_OUTPUT_DIR stand in for /input
and /output:

    mkdir -p out && MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py

Output contract: for each <id>.in, write <id>.out = {"hours": [{"hour": h, "q": [q05, q25, q50, q75,
q95]} for h in 2..24]}, each q finite, > 0, <= 1e9, non-decreasing; at most 65,536 bytes.
"""

import json
import math
import os
import sys
from pathlib import Path

# The grader's -P leaves /bot off sys.path: put it back first, so a sibling module would import.
sys.path.insert(0, str(Path(__file__).resolve().parent))

INPUT_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))

# The quantile levels the contest scores, in the order each row lists them.
LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
# The standard normal's quantile at each level (only for the no-samples fallback).
Z = [-1.645, -0.674, 0, 0.674, 1.645]
# The fallback spread, in natural-log units per square-root hour (the house persistence form).
FALLBACK_SIGMA = 0.15

# Pool discipline (see the module docstring; tuned in backtest.py).
MIN_HOUR1 = 200          # a comparable's hour-1 print must be at least this to anchor a ratio curve
MIN_DAY_HOURS = 18       # and its release day must carry at least this many of hours 2..24
MIN_HOUR1_SHARE = 0.05   # hour 1 under this share of the day peak = a later global unlock, not rolling
ROLLING_WEIGHT = 2.0     # weight multiplier for rolling / midnight-local unlocks
SPREAD_SCALE = 1.15      # widen pooled quantiles around the median by this, in log space


def round2(x: float) -> float | int:
    """x rounded to 2 decimals, half up, as JavaScript's Math.round(x * 100) / 100 rounds it.

    A whole number comes back as an int, so json.dumps writes 1240 where JavaScript writes 1240.
    """
    scaled = x * 100
    whole = math.floor(scaled)
    if scaled - whole >= 0.5:
        whole += 1
    value = whole / 100
    return int(value) if value.is_integer() else value


def release_day_curve(comparable: dict) -> dict[int, float]:
    """hour (1..24) -> viewers for the comparable's release day, from its hourly points."""
    day = comparable["day_start"][:10]
    curve: dict[int, float] = {}
    for point in comparable.get("hourly") or []:
        stamp = point.get("from") or ""
        if stamp[:10] == day and point.get("viewers") is not None:
            curve[int(stamp[11:13]) + 1] = point["viewers"]
    return curve


def build_pool(case: dict) -> list[tuple[dict[int, float], float]]:
    """The analogue pool: (release-day curve, weight) for each comparable that fits the regime."""
    pool: list[tuple[dict[int, float], float]] = []
    for comparable in case.get("comparables") or []:
        curve = release_day_curve(comparable)
        if curve.get(1, 0) < MIN_HOUR1:
            continue
        if sum(1 for h in range(2, 25) if h in curve) < MIN_DAY_HOURS:
            continue
        if curve[1] < MIN_HOUR1_SHARE * max(curve.values()):
            continue  # unlocks later in the UTC day: a different shape family
        unlock = (comparable.get("unlock") or "").lower()
        weight = ROLLING_WEIGHT if ("midnight local" in unlock or "rolling" in unlock) else 1.0
        pool.append((curve, weight))
    return pool


def weighted_quantile(samples: list[tuple[float, float]], tau: float) -> float:
    """The weighted quantile of (value, weight) samples: the first value whose cumulative
    weight reaches tau of the total (a step quantile — no interpolation, so no invented data)."""
    ordered = sorted(samples)
    total = sum(w for _, w in ordered)
    threshold = tau * total
    cumulative = 0.0
    for value, weight in ordered:
        cumulative += weight
        if cumulative >= threshold:
            return value
    return ordered[-1][0]


def hour_quantiles(p1: float, h: int, pool: list[tuple[dict[int, float], float]]) -> list[float | int]:
    """The five quantiles of hour h: the pooled log-ratio quantiles around p1."""
    samples = [
        (math.log(curve[h] / curve[1]), weight)
        for curve, weight in pool
        if h in curve
    ]
    if not samples:
        return [round2(p1 * math.exp(z * FALLBACK_SIGMA * math.sqrt(h - 1))) for z in Z]
    median = weighted_quantile(samples, 0.5)
    quantiles = []
    for tau in LEVELS:
        log_ratio = median + (weighted_quantile(samples, tau) - median) * SPREAD_SCALE
        value = p1 * math.exp(log_ratio)
        quantiles.append(round2(min(max(value, 0.01), 1e9)))
    quantiles.sort()
    return quantiles


def forecast_case(case: dict, name: str) -> dict:
    if case["levels"] != LEVELS:
        raise ValueError(f"{name} asks for levels {case['levels']}, not {LEVELS}")
    first = next((k for k in case["known"] if k["hour"] == 1), None)
    if first is None:
        raise ValueError(f"{name} has no hour-1 print")
    p1 = max(1, first["viewers"])
    pool = build_pool(case)
    return {"hours": [{"hour": row["hour"], "q": hour_quantiles(p1, row["hour"], pool)}
                      for row in case["forecast"]]}


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    # Every case file, in name order, so two runs write the same bytes.
    for path in sorted(INPUT_DIR.glob("*.in")):
        case = json.loads(path.read_text(encoding="utf-8"))
        forecast = forecast_case(case, path.name)
        (OUTPUT_DIR / f"{path.stem}.out").write_text(
            json.dumps(forecast, separators=(",", ":")) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
