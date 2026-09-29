"""Best-effort Linux container metrics, without credentials or external calls."""

import logging
from pathlib import Path
import sys
from time import monotonic
import time
from bot.logging.health import health


def memory_limit_mb():
    for path in ("/sys/fs/cgroup/memory.max", "/sys/fs/cgroup/memory/memory.limit_in_bytes"):
        try:
            value = int(Path(path).read_text().strip())
            if 0 < value < 2 ** 60:
                return round(value / 1024 ** 2, 1)
        except (OSError, ValueError):
            pass
    return None

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
            health.host = {'observed_at': time.time(), 'rss_mb': None,
                           'memory_limit_mb': None, 'wake_lag_ms': round(wake_lag * 1000, 1),
                           'throttle_percent': None}
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
        throttle_percent = None
        if current is not None and self.previous is not None:
            when, previous = self.previous
            interval = now - when
            if interval > 0:
                throttle_percent = round(max(0, current[1] - previous[1]) / (interval * 1000) * 100, 2)
        health.host = {'observed_at': time.time(), 'rss_mb': round(rss, 1) if rss is not None else None,
                       'memory_limit_mb': memory_limit_mb(), 'wake_lag_ms': round(wake_lag * 1000, 1),
                       'throttle_percent': throttle_percent}
        if current is not None and self.previous is not None:
            when, previous = self.previous
            logger.info("host_performance interval_s=%.1f rss_mb=%s wake_lag_ms=%.0f throttled_periods=%d throttled_ms=%.0f",
                        now - when, round(rss, 1) if rss is not None else "unavailable",
                        wake_lag * 1000, max(0, current[0] - previous[0]), max(0, current[1] - previous[1]))
        else:
            logger.debug("host_performance rss_mb=%s wake_lag_ms=%.0f throttle_sample_available=%s",
                         rss, wake_lag * 1000, current is not None)
        self.previous = (now, current) if current is not None else None
