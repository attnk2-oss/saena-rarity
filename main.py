#!/usr/bin/env python3
"""Deterministic GTA VI trophy earn-rate forecaster for make.fun cases."""

from __future__ import annotations

import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence


QUANTILE_Z = (-1.6449, -0.6745, 0.0, 0.6745, 1.6449)
MIN_PERCENT = 0.01
MAX_PERCENT = 99.99
EPS = 1.0e-12


def parse_rfc3339(value: str) -> datetime:
    """Parse an RFC3339 timestamp and normalize it to UTC."""
    text = str(value).strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def hours_between(start: datetime, end: datetime) -> float:
    return (end - start).total_seconds() / 3600.0


def linear_fit(xs: Sequence[float], ys: Sequence[float]) -> tuple[float, float, float] | None:
    """Return (slope, intercept, residual RMS) for an ordinary least-squares fit."""
    count = len(xs)
    if count < 2 or count != len(ys):
        return None
    x_mean = math.fsum(xs) / count
    y_mean = math.fsum(ys) / count
    denominator = math.fsum((x - x_mean) ** 2 for x in xs)
    if denominator <= EPS:
        return None
    numerator = math.fsum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
    slope = numerator / denominator
    intercept = y_mean - slope * x_mean
    residuals = [y - (intercept + slope * x) for x, y in zip(xs, ys)]
    rms = math.sqrt(math.fsum(r * r for r in residuals) / count)
    return slope, intercept, rms


def clamp(value: float, low: float, high: float) -> float:
    return low if value < low else high if value > high else value


def logit(probability: float) -> float:
    p = clamp(probability, 1.0e-15, 1.0 - 1.0e-15)
    return math.log(p / (1.0 - p))


def unlogit_percent(value: float) -> float:
    """Invert the logit transform directly into percentage points."""
    if value >= 0.0:
        if value > 50.0:
            return 100.0
        return 100.0 / (1.0 + math.exp(-value))
    if value < -50.0:
        return 0.0
    exp_value = math.exp(value)
    return 100.0 * exp_value / (1.0 + exp_value)


def tracked_change_points(reads: Sequence[dict]) -> list[tuple[float, float]]:
    """Keep the initial observation and each later change in tracked count."""
    if not reads:
        return []
    start = parse_rfc3339(reads[0]["at"])
    points: list[tuple[float, float]] = []
    previous: float | None = None
    for read in reads:
        h = hours_between(start, parse_rfc3339(read["at"]))
        tracked = max(0.0, float(read["players_tracked"]))
        if previous is None or tracked != previous:
            points.append((h, tracked))
        previous = tracked
    return points


def tracked_forecast(
    points: Sequence[tuple[float, float]], target_hour: float
) -> tuple[float, float]:
    """Return predicted tracked players and the fitted tracked slope."""
    if not points:
        return 1.0, 0.35

    x_values = [math.log1p(max(0.0, h)) for h, _ in points]
    y_values = [math.log(max(value, 0.5)) for _, value in points]
    fit = linear_fit(x_values, y_values)

    fitted_slope = fit[0] if fit is not None else 0.35
    last_hour, last_tracked = points[-1]
    x_target = math.log1p(max(0.0, target_hour))
    x_last = math.log1p(max(0.0, last_hour))

    if len(points) >= 3 and fit is not None:
        horizon = max(0.0, target_hour - last_hour)
        decades = math.log10(1.0 + horizon / max(last_tracked, 0.25))
        effective_slope = fitted_slope * (0.6 ** decades)
    else:
        effective_slope = 0.35

    predicted = last_tracked * math.exp(effective_slope * (x_target - x_last))
    return max(predicted, last_tracked), fitted_slope


def recent_holder_points(points: Sequence[tuple[float, float]]) -> list[tuple[float, float]]:
    """Use the six-hour tail, or the final twelve observations when sparse."""
    if len(points) < 3:
        return []
    newest = points[-1][0]
    recent = [point for point in points if point[0] >= newest - 6.0]
    if len(recent) < 3:
        recent = list(points[-12:])
    return recent


def holder_forecast(
    points: Sequence[tuple[float, float]],
    current_rate: float,
    tracked_slope: float,
    target_hour: float,
) -> tuple[float, float]:
    """Predict the holder count at target and return it with sigma_fit."""
    if not points:
        return 0.0, 0.5

    x_now = math.log1p(max(0.0, points[-1][0]))
    x_target = math.log1p(max(0.0, target_hour))
    holder_now = min(max(0.0, points[-1][1]), 1.0e300)
    recent = recent_holder_points(points)
    fit = None
    if recent:
        fit = linear_fit(
            [math.log1p(max(0.0, h)) for h, _ in recent],
            [math.log(max(count, 0.5)) for _, count in recent],
        )

    if fit is not None:
        slope = clamp(fit[0], 0.0, 1.5)
        sigma_fit = 0.35 + fit[2] * 0.8
    else:
        if current_rate > 0.05:
            share = 0.2 + 0.8 * math.sqrt(min(current_rate / 50.0, 1.0))
        else:
            share = 0.15
        slope = max(0.1, tracked_slope * share)
        sigma_fit = 0.5

    if holder_now <= 0.0:
        return 0.0, sigma_fit
    predicted = holder_now * math.exp(slope * (x_target - x_now))
    return predicted, sigma_fit


def logit_sigma(predicted_rate: float, sigma_rate: float) -> float:
    """Delta-method logit uncertainty with safe one-sided derivatives."""
    p = predicted_rate / 100.0
    if p <= 0.0 or p >= 1.0:
        return 1.6

    step = max(sigma_rate, 1.0e-12)
    half = step / 2.0
    near_zero = p - half <= 1.0e-12
    near_one = p + half >= 1.0 - 1.0e-12

    if near_zero and near_one:
        derivative = 1.0 / max(p * (1.0 - p), 1.0e-12)
    elif near_zero:
        upper = min(1.0 - 1.0e-15, p + half)
        derivative = (logit(upper) - logit(p)) / max(upper - p, 1.0e-15)
    elif near_one:
        lower = max(1.0e-15, p - half)
        derivative = (logit(p) - logit(lower)) / max(p - lower, 1.0e-15)
    else:
        lower = max(1.0e-15, p - half)
        upper = min(1.0 - 1.0e-15, p + half)
        derivative = (logit(upper) - logit(lower)) / (upper - lower)
    return min(sigma_rate * derivative, 1.6)


def quantiles_for_trophy(
    holders: Sequence[tuple[float, float]],
    rate: float,
    tracked_slope: float,
    tracked_target: float,
    target_hour: float,
    horizon_days: float,
) -> list[float]:
    if not holders or rate <= 0.0 or tracked_target <= 0.0:
        return [MIN_PERCENT] * 5

    holder_target, sigma_fit = holder_forecast(
        holders, rate, tracked_slope, target_hour
    )
    if holder_target <= 0.0:
        return [MIN_PERCENT] * 5

    predicted_rate = 100.0 * holder_target / tracked_target
    p = clamp(predicted_rate / 100.0, 1.0e-12, 1.0 - 1.0e-12)
    center = logit(p)
    sigma_rate = max(sigma_fit * math.sqrt(1.0 + max(0.0, horizon_days)), 0.10)
    sigma_logit = logit_sigma(predicted_rate, sigma_rate)

    values = [unlogit_percent(center + z * sigma_logit) for z in QUANTILE_Z]
    values = [clamp(value, MIN_PERCENT, MAX_PERCENT) for value in values]
    values.sort()
    return [round(value, 4) for value in values]


def forecast_case(case: dict) -> dict:
    raw_reads = list(case.get("history") or [])
    raw_reads.sort(key=lambda read: parse_rfc3339(read["at"]))
    if not raw_reads:
        trophies = case.get("trophies") or []
        return {"trophies": [{"id": int(t["id"]), "q": [MIN_PERCENT] * 5} for t in trophies]}

    start = parse_rfc3339(raw_reads[0]["at"])
    target_value = case["target"]
    target_at = target_value["at"] if isinstance(target_value, dict) else target_value
    target_time = parse_rfc3339(target_at)
    target_hour = hours_between(start, target_time)
    last_read_time = parse_rfc3339(raw_reads[-1]["at"])
    horizon_days = max(0.0, hours_between(last_read_time, target_time) / 24.0)

    changes = tracked_change_points(raw_reads)
    tracked_target, tracked_slope = tracked_forecast(changes, target_hour)

    trophies = list(case.get("trophies") or [])
    rates = list(raw_reads[-1].get("rates") or [])
    holder_series: list[list[tuple[float, float]]] = [[] for _ in trophies]
    for read in raw_reads:
        read_time = parse_rfc3339(read["at"])
        h = hours_between(start, read_time)
        tracked = float(read["players_tracked"])
        is_change = any(abs(h - point[0]) <= 1.0e-12 for point in changes)
        if not is_change:
            continue
        read_rates = list(read.get("rates") or [])
        for index in range(len(trophies)):
            if index >= len(read_rates):
                continue
            holder_count = round(float(read_rates[index]) * tracked / 100.0)
            holder_series[index].append((h, float(holder_count)))

    results = []
    for index, trophy in enumerate(trophies):
        rate = float(rates[index]) if index < len(rates) else 0.0
        q = quantiles_for_trophy(
            holder_series[index],
            rate,
            tracked_slope,
            tracked_target,
            target_hour,
            horizon_days,
        )
        results.append({"id": int(trophy["id"]), "q": q})
    return {"trophies": results}


def input_directory(argv: Sequence[str]) -> str:
    if "MAKEFUN_INPUT_DIR" in os.environ:
        return os.environ["MAKEFUN_INPUT_DIR"]
    return argv[1] if len(argv) > 1 else "/input"


def output_directory(argv: Sequence[str]) -> str:
    if "MAKEFUN_OUTPUT_DIR" in os.environ:
        return os.environ["MAKEFUN_OUTPUT_DIR"]
    return argv[2] if len(argv) > 2 else "/output"


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv if argv is None else argv)
    in_dir = Path(input_directory(args))
    out_dir = Path(output_directory(args))
    out_dir.mkdir(parents=True, exist_ok=True)

    for input_path in sorted(in_dir.glob("p*.in"), key=lambda path: path.name):
        with input_path.open("r", encoding="utf-8") as handle:
            case = json.load(handle)
        result = forecast_case(case)
        output_path = out_dir / (input_path.stem + ".out")
        with output_path.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
            handle.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
