"""Held-out site 501: one day on a trunk sized the naive way, then what each policy needs."""
import json
from trunk.planner import hairpin_aware_channels, make_site, naive_channels
from trunk.policy import Adaptive, HairpinAll, ReferWhenSupported
from trunk.sim import run

s = make_site(501)
n0 = naive_channels(s)
print(f"site 501: peak {max(s.hourly):.0f} calls/h, AI contains {s.contain:.0%}, {s.agents} human agents, "
      f"PBX accepts REFER: {s.refer_ok}, {s.supervise_share:.0%} of transfers need the AI to stay on")
print(f"naive Erlang B sizing (AI talk time only, 1% blocking): {n0} channels")
print(f"hairpin-aware formula (2 channels through queue + talk): {hairpin_aware_channels(s, 1.0)} channels\n")
rows = json.load(open("out/heldout.json"))["rows"]
r = next(x for x in rows if x["seed"] == 501)
print(f"{'policy':22} {'peak-hour blocked @'+str(n0):>22} {'failed transfers':>17} {'channels needed':>16} {'supervision lost':>17}")
for p in (HairpinAll(), ReferWhenSupported(), Adaptive()):
    o = run(s, p, channels=n0).summary()
    print(f"{p.name:22} {o['peak_hour_blocked_pct']:21.1f}% {o['failed_transfers']:17d} {r[p.name]['needed']:16d} {r[p.name]['supervision_lost']:17d}")
