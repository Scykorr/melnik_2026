from __future__ import annotations

import math
import statistics
from dataclasses import dataclass


@dataclass(frozen=True)
class FormulaParams:
    version: str = "ipa-1.0.0"
    lambda_decay: float = 0.05
    history_window_days: int = 28
    max_age_days: int = 30


@dataclass(frozen=True)
class ContributionInput:
    event_id: int
    relevance: float
    scale: float
    source_quality: float
    novelty: float
    age_days: float


def _unit(value: float) -> float:
    if value < 0:
        return 0.0
    if value > 1:
        return 1.0
    return float(value)


def contribution(item: ContributionInput, params: FormulaParams | None = None) -> float:
    """contribution = relevance * scale * source_quality * novelty * exp(-lambda * age_days)."""
    params = params or FormulaParams()
    age = float(item.age_days)
    if age < 0 or age > params.max_age_days:
        return 0.0
    raw = (
        _unit(item.relevance)
        * _unit(item.scale)
        * _unit(item.source_quality)
        * _unit(item.novelty)
        * math.exp(-params.lambda_decay * age)
    )
    return raw


def rolling_index(
    raw_sum: float,
    history: list[float],
    params: FormulaParams | None = None,
) -> tuple[float | None, str]:
    """Нормирует сумму относительно медианы и MAD. При нулевом MAD или короткой истории — отказ."""
    params = params or FormulaParams()
    window = list(history[-params.history_window_days :])
    if len(window) < params.history_window_days:
        return None, "недостаточно данных"
    median = statistics.median(window)
    mad = statistics.median([abs(value - median) for value in window])
    if mad == 0:
        return None, "недостаточно данных"
    z = (raw_sum - median) / (1.4826 * mad)
    z = max(-20.0, min(20.0, z))
    value = 100.0 / (1.0 + math.exp(-z))
    return round(value, 2), "ok"
