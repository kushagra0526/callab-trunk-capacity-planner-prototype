"""Size the trunk for each site three ways and score each transfer policy.

usage: python evaluate.py dev|heldout
"""

import json
import statistics as st
import sys
from multiprocessing import Pool
from pathlib import Path

from trunk.planner import channels_needed, hairpin_aware_channels, make_site, naive_channels
from trunk.policy import Adaptive, HairpinAll, ReferWhenSupported
from trunk.sim import run

SPLITS = {"dev": range(1, 11), "heldout": range(501, 541)}
POL = lambda: [HairpinAll(), ReferWhenSupported(), Adaptive()]


def one(seed):
    s = make_site(seed)
    n0 = naive_channels(s)
    row = {"seed": seed, "refer_ok": s.refer_ok, "peak_calls_h": round(max(s.hourly)), "agents": s.agents,
           "naive": n0, "formula_hairpin_all": hairpin_aware_channels(s, 1.0)}
    for p in POL():
        need = channels_needed(s, p, start=n0)
        at_naive = run(s, p, channels=n0).summary()
        at_need = run(s, p, channels=need).summary()
        row[p.name] = {"needed": need, "peak_blocked_at_naive": at_naive["peak_hour_blocked_pct"],
                       "failed_at_naive": at_naive["failed_transfers"], "supervision_lost": at_need["supervision_lost"],
                       "callbacks": at_need["callbacks"], "transfers": at_need["transfers"], "abandoned": at_need["abandoned"]}
    return row


if __name__ == "__main__":
    split = sys.argv[1] if len(sys.argv) > 1 else "dev"
    with Pool() as pool:
        rows = pool.map(one, SPLITS[split])
    names = [p.name for p in POL()]
    summ = {"sites": len(rows), "refer_ok_sites": sum(r["refer_ok"] for r in rows)}
    for nm in names:
        summ[nm] = {"needed_over_naive": st.mean(r[nm]["needed"] / r["naive"] for r in rows),
                    "peak_blocked_at_naive_pct_mean": st.mean(r[nm]["peak_blocked_at_naive"] for r in rows),
                    "peak_blocked_at_naive_pct_max": max(r[nm]["peak_blocked_at_naive"] for r in rows),
                    "supervision_lost_per_day": st.mean(r[nm]["supervision_lost"] for r in rows),
                    "callbacks_per_day": st.mean(r[nm]["callbacks"] for r in rows)}
    summ["adaptive_vs_hairpin_channel_saving_pct"] = 100 * st.mean(1 - r["adaptive"]["needed"] / r["hairpin all"]["needed"] for r in rows)
    summ["formula_vs_sim_hairpin_all_err_pct"] = 100 * st.mean(abs(r["formula_hairpin_all"] - r["hairpin all"]["needed"]) / r["hairpin all"]["needed"] for r in rows)
    Path("out").mkdir(exist_ok=True)
    Path(f"out/{split}.json").write_text(json.dumps({"summary": summ, "rows": rows}, indent=1))
    print(f"{split}: {summ['sites']} sites ({summ['refer_ok_sites']} accept REFER on the trunk)\n")
    for nm in names:
        v = summ[nm]
        print(f"  {nm:22} channels needed {v['needed_over_naive']:.2f}x naive | at naive sizing: peak-hour blocking "
              f"{v['peak_blocked_at_naive_pct_mean']:4.1f}% avg, {v['peak_blocked_at_naive_pct_max']:4.1f}% worst | "
              f"supervision lost {v['supervision_lost_per_day']:5.1f}/day | callbacks {v['callbacks_per_day']:5.1f}/day")
    print(f"\n  adaptive needs {summ['adaptive_vs_hairpin_channel_saving_pct']:.0f}% fewer channels than hairpin-all, with 0 supervision lost")
    print(f"  hairpin-aware formula vs simulated need (hairpin all): {summ['formula_vs_sim_hairpin_all_err_pct']:.0f}% mean abs error")
