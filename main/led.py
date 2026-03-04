"""
LED Control Module
==================
Green and Red LED control with non-blocking blink via threading.
Direct port of LED HELPERS section in main.ino (lines 74-85)
plus extended blink functions used throughout the panic sequence.

Thread-safe: a single daemon thread handles the blink loop.
Calling any blink function stops the previous pattern first.
"""

import RPi.GPIO as GPIO
import threading
import time
from config import PIN_LED_GREEN, PIN_LED_RED


# ── Internal state ──────────────────────────────────────────────────────────
_blink_thread = None
_blink_stop = threading.Event()
_lock = threading.Lock()


# ── Setup ───────────────────────────────────────────────────────────────────

def setup():
    """
    Initialize both LED pins as outputs, all OFF.
    Call once during system startup.
    """
    GPIO.setup(PIN_LED_GREEN, GPIO.OUT)
    GPIO.setup(PIN_LED_RED, GPIO.OUT)
    all_off()


# ── Direct control ──────────────────────────────────────────────────────────

def green_on():
    GPIO.output(PIN_LED_GREEN, GPIO.HIGH)


def green_off():
    GPIO.output(PIN_LED_GREEN, GPIO.LOW)


def red_on():
    GPIO.output(PIN_LED_RED, GPIO.HIGH)


def red_off():
    GPIO.output(PIN_LED_RED, GPIO.LOW)


def all_off():
    """Turn both LEDs off and stop any running blink pattern."""
    stop_blink()
    green_off()
    red_off()


# ── Non-blocking blink engine ──────────────────────────────────────────────

def _blink_worker(pin, interval):
    """
    Internal worker: toggles *pin* at *interval* seconds until _blink_stop is set.
    Runs as a daemon thread so it won't prevent interpreter exit.
    """
    state = False
    while not _blink_stop.is_set():
        state = not state
        GPIO.output(pin, GPIO.HIGH if state else GPIO.LOW)
        # Use wait() instead of sleep() so we can interrupt quickly
        _blink_stop.wait(interval)
    # Ensure LED is off when stopping
    GPIO.output(pin, GPIO.LOW)


def stop_blink():
    """
    Stop the currently running blink thread (if any).
    Blocks briefly until the thread exits cleanly.
    """
    global _blink_thread
    with _lock:
        if _blink_thread is not None and _blink_thread.is_alive():
            _blink_stop.set()
            _blink_thread.join(timeout=2.0)
        _blink_stop.clear()
        _blink_thread = None


def _start_blink(pin, interval):
    """
    Internal: stop previous blink and start a new one on *pin*.
    """
    global _blink_thread
    stop_blink()
    with _lock:
        _blink_stop.clear()
        _blink_thread = threading.Thread(
            target=_blink_worker,
            args=(pin, interval),
            daemon=True,
            name="led-blink"
        )
        _blink_thread.start()


# ── Public blink functions ──────────────────────────────────────────────────

def blink_red(interval=0.2):
    """
    Non-blocking red LED blink.
    Used during ARM phase countdown (Phase 1) and error states.
    Default 200ms matches main.ino BLINK_FAST pattern.
    """
    _start_blink(PIN_LED_RED, interval)


def blink_green(interval=0.5):
    """
    Non-blocking green LED blink — slow.
    Used during GPS acquisition (Phase 2: 500ms).
    """
    _start_blink(PIN_LED_GREEN, interval)


def blink_green_fast(interval=0.3):
    """
    Non-blocking green LED blink — fast.
    Used during SMS sending (Phase 3: 300ms).
    """
    _start_blink(PIN_LED_GREEN, interval)


def blink_both(interval=0.3):
    """
    Alternate red/green blink. Used for special status indication.
    Since we only have one blink thread, this manually alternates both LEDs.
    """
    stop_blink()

    def _alternate_worker():
        toggle = False
        while not _blink_stop.is_set():
            if toggle:
                GPIO.output(PIN_LED_GREEN, GPIO.HIGH)
                GPIO.output(PIN_LED_RED, GPIO.LOW)
            else:
                GPIO.output(PIN_LED_GREEN, GPIO.LOW)
                GPIO.output(PIN_LED_RED, GPIO.HIGH)
            toggle = not toggle
            _blink_stop.wait(interval)
        GPIO.output(PIN_LED_GREEN, GPIO.LOW)
        GPIO.output(PIN_LED_RED, GPIO.LOW)

    global _blink_thread
    with _lock:
        _blink_stop.clear()
        _blink_thread = threading.Thread(
            target=_alternate_worker,
            daemon=True,
            name="led-blink-both"
        )
        _blink_thread.start()


def solid_green():
    """Stop blink, turn green ON solid. Indicates idle/ready state."""
    stop_blink()
    red_off()
    green_on()


def solid_red():
    """Stop blink, turn red ON solid. Indicates error state."""
    stop_blink()
    green_off()
    red_on()
