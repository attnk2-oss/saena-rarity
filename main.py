#!/usr/bin/env python3
"""Refresh-step rarity forecaster for make.fun cases."""

from __future__ import annotations

import json
import math
import os
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

Z_LEVELS = (-1.6449, -0.6745, 0.0, 0.6745, 1.6449)


def parse_time(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    stamp = datetime.fromisoformat(text)
    if stamp.tzinfo is None:
        return stamp.replace(tzinfo=timezone.utc)
    return stamp


def hours_between(start: datetime, end: datetime) -> float:
    return (end - start).total_seconds() / 3600.0


def rate_at(read: dict, index: int) -> float | None:
    rates = read.get("rates") or []
    if index >= len(rates):
        return None
    value = rates[index]
    if value is None:
        return None
    return float(value)


def latest_rate(read: dict, index: int) -> float:
    value = rate_at(read, index)
    return 0.01 if value is None else value


def target_time(case: dict) -> str:
    target = case.get("target")
    if isinstance(target, dict):
        return target.get("at", "")
    return target or ""


def forecast(case: dict) -> list[dict]:
    trophies = case.get("trophies") or []
    history = sorted(case.get("history") or [], key=lambda read: parse_time(read["at"]))
    if not history:
        return [
            {"id": trophy.get("id"), "q": [0.01, 0.01, 0.01, 0.01, 0.01]}
            for trophy in trophies
        ]

    last = history[-1]
    last_at = parse_time(last["at"])
    target_at = parse_time(target_time(case))
    horizon_h = hours_between(last_at, target_at)

    tracked = [read.get("players_tracked") for read in history]
    steps = [
        index
        for index in range(1, len(history))
        if tracked[index] != tracked[index - 1]
    ]

    drift = 0.0
    if len(steps) >= 2:
        b = steps[-1]
        a = b - 1
        changes = []
        for index in range(len(trophies)):
            before = rate_at(history[a], index)
            after = rate_at(history[b], index)
            if before is not None and after is not None and before >= 0.05 and after >= 0.05:
                changes.append(math.log(after / before))
        if changes:
            drift = min(max(statistics.median(changes), 0.0), 0.40)

    if len(steps) >= 2:
        step_gaps = [
            hours_between(parse_time(history[steps[i - 1]]["at"]), parse_time(history[steps[i]]["at"]))
            for i in range(1, len(steps))
        ]
        gap_h = statistics.median(step_gaps)
    else:
        gap_h = horizon_h

    refreshes = min(max(horizon_h / max(gap_h, 0.5), 0.0), 4.0)
    tilt = min(max(math.exp(drift * refreshes * 0.5), 1.0), 1.5)

    # No forward horizon means no widening beyond the model floor.
    if horizon_h <= 0.0:
        sigma = 0.22
    else:
        horizon_days = horizon_h / 24.0
        sigma = min(max(0.22 * math.sqrt(horizon_days) + 0.10, 0.22), 0.60)

    output = []
    for index, trophy in enumerate(trophies):
        base = latest_rate(last, index)
        median = min(max(base * tilt, 0.01), 99.99)
        center = math.log(median + 0.01)
        quantiles = [math.exp(center + z * sigma) - 0.01 for z in Z_LEVELS]
        quantiles = sorted(min(max(value, 0.01), 99.99) for value in quantiles)
        output.append(
            {
                "id": trophy.get("id"),
                "q": [round(value, 4) for value in quantiles],
            }
        )
    return output


def main() -> None:
    input_dir = Path(os.environ.get("MAKEFUN_INPUT_DIR") or (sys.argv[1] if len(sys.argv) > 1 else "/input"))
    output_dir = Path(os.environ.get("MAKEFUN_OUTPUT_DIR") or (sys.argv[2] if len(sys.argv) > 2 else "/output"))
    output_dir.mkdir(parents=True, exist_ok=True)

    for source in sorted(input_dir.glob("p*.in")):
        case = json.loads(source.read_text(encoding="utf-8"))
        result = {"trophies": forecast(case)}
        destination = output_dir / (source.stem + ".out")
        destination.write_text(
            json.dumps(result, separators=(",", ":"), ensure_ascii=False) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
