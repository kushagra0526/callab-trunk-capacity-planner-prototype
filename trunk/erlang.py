"""Erlang B (blocking) and Erlang C (queueing) — the textbook trunk/agent sizing formulas."""

from __future__ import annotations

import math


def erlang_b(load: float, n: int) -> float:
    """P(all n channels busy) for offered load in Erlangs (recursive, numerically stable)."""
    b = 1.0
    for k in range(1, n + 1):
        b = load * b / (k + load * b)
    return b


def channels_for(load: float, target: float = 0.01) -> int:
    n = 0
    while erlang_b(load, n) > target:
        n += 1
    return n


def erlang_c(load: float, agents: int) -> float:
    """P(wait > 0) with `agents` servers (M/M/c)."""
    if agents <= load:
        return 1.0
    b = erlang_b(load, agents)
    return agents * b / (agents - load * (1 - b))


def mean_wait(load: float, agents: int, aht_s: float) -> float:
    if agents <= load:
        return math.inf
    return erlang_c(load, agents) * aht_s / (agents - load)
