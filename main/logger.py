"""
File-Based Event Logger + Colored Console Logger
==================================================
Replaces SD card logging from the Arduino version.
Writes structured log entries to a plain text file on the Pi filesystem.
Provides colored console logging (green=OK, yellow=WARN, red=ERROR).

Port of: logToSD() in main.ino (lines 598-663)
"""

import os
import sys
import logging
from datetime import datetime, timezone

from config import LOG_FILE


# ── ANSI Color Codes ──────────────────────────────────────────────────────

class _Colors:
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    GREEN   = "\033[32m"
    YELLOW  = "\033[33m"
    RED     = "\033[31m"
    CYAN    = "\033[36m"
    WHITE   = "\033[37m"
    BRIGHT_GREEN  = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_RED    = "\033[91m"
    BRIGHT_CYAN   = "\033[96m"
    DIM     = "\033[2m"


class ColoredFormatter(logging.Formatter):
    """Custom formatter that adds ANSI colors based on log level."""

    LEVEL_COLORS = {
        logging.DEBUG:    _Colors.DIM + _Colors.WHITE,
        logging.INFO:     _Colors.BRIGHT_GREEN,
        logging.WARNING:  _Colors.BRIGHT_YELLOW,
        logging.ERROR:    _Colors.BRIGHT_RED,
        logging.CRITICAL: _Colors.BOLD + _Colors.BRIGHT_RED,
    }

    LEVEL_ICONS = {
        logging.DEBUG:    "·",
        logging.INFO:     "✓",
        logging.WARNING:  "⚠",
        logging.ERROR:    "✗",
        logging.CRITICAL: "✗✗",
    }

    def format(self, record):
        color = self.LEVEL_COLORS.get(record.levelno, _Colors.WHITE)
        icon = self.LEVEL_ICONS.get(record.levelno, " ")
        reset = _Colors.RESET
        timestamp = _Colors.DIM + self.formatTime(record, "%H:%M:%S") + reset

        msg = record.getMessage()
        level_tag = f"{color}{record.levelname:<8}{reset}"

        return f"{timestamp} {color}{icon}{reset} {level_tag} {color}{msg}{reset}"


def get_logger(name="PEL"):
    """
    Return a named logger with colored console output.

    Usage:
        from logger import get_logger
        log = get_logger(__name__)
        log.info("System ready")        # green
        log.warning("SIM issue")        # yellow
        log.error("Modem not found")    # red
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.DEBUG)
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(ColoredFormatter())
        logger.addHandler(handler)
        logger.propagate = False
    return logger


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

    _log = get_logger("PEL.logger")
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(entry)
        _log.info(f"Logged OK -> {LOG_FILE}")
    except OSError as e:
        _log.error(f"Log write FAILED: {e}")


def _system_timestamp():
    """Return formatted system clock timestamp."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
