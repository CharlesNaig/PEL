"""
File-Based Event Logger
========================
Replaces SD card logging from the Arduino version.
Writes structured log entries to a plain text file on the Pi filesystem.

Port of: logToSD() in main.ino (lines 598-663)
"""

import os
from datetime import datetime, timezone

from config import LOG_FILE


def log_event(status, lat=0.0, lng=0.0, utc_time=None):
    """
    Append a log entry to LOG_FILE.

    Args:
        status:   Event string, e.g. 'SUCCESS', 'FAILED — GPS Timeout',
                  'CANCELLED'
        lat:      Latitude float (0.0 if unknown)
        lng:      Longitude float (0.0 if unknown)
        utc_time: UTC timestamp string from GNSS (e.g. '20240601120000.000')
                  If None, uses system clock.

    Port of:
        logToSD(status, lat, lng) in main.ino.
        Arduino version fell back to millis() uptime when GPS date was
        unavailable; this version falls back to the Pi system clock which
        is NTP-synced on most Raspberry Pis.
    """
    # Format timestamp
    if utc_time and len(utc_time) >= 14:
        try:
            # GNSS UTC format: YYYYMMDDHHmmss.sss
            ts = (
                f"{utc_time[0:4]}-{utc_time[4:6]}-{utc_time[6:8]} "
                f"{utc_time[8:10]}:{utc_time[10:12]}:{utc_time[12:14]} UTC"
            )
        except (IndexError, ValueError):
            ts = _system_timestamp()
    else:
        ts = _system_timestamp()

    entry = (
        "--------------------------------\n"
        f"[{ts}]\n"
        f"Latitude:  {lat:.6f}\n"
        f"Longitude: {lng:.6f}\n"
        f"Status:    {status}\n"
        "--------------------------------\n"
        "\n"
    )

    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(entry)
        print(f"[LOG] Logged OK -> {LOG_FILE}")
    except OSError as e:
        print(f"[LOG] Write FAILED: {e}")


def _system_timestamp():
    """Return formatted system clock timestamp."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
