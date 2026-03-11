"""
Panic Sequence — 4-Phase State Machine
========================================
Core logic: ARM → CONFIRM → CANCEL WINDOW → EXECUTE.
Direct 1:1 port of handlePanicSequence() + executePanic() from main.ino
(lines 166-400).

This module does NOT import RPi.GPIO directly — it delegates to
buzzer.py, led.py, and logger.py for all hardware I/O.
"""

import time
import RPi.GPIO as GPIO

import config
import buzzer
import led
import logger
from logger import get_logger

log = get_logger("PEL.panic")


# ── Helpers ────────────────────────────────────────────────────────────────

def _button_pressed():
    """Return True if button is currently pressed (active LOW)."""
    return GPIO.input(config.PIN_BUTTON) == GPIO.LOW


def _wait_button_release(timeout=10.0):
    """Block until button is released or timeout."""
    end = time.time() + timeout
    while _button_pressed() and time.time() < end:
        time.sleep(0.01)


# ── Phase 1–3: Handle Panic Sequence ──────────────────────────────────────

def handle_panic_sequence(modem, gtu7_module=None, gps_poller=None):
    """
    Full 4-phase panic sequence triggered by a button press.

    Phase 1: Hold to Arm     — 3s hold, red blink, buzzer tick each second
    Phase 2: Armed Confirm   — double beep, both LEDs flash
    Phase 3: Cancel Window   — 3s green blink, press button to cancel
    Phase 4: Execute Panic   — GPS → SMS → Log → Feedback

    Args:
        modem: Initialised A7670E instance
        gtu7_module: Optional GTU7 instance (None if disabled/unavailable)
        gps_poller: Optional GPSPoller instance for cached background fixes

    Port of: handlePanicSequence() in main.ino (lines 177-297)
    """
    log.warning("Button held — arming...")

    # ─── PHASE 1: Hold to Arm ──────────────────────────────────────────
    hold_start = time.time()
    tick_count = 0
    armed = False

    led.blink_red(interval=0.2)          # Fast red blink while holding

    while _button_pressed():
        elapsed = time.time() - hold_start

        # Buzzer tick once per second (up to 3)
        second = int(elapsed)
        if second > tick_count and tick_count < 3:
            tick_count += 1
            buzzer.tick()
            log.info(f"Arming... {tick_count}/3")

        # Armed after ARM_HOLD_TIME seconds
        if elapsed >= config.ARM_HOLD_TIME:
            armed = True
            break

        time.sleep(0.01)

    led.all_off()
    buzzer.buzzer_off()

    if not armed:
        log.warning("Cancelled — released too early.")
        return

    # ─── PHASE 2: Armed Confirmation ───────────────────────────────
    log.warning("ARMED! Press button within 3s to cancel.")

    led.green_on()
    led.red_on()
    buzzer.double_beep()
    time.sleep(0.2)
    led.all_off()

    # Wait for button release before entering cancel window
    _wait_button_release()
    time.sleep(0.1)

    # ─── PHASE 3: Cancellation Window ─────────────────────────────────
    log.info("Cancel window open (3 seconds)...")

    cancel_start = time.time()
    cancelled = False

    led.blink_green(interval=0.5)        # Slow green blink

    while (time.time() - cancel_start) < config.CANCEL_WINDOW:
        if _button_pressed():
            time.sleep(config.DEBOUNCE_DELAY)
            if _button_pressed():
                cancelled = True
                _wait_button_release()
                break
        time.sleep(0.01)

    led.all_off()

    if cancelled:
        log.warning("CANCELLED by user.")
        led.red_on()
        buzzer.cancel_sound()
        time.sleep(0.5)
        led.all_off()
        logger.log_event("CANCELLED")
        log.info("System Idle.")
        return

    # ─── PHASE 4: Execute ─────────────────────────────────────────
    log.warning("=========================================")
    log.warning(">>> EXECUTING PANIC ROUTINE <<<")
    log.warning("=========================================")
    execute_panic(modem, gtu7_module, gps_poller)


# ── Phase 4: Execute Panic Routine ────────────────────────────────────────

def execute_panic(modem, gtu7_module=None, gps_poller=None):
    """
    GPS acquisition → SMS sending → Logging → Feedback.

    Key behaviour:
      - First checks the background GPS poller for a cached fix.
        If a fresh fix exists (< GPS_BG_MAX_AGE seconds old), it's
        used immediately — no waiting for satellites.
      - If no cached fix, polls BOTH A7670E GNSS and GT-U7 each cycle
        until a valid fix is obtained.
      - Pauses the background poller during SMS (modem is busy).
      - SMS retries with modem wake/reconnect until at least one
        contact receives the alert.

    Args:
        modem: Initialised A7670E instance
        gtu7_module: Optional GTU7 instance (None to use A7670E only)
        gps_poller: Optional GPSPoller instance for cached background fixes

    Port of: executePanic() in main.ino (lines 299-400)
    """
    led.green_on()
    buzzer.tick()

    # ── Step 1: Acquire GPS (retry until success) ────────────────────
    log.info("")
    log.info("[STEP 1/4] GPS ACQUISITION")
    log.info("-----------------------------------------")
    log.info("Searching for GPS satellites...")
    limit_label = ("unlimited"
                   if config.GPS_MAX_CYCLES == 0
                   else str(config.GPS_MAX_CYCLES))
    gps_sources = "A7670E"
    if gtu7_module and gtu7_module.is_enabled:
        gps_sources += " + GT-U7"
    log.info(f"GPS sources: {gps_sources}")
    log.info(f"Cycle timeout: {config.GPS_TIMEOUT}s  |  Max cycles: {limit_label}")

    lat, lng, utc_time = None, None, None
    gps_source = None
    gps_cycle = 0

    # ── Check background poller for cached fix first ─────────────
    if gps_poller and gps_poller.has_fix:
        lat, lng, utc_time, gps_source = gps_poller.get_fix(
            max_age=config.GPS_BG_MAX_AGE
        )
        if lat is not None:
            age = gps_poller.fix_age
            log.info(f"  Using cached background fix ({age:.0f}s old)")

    if lat is None or lng is None:
        # No cached fix — fall back to active polling
        if gps_poller:
            gps_poller.pause()  # pause background poller to avoid conflicts

        while lat is None or lng is None:
            gps_cycle += 1
            cycle_tag = (f"#{gps_cycle}"
                         + (f"/{config.GPS_MAX_CYCLES}"
                            if config.GPS_MAX_CYCLES > 0 else ""))
            log.info(f"  --- GPS cycle {cycle_tag} ---")

            # Wake modem (recovers from idle timeout)
            led.blink_green(interval=0.3)
            if not modem.wake(max_attempts=config.MODEM_WAKE_ATTEMPTS):
                log.warning(f"  Modem unresponsive — pausing {config.GPS_CYCLE_PAUSE}s...")
                time.sleep(config.GPS_CYCLE_PAUSE)
                if (config.GPS_MAX_CYCLES > 0
                        and gps_cycle >= config.GPS_MAX_CYCLES):
                    break
                continue

            # Enable A7670E GNSS — fresh start each cycle
            modem.enable_gnss()
            time.sleep(1.0)

            # Dual-poll loop: check both GPS sources each interval
            poll_start = time.time()
            poll_count = 0

            while (time.time() - poll_start) < config.GPS_TIMEOUT:
                poll_count += 1
                remaining = config.GPS_TIMEOUT - (time.time() - poll_start)
                log.info(f"  GPS poll #{poll_count}  ({remaining:.0f}s remaining)")

                # Poll A7670E GNSS
                lat, lng, utc_time = modem.poll_gnss_once()
                if lat is not None:
                    gps_source = "A7670E"
                    break

                # Poll GT-U7 (if available)
                if gtu7_module and gtu7_module.is_enabled:
                    lat, lng, utc_time = gtu7_module.poll_fix()
                    if lat is not None:
                        gps_source = "GT-U7"
                        break

                log.warning("  No fix yet...")

                # Wait before next poll, but check timeout
                wait_end = time.time() + config.GPS_POLL_INTERVAL
                while time.time() < wait_end and (time.time() - poll_start) < config.GPS_TIMEOUT:
                    time.sleep(0.1)

            if lat is not None and lng is not None:
                break  # got a fix!

            # Cycle failed — restart GNSS for next attempt
            log.warning(f"  GPS cycle {cycle_tag} — no fix. Restarting GNSS...")
            modem.disable_gnss()
            time.sleep(config.GPS_CYCLE_PAUSE)

            if (config.GPS_MAX_CYCLES > 0
                    and gps_cycle >= config.GPS_MAX_CYCLES):
                log.error("  GPS max cycles reached — giving up.")
                break

        # Resume background poller after active polling
        if gps_poller:
            gps_poller.resume()

    # Check ultimate GPS result
    if lat is None or lng is None:
        log.error("")
        log.error("✗ GPS FAILED — No satellites found")
        log.error("  Possible causes:")
        log.error("  - Testing indoors (GPS needs clear sky)")
        log.error("  - GNSS antenna not connected")
        log.error("  - Module not powered properly")
        log.error("-----------------------------------------")
        led.all_off()
        led.red_on()
        buzzer.fail_sound()
        logger.log_event("FAILED — GPS Timeout")
        time.sleep(0.5)
        led.all_off()
        modem.disable_gnss()
        # Resume background poller even on failure
        if gps_poller:
            gps_poller.resume()
        log.info("System Idle.")
        log.info("=========================================\n")
        return

    log.info("")
    log.info(f"✓ GPS FIX via {gps_source}!")
    log.info(f"  Latitude:  {lat:.6f}")
    log.info(f"  Longitude: {lng:.6f}")
    if utc_time:
        log.info(f"  UTC Time:  {utc_time}")
    log.info("-----------------------------------------")

    # Turn off GNSS to free UART bandwidth for SMS
    modem.disable_gnss()

    # Pause background GPS during SMS (modem busy with AT+CMGS)
    if gps_poller:
        gps_poller.pause()

    # ── Step 2: Send SMS (retry until success) ───────────────────────
    log.info("")
    log.info("[STEP 2/4] SMS TRANSMISSION")
    log.info("-----------------------------------------")

    map_link = modem.build_map_link(lat, lng)
    log.info(f"GPS Coords: {map_link}")
    log.info("")
    log.info(f"Sending to {len(config.CONTACTS)} emergency contacts...")

    sms_ok = False
    sms_cycle = 0

    while not sms_ok:
        sms_cycle += 1
        cycle_tag = (f"#{sms_cycle}"
                     + (f"/{config.SMS_MAX_CYCLES}"
                        if config.SMS_MAX_CYCLES > 0 else ""))
        log.info(f"\n  --- SMS cycle {cycle_tag} ---")

        # Wake modem (may have gone idle during GPS)
        led.blink_green_fast(interval=0.3)
        if not modem.wake(max_attempts=config.MODEM_WAKE_ATTEMPTS):
            log.warning(f"  Modem unresponsive — pausing {config.SMS_CYCLE_PAUSE}s...")
            time.sleep(config.SMS_CYCLE_PAUSE)
            if (config.SMS_MAX_CYCLES > 0
                    and sms_cycle >= config.SMS_MAX_CYCLES):
                log.error("  SMS max cycles reached — giving up.")
                break
            continue

        # Re-init SMS mode (may be lost after reconnect)
        modem.send_command("AT+CMGF=1", timeout=1.0)
        modem.send_command('AT+CSCS="GSM"', timeout=1.0)
        modem.send_command("AT+CSMP=17,167,0,0", timeout=1.0)

        sms_ok = modem.send_to_all_contacts(
            contacts=config.CONTACTS,
            map_link=map_link,
            owner_name=config.OWNER_NAME,
            sms_template=config.SMS_TEMPLATE,
            retries=config.SMS_RETRY_COUNT,
        )

        if sms_ok:
            break

        log.warning(f"  SMS cycle {cycle_tag} failed — retrying in "
              f"{config.SMS_CYCLE_PAUSE}s...")
        time.sleep(config.SMS_CYCLE_PAUSE)

        if (config.SMS_MAX_CYCLES > 0
                and sms_cycle >= config.SMS_MAX_CYCLES):
            log.error("  SMS max cycles reached — giving up.")
            break

    log.info("-----------------------------------------")

    # ── Step 3: Log event ────────────────────────────────────────
    log.info("")
    log.info("[STEP 3/4] FILE LOGGING")
    log.info("-----------------------------------------")
    if sms_ok:
        logger.log_event("SUCCESS", lat, lng, utc_time)
    else:
        logger.log_event("FAILED — SMS Send Error", lat, lng, utc_time)
    log.info("-----------------------------------------")

    # ── Step 4: Feedback ─────────────────────────────────────────
    log.info("")
    log.info("[STEP 4/4] FINAL STATUS")
    log.info("-----------------------------------------")

    led.all_off()

    if sms_ok:
        log.info("✓ PANIC ALERT SENT SUCCESSFULLY")
        log.info("  Emergency contacts have been notified")
        log.info("  Location shared via SMS")
        led.green_on()
        buzzer.success_sound()
        time.sleep(0.5)
    else:
        log.error("✗ PANIC ALERT FAILED")
        log.error("  Unable to send SMS to contacts")
        log.error("  Check SIM card and network signal")
        led.red_on()
        buzzer.fail_sound()
        time.sleep(0.5)

    led.all_off()

    # Resume background GPS polling
    if gps_poller:
        gps_poller.resume()

    log.info("-----------------------------------------")
    log.info("System Idle.")
    log.info("=========================================\n")
    time.sleep(0.5)
