import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from trunk.erlang import channels_for, erlang_b, erlang_c
from trunk.planner import make_site, naive_channels
from trunk.policy import Adaptive, HairpinAll, ReferWhenSupported
from trunk.sim import Site, run


class TestErlang(unittest.TestCase):
    def test_known_values(self):
        self.assertAlmostEqual(erlang_b(10, 10), 0.2146, places=3)     # textbook table value
        self.assertEqual(channels_for(10, 0.01), 18)
        self.assertAlmostEqual(erlang_c(10, 12), 0.4493, places=3)

    def test_sim_matches_erlang_b_without_transfers(self):
        # pure AI calls, no transfers: blocking should match Erlang B
        s = Site(seed=3, hourly=[360] * 12, channels=12, agents=1, contain=1.0, ai_aht=100)
        load = 360 * 100 / 3600
        sims = [run(s, HairpinAll(), seed_offset=d).summary()["blocked_pct"] for d in range(4)]
        self.assertAlmostEqual(sum(sims) / 4 / 100, erlang_b(load, 12), delta=0.01)


class TestPolicies(unittest.TestCase):
    def test_hairpin_needs_more_than_naive(self):
        s = make_site(2)
        n0 = naive_channels(s)
        self.assertGreater(run(s, HairpinAll(), channels=n0).summary()["peak_hour_blocked_pct"], 5)

    def test_adaptive_never_drops_supervision(self):
        s = make_site(2)
        s.refer_ok = True
        a = run(s, Adaptive(), channels=40).summary()
        r = run(s, ReferWhenSupported(), channels=40).summary()
        self.assertEqual(a["supervision_lost"], 0)
        self.assertGreater(r["supervision_lost"], 0)

    def test_deterministic(self):
        s = make_site(5)
        self.assertEqual(run(s, Adaptive(), channels=30).summary(), run(s, Adaptive(), channels=30).summary())


if __name__ == "__main__":
    unittest.main()
