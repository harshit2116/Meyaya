"""Best-effort Linux container metrics, without credentials or external calls."""

import logging
from pathlib import Path
import sys
from time import monotonic

logger = logging.getLogger(__name__)


def cpu_counters():
    # cgroup v2 uses microseconds; v1 reports throttle time in nanoseconds.
    for path, divisor in (("/sys/fs/cgroup/cpu.stat", 1000),
                          ("/sys/fs/cgroup/cpu/cpu.stat", 1_000_000)):
        try:
            values = dict(line.split() for line in Path(path).read_text().splitlines())
            return (int(values.get("nr_throttled", 0)),
                    int(values.get("throttled_usec", values.get("throttled_time", 0))) / divisor)
        except (OSError, ValueError):
            continue
    return None


class HostMetrics:
    def __init__(self):
        self.previous = None

    def record(self, wake_lag):
        if not sys.platform.startswith("linux"):
            return
        current = cpu_counters()
        rss = None
        try:
            for line in Path("/proc/self/status").read_text().splitlines():
                if line.startswith("VmRSS:"):
                    rss = int(line.split()[1]) / 1024
                    break
        except (OSError, ValueError):
            pass
        now = monotonic()
        if current is not None and self.previous is not None:
            when, previous = self.previous
            logger.info("host_performance interval_s=%.1f rss_mb=%s wake_lag_ms=%.0f throttled_periods=%d throttled_ms=%.0f",
                        now - when, round(rss, 1) if rss is not None else "unavailable",
                        wake_lag * 1000, max(0, current[0] - previous[0]), max(0, current[1] - previous[1]))
        else:
            logger.debug("host_performance rss_mb=%s wake_lag_ms=%.0f throttle_sample_available=%s",
                         rss, wake_lag * 1000, current is not None)
        self.previous = (now, current) if current is not None else None
