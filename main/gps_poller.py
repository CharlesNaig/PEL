"""
GPS Background Poller — 24/7 Live Location Tracker
====================================================
Runs a background thread that continuously polls both A7670E GNSS and
GT-U7, keeping the latest known fix cached in memory.

When the panic button is pressed, the cached fix is available immediately
(or nearly so), dramatically reducing response time.

The poller thread is daemon — it exits automatically when main.py shuts down.
"""

import threading
import time

from logger import get_logger

log = get_logger("PEL.gps_poller")


class GPSPoller:
    """
    Background GPS poller that continuously queries both GPS modules
    and caches the latest valid fix.
    """

    def __init__(self, modem, gtu7_module=None, poll_interval=5):
        """
        Args:
            modem: Initialised A7670E instance
            gtu7_module: Optional GTU7 instance (None if disabled)
            poll_interval: Seconds between poll cycles
        """
        self._modem = modem
        self._gtu7 = gtu7_module
        self._poll_interval = poll_interval

        # Cached fix (thread-safe via lock)
        self._lock = threading.Lock()
        self._lat = None
        self._lng = None
        self._utc_time = None
        self._source = None
        self._fix_time = None       # time.time() when fix was obtained
        self._fix_count = 0         # total fixes obtained

        # Thread control
        self._thread = None
        self._running = False
        self._paused = False        # pause during panic SMS (modem busy)
        self._gnss_enabled = False

    @property
    def has_fix(self):
        """True if a valid cached fix exists."""
        with self._lock:
            return self._lat is not None

    @property
    def fix_age(self):
        """Seconds since last fix, or None if no fix."""
        with self._lock:
            if self._fix_time is None:
                return None
            return time.time() - self._fix_time

    def get_fix(self, max_age=60):
        """
        Retrieve the cached GPS fix if it's fresh enough.

        Args:
            max_age: Maximum age in seconds to consider the fix valid.
                     Use 0 to accept any age.

        Returns:
            (lat, lng, utc_time, source) or (None, None, None, None)
        """
        with self._lock:
            if self._lat is None:
                return (None, None, None, None)
            if max_age > 0 and self._fix_time is not None:
                age = time.time() - self._fix_time
                if age > max_age:
                    return (None, None, None, None)
            return (self._lat, self._lng, self._utc_time, self._source)

    def start(self):
        """Start the background polling thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        log.info("[GPS-BG] Background GPS poller started")

    def stop(self):
        """Stop the background polling thread."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5.0)
            self._thread = None
        # Disable GNSS when stopping
        if self._gnss_enabled:
            try:
                self._modem.disable_gnss()
                self._gnss_enabled = False
            except Exception:
                pass
        log.info("[GPS-BG] Background GPS poller stopped")

    def pause(self):
        """Pause polling (e.g. when modem is busy sending SMS)."""
        self._paused = True
        log.warning("[GPS-BG] Polling paused (modem busy)")

    def resume(self):
        """Resume polling after pause."""
        self._paused = False
        log.info("[GPS-BG] Polling resumed")

    def _poll_loop(self):
        """Main polling loop — runs in background thread."""
        # Enable A7670E GNSS on first start
        try:
            if self._modem and self._modem.is_connected:
                self._modem.enable_gnss()
                self._gnss_enabled = True
        except Exception as e:
            log.error(f"[GPS-BG] GNSS enable error: {e}")

        while self._running:
            if self._paused:
                time.sleep(0.5)
                continue

            try:
                self._poll_once()
            except Exception as e:
                log.error(f"[GPS-BG] Poll error: {e}")

            # Sleep in small increments so stop() is responsive
            for _ in range(int(self._poll_interval * 10)):
                if not self._running:
                    break
                time.sleep(0.1)

    def _poll_once(self):
        """Poll both GPS sources once and update the cache if fix found."""
        # Poll A7670E GNSS
        if self._modem and self._modem.is_connected and not self._paused:
            try:
                lat, lng, utc_time = self._modem.poll_gnss_once()
                if lat is not None:
                    self._update_fix(lat, lng, utc_time, "A7670E")
                    return
            except Exception:
                pass

        # Poll GT-U7
        if self._gtu7 and self._gtu7.is_enabled and not self._paused:
            try:
                lat, lng, utc_time = self._gtu7.poll_fix()
                if lat is not None:
                    self._update_fix(lat, lng, utc_time, "GT-U7")
                    return
            except Exception:
                pass

    def _update_fix(self, lat, lng, utc_time, source):
        """Thread-safe update of the cached fix."""
        with self._lock:
            self._lat = lat
            self._lng = lng
            self._utc_time = utc_time
            self._source = source
            self._fix_time = time.time()
            self._fix_count += 1

            if self._fix_count == 1:
                log.info(f"[GPS-BG] First fix via {source}: "
                      f"{lat:.6f}, {lng:.6f}")
            elif self._fix_count % 12 == 0:
                # Log every ~60s (12 polls at 5s interval) so we know it's alive
                log.info(f"[GPS-BG] Fix #{self._fix_count} via {source}: "
                      f"{lat:.6f}, {lng:.6f}")
