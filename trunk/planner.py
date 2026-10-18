"""Trunk sizing: naive Erlang B on AI handle time vs a hairpin-aware formula vs simulation."""

from __future__ import annotations

import math
import random

from .erlang import channels_for, mean_wait
from .sim import Site, run


def make_site(seed: int) -> Site:
    rng = random.Random(seed * 7919)
    base = rng.uniform(60, 220)
    shape = [0.6, 1.3, 1.5, 1.2, 0.9, 1.0, 1.1, 0.95, 0.8, 0.65, 0.5, 0.35]
    hourly = [max(10, base * s * rng.uniform(0.85, 1.15)) for s in shape]
    contain = rng.uniform(0.45, 0.75)
    agent_aht = rng.uniform(240, 420)
    peak_xfer_erl = max(hourly) * (1 - contain) * agent_aht / 3600
    agents = max(2, math.ceil(peak_xfer_erl * rng.uniform(0.95, 1.15)))   # lean staffing, like most contact centers
    return Site(seed=seed, hourly=hourly, channels=0, agents=agents, contain=contain,
                ai_aht=rng.uniform(100, 200), agent_aht=agent_aht, patience=rng.uniform(150, 300),
                refer_ok=rng.random() < 0.7, supervise_share=rng.uniform(0.1, 0.3))


def naive_channels(site: Site, target=0.01) -> int:
    """What you get sizing the trunk on AI talk time alone."""
    return channels_for(max(site.hourly) * site.ai_aht / 3600, target)


def hairpin_aware_channels(site: Site, hairpin_share: float, target=0.01) -> int:
    """Each hairpinned transfer holds 2 channels through queue wait + human talk."""
    lam = max(site.hourly) / 3600
    xfer = 1 - site.contain
    w = mean_wait(lam * xfer * site.agent_aht, site.agents, site.agent_aht)
    w = min(w, site.patience) if math.isfinite(w) else site.patience
    load = lam * (site.ai_aht + xfer * hairpin_share * 2 * (w + site.agent_aht))
    return channels_for(load, target)


def ok(site, policy, n, days=3, target=1.0):
    """Peak-hour blocking <= target % and failed transfers <= target % of transfers, on every simulated day."""
    for d in range(days):
        s = run(site, policy, channels=n, seed_offset=d).summary()
        if s["peak_hour_blocked_pct"] > target or s["failed_transfers"] > target / 100 * max(1, s["transfers"]):
            return False
    return True


def channels_needed(site, policy, start=1, cap=400):
    n = start
    while n < cap and not ok(site, policy, n):
        n += max(1, n // 20)
    # step back down one at a time to the smallest passing value
    while n > start and ok(site, policy, n - 1):
        n -= 1
    return n
