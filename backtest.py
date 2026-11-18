"""Backtest for the analogue forecaster in main.py (development tool; not part of the graded run).

Leave-one-out over the comparables embedded in a kit practice case: each comparable in turn plays
the target — its hour-1 print anchors the forecast, the remaining pool forecasts its day, and the
mean pinball loss on the log scale is compared with the house persistence baseline's. The shipped
configuration (main.py's constants) is the one this procedure selected; the four practice launches
were then checked against their recorded days as a held-out test (numbers in README.md).

Usage:  python3 backtest.py <kit input dir>        e.g. python3 backtest.py ../kit/input
"""

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from main import LEVELS, Z, build_pool, hour_quantiles, release_day_curve  # noqa: E402


def pinball(q: float, y: float, tau: float) -> float:
    d = math.log(max(y, 1)) - math.log(q)
    return 2 * max(tau * d, (tau - 1) * d)


def score(rows: dict[int, list], actual: dict[int, float]) -> float:
    total, n = 0.0, 0
    for h, qs in rows.items():
        if h in actual:
            for tau, q in zip(LEVELS, qs):
                total += pinball(q, actual[h], tau)
                n += 1
    return total / n


def baseline(p1: float) -> dict[int, list]:
    return {h: [p1 * math.exp(z * 0.15 * math.sqrt(h - 1)) for z in Z] for h in range(2, 25)}


def main() -> None:
    case = json.loads((Path(sys.argv[1]) / "p00.in").read_text())
    pool = build_pool(case)
    targets = []
    for comparable in case["comparables"]:
        curve = release_day_curve(comparable)
        if curve.get(1, 0) >= 200 and sum(1 for h in range(2, 25) if h in curve) >= 18 \
                and curve[1] >= 0.05 * max(curve.values()):
            targets.append((comparable["name"], curve))
    model_total = base_total = 0.0
    for name, curve in targets:
        rest = {"comparables": [c for c in case["comparables"] if c["name"] != name]}
        sub_pool = build_pool(rest)
        rows = {h: hour_quantiles(curve[1], h, sub_pool) for h in range(2, 25)}
        m, b = score(rows, curve), score(baseline(curve[1]), curve)
        model_total += m
        base_total += b
        print(f"{name[:42]:44s} model={m:.4f} baseline={b:.4f}")
    n = len(targets)
    print(f"\nleave-one-out over {n} comparables: model={model_total / n:.4f} "
          f"baseline={base_total / n:.4f} gain={(base_total - model_total) / base_total * 100:.1f}%")


if __name__ == "__main__":
    main()
