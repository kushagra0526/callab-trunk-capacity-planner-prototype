"""One business day of calls through an on-prem PBX, a licensed SIP trunk to the AI agent, and a human queue.

Trunk channels are the scarce thing. A call to the AI takes 1 channel. A transfer back to
human agents either:
  REFER   - the PBX takes the call over (RFC 3515); the AI's channel is freed at once.
            Context can ride in a UUI header, but the AI can no longer supervise the call.
  HAIRPIN - the AI bridges a second leg back into the PBX queue and stays in the media
            path: 2 channels held through the whole queue wait + human talk time.
  CALLBACK- the AI takes the details and frees the channel; a human calls back from the
            PBX later (no trunk use).
All rates are invented but plausible; nothing here is Callab's data.
"""

from __future__ import annotations

import heapq
import math
import random
from dataclasses import dataclass, field


@dataclass
class Site:
    seed: int
    hourly: list            # calls per hour, 8:00 .. 20:00
    channels: int
    agents: int
    contain: float = 0.6    # share of AI calls resolved without a human
    ai_aht: float = 150.0   # seconds
    agent_aht: float = 330.0
    patience: float = 240.0  # mean seconds a caller waits in queue before hanging up
    refer_ok: bool = True    # PBX accepts REFER on this trunk (config dependent)
    supervise_share: float = 0.2   # transfers that need the AI to stay on (complaints, VIP, compliance)
    callback_accept: float = 0.6


@dataclass
class Out:
    calls: int = 0
    blocked: int = 0
    failed_transfer: int = 0
    abandoned: int = 0
    transfers: int = 0
    callbacks: int = 0
    supervision_lost: int = 0
    peak_used: int = 0
    blocked_by_hour: list = field(default_factory=lambda: [0] * 12)
    calls_by_hour: list = field(default_factory=lambda: [0] * 12)
    queue_waits: list = field(default_factory=list)

    def summary(self):
        w = sorted(self.queue_waits)
        return {"calls": self.calls, "blocked_pct": 100 * self.blocked / max(1, self.calls),
                "peak_hour_blocked_pct": max(100 * b / max(1, c) for b, c in zip(self.blocked_by_hour, self.calls_by_hour)),
                "failed_transfers": self.failed_transfer, "abandoned": self.abandoned, "transfers": self.transfers,
                "callbacks": self.callbacks, "supervision_lost": self.supervision_lost, "peak_channels": self.peak_used,
                "queue_wait_p90_s": w[int(0.9 * (len(w) - 1))] if w else 0.0}


def run(site: Site, policy, channels: int | None = None, seed_offset: int = 0) -> Out:
    N = site.channels if channels is None else channels
    rng = random.Random(site.seed * 31 + seed_offset)
    out = Out()
    ev, seq = [], 0

    def push(t, kind, cid):
        nonlocal seq
        seq += 1
        heapq.heappush(ev, (t, seq, kind, cid))

    # arrivals: non-homogeneous Poisson by hour (thinning-free: per-hour Poisson process)
    t0 = 0.0
    for h, lam in enumerate(site.hourly):
        t = h * 3600.0
        while True:
            t += rng.expovariate(lam / 3600.0)
            if t >= (h + 1) * 3600.0:
                break
            push(t, "arrive", None)
    used = 0
    free_agents = site.agents
    queue = []            # (t_enqueued, cid) FIFO; callbacks served after live callers
    callbacks = []
    calls = {}            # cid -> dict(ch=channels held, state)
    nxt = 0

    def occupy(k):
        nonlocal used
        used += k
        out.peak_used = max(out.peak_used, used)

    def serve(t):
        nonlocal free_agents, used
        while free_agents > 0 and (queue or callbacks):
            if queue:
                tq, cid = queue.pop(0)
                c = calls[cid]
                if c["state"] != "queued":
                    continue
                c["state"] = "talking"
                out.queue_waits.append(t - tq)
            else:
                cid = callbacks.pop(0)
                c = calls[cid]
                c["state"] = "talking"
            free_agents -= 1
            push(t + rng.lognormvariate(math.log(site.agent_aht) - 0.08, 0.4), "agent_done", cid)

    while ev:
        t, _, kind, cid = heapq.heappop(ev)
        if kind == "arrive":
            out.calls += 1
            h = min(11, int(t // 3600))
            out.calls_by_hour[h] += 1
            if used + 1 > N:
                out.blocked += 1
                out.blocked_by_hour[h] += 1
                continue
            cid = nxt
            nxt += 1
            occupy(1)
            calls[cid] = {"ch": 1, "state": "ai", "supervise": rng.random() < site.supervise_share}
            push(t + rng.lognormvariate(math.log(site.ai_aht) - 0.08, 0.4), "ai_done", cid)
        elif kind == "ai_done":
            c = calls[cid]
            if rng.random() < site.contain:
                used -= c["ch"]
                c["ch"] = 0
                c["state"] = "done"
                continue
            out.transfers += 1
            est_wait = (len(queue) + 1) / max(1, site.agents) * site.agent_aht if free_agents == 0 else 0.0
            mode = policy.choose(site, c, N - used, est_wait)
            if mode == "callback" and rng.random() >= site.callback_accept:
                mode = policy.fallback(site, c)
            if mode == "callback":
                out.callbacks += 1
                used -= c["ch"]
                c["ch"] = 0
                c["state"] = "callback"
                callbacks.append(cid)
                serve(t)
                continue
            if mode == "refer":
                if c["supervise"]:
                    out.supervision_lost += 1
                used -= c["ch"]
                c["ch"] = 0
            else:   # hairpin
                if used + 1 > N:
                    out.failed_transfer += 1
                    used -= c["ch"]
                    c["ch"] = 0
                    c["state"] = "done"
                    continue
                occupy(1)
                c["ch"] = 2
            c["state"] = "queued"
            queue.append((t, cid))
            push(t + rng.expovariate(1 / site.patience), "abandon", cid)
            serve(t)
        elif kind == "abandon":
            c = calls[cid]
            if c["state"] == "queued":
                c["state"] = "done"
                out.abandoned += 1
                used -= c["ch"]
                c["ch"] = 0
        elif kind == "agent_done":
            c = calls[cid]
            c["state"] = "done"
            used -= c["ch"]
            c["ch"] = 0
            free_agents += 1
            serve(t)
    return out
