"""Transfer policies: how a call goes from the AI back to human agents."""


class HairpinAll:
    """Stay in the media path for every transfer (keeps supervision and context)."""
    name = "hairpin all"

    def choose(self, site, call, free, est_wait):
        return "hairpin"

    def fallback(self, site, call):
        return "hairpin"


class ReferWhenSupported(HairpinAll):
    """REFER every transfer the PBX accepts (frees the channel, loses supervision)."""
    name = "REFER when supported"

    def choose(self, site, call, free, est_wait):
        return "refer" if site.refer_ok else "hairpin"

    def fallback(self, site, call):
        return "refer" if site.refer_ok else "hairpin"


class Adaptive(HairpinAll):
    """REFER when the call doesn't need supervision; hairpin only when it does.

    When a hairpin would eat into the channels reserved for new inbound calls, or the
    agent queue is long (2 channels held the whole wait), offer a callback instead.
    """
    name = "adaptive"

    def __init__(self, reserve_frac=0.12, max_wait_s=90.0):
        self.reserve_frac, self.max_wait_s = reserve_frac, max_wait_s

    def choose(self, site, call, free, est_wait):
        if site.refer_ok and not call["supervise"]:
            return "refer"
        reserve = max(1, round(self.reserve_frac * site.channels))
        if free - 1 < reserve or est_wait > self.max_wait_s:
            return "callback"
        return "hairpin"

    def fallback(self, site, call):
        return "refer" if site.refer_ok and not call["supervise"] else "hairpin"
