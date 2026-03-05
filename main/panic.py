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

def handle_panic_sequence(modem):
    """
    Full 4-phase panic sequence triggered by a button press.

    Phase 1: Hold to Arm     — 3s hold, red blink, buzzer tick each second
    Phase 2: Armed Confirm   — double beep, both LEDs flash
    Phase 3: Cancel Window   — 3s green blink, press button to cancel
    Phase 4: Execute Panic   — GPS → SMS → Log → Feedback

    Args:
        modem: Initialised A7670E instance

    Port of: handlePanicSequence() in main.ino (lines 177-297)
    """
    print("Button held — arming...")

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
            print(f"Arming... {tick_count}/3")

        # Armed after ARM_HOLD_TIME seconds
        if elapsed >= config.ARM_HOLD_TIME:
            armed = True
            break

        time.sleep(0.01)

    led.all_off()
    buzzer.buzzer_off()

    if not armed:
        print("Cancelled — released too early.")
        return

    # ─── PHASE 2: Armed Confirmation ───────────────────────────────────
    print("ARMED! Press button within 3s to cancel.")

    led.green_on()
    led.red_on()
    buzzer.double_beep()
    time.sleep(0.2)
    led.all_off()

    # Wait for button release before entering cancel window
    _wait_button_release()
    time.sleep(0.1)

    # ─── PHASE 3: Cancellation Window ─────────────────────────────────
    print("Cancel window open (3 seconds)...")

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
        print("CANCELLED by user.")
        led.red_on()
        buzzer.cancel_sound()
        time.sleep(0.5)
        led.all_off()
        logger.log_event("CANCELLED")
        print("System Idle.")
        return

    # ─── PHASE 4: Execute ─────────────────────────────────────────────
    print()
    print("=========================================")
    print(">>> EXECUTING PANIC ROUTINE <<<")
    print("=========================================")
    execute_panic(modem)


# ── Phase 4: Execute Panic Routine ────────────────────────────────────────

def execute_panic(modem):
    """
    GPS acquisition → SMS sending → Logging → Feedback.

    Key behaviour:
      - GPS retries indefinitely (restarts GNSS each cycle) until
        a valid fix is obtained. Set GPS_MAX_CYCLES > 0 to cap.
      - SMS retries with modem wake/reconnect until at least one
        contact receives the alert. Set SMS_MAX_CYCLES > 0 to cap.
      - The modem is woken before every critical operation so an
        idle-timeout (no response after long standby) is recovered
        automatically.

    Args:
        modem: Initialised A7670E instance

    Port of: executePanic() in main.ino (lines 299-400)
    """
    led.green_on()
    buzzer.tick()

    # ── Step 1: Acquire GPS (retry until success) ────────────────────
    print()
    print("[STEP 1/4] GPS ACQUISITION")
    print("-----------------------------------------")
    print("Searching for GPS satellites...")
    limit_label = ("unlimited"
                   if config.GPS_MAX_CYCLES == 0
                   else str(config.GPS_MAX_CYCLES))
    print(f"Cycle timeout: {config.GPS_TIMEOUT}s  |  Max cycles: {limit_label}")
    print()

    lat, lng, utc_time = None, None, None
    gps_cycle = 0

    while lat is None or lng is None:
        gps_cycle += 1
        cycle_tag = (f"#{gps_cycle}"
                     + (f"/{config.GPS_MAX_CYCLES}"
                        if config.GPS_MAX_CYCLES > 0 else ""))
        print(f"  --- GPS cycle {cycle_tag} ---")

        # Wake modem (recovers from idle timeout)
        led.blink_green(interval=0.3)
        if not modem.wake(max_attempts=config.MODEM_WAKE_ATTEMPTS):
            print(f"  Modem unresponsive — pausing {config.GPS_CYCLE_PAUSE}s...")
            time.sleep(config.GPS_CYCLE_PAUSE)
            if (config.GPS_MAX_CYCLES > 0
                    and gps_cycle >= config.GPS_MAX_CYCLES):
                break
            continue

        # Enable GNSS — fresh start each cycle
        modem.enable_gnss()
        time.sleep(1.0)

        lat, lng, utc_time = modem.acquire_gps(
            timeout=config.GPS_TIMEOUT,
            poll_interval=config.GPS_POLL_INTERVAL,
        )

        if lat is not None and lng is not None:
            break  # got a fix!

        # Cycle failed — restart GNSS for next attempt
        print(f"  GPS cycle {cycle_tag} — no fix. Restarting GNSS...")
        modem.disable_gnss()
        time.sleep(config.GPS_CYCLE_PAUSE)

        if (config.GPS_MAX_CYCLES > 0
                and gps_cycle >= config.GPS_MAX_CYCLES):
            print("  GPS max cycles reached — giving up.")
            break

    # Check ultimate GPS result
    if lat is None or lng is None:
        print()
        print("✗ GPS FAILED — No satellites found")
        print("  Possible causes:")
        print("  - Testing indoors (GPS needs clear sky)")
        print("  - GNSS antenna not connected")
        print("  - Module not powered properly")
        print("-----------------------------------------")
        led.all_off()
        led.red_on()
        buzzer.fail_sound()
        logger.log_event("FAILED — GPS Timeout")
        time.sleep(0.5)
        led.all_off()
        modem.disable_gnss()
        print("System Idle.")
        print("=========================================\n")
        return

    print()
    print("✓ GPS FIX ACQUIRED!")
    print(f"  Latitude:  {lat:.6f}")
    print(f"  Longitude: {lng:.6f}")
    if utc_time:
        print(f"  UTC Time:  {utc_time}")
    print("-----------------------------------------")

    # Turn off GNSS to free UART bandwidth for SMS
    modem.disable_gnss()

    # ── Step 2: Send SMS (retry until success) ───────────────────────
    print()
    print("[STEP 2/4] SMS TRANSMISSION")
    print("-----------------------------------------")

    map_link = modem.build_map_link(lat, lng)
    print(f"GPS Coords: {map_link}")
    print()
    print(f"Sending to {len(config.CONTACTS)} emergency contacts...")

    sms_ok = False
    sms_cycle = 0

    while not sms_ok:
        sms_cycle += 1
        cycle_tag = (f"#{sms_cycle}"
                     + (f"/{config.SMS_MAX_CYCLES}"
                        if config.SMS_MAX_CYCLES > 0 else ""))
        print(f"\n  --- SMS cycle {cycle_tag} ---")

        # Wake modem (may have gone idle during GPS)
        led.blink_green_fast(interval=0.3)
        if not modem.wake(max_attempts=config.MODEM_WAKE_ATTEMPTS):
            print(f"  Modem unresponsive — pausing {config.SMS_CYCLE_PAUSE}s...")
            time.sleep(config.SMS_CYCLE_PAUSE)
            if (config.SMS_MAX_CYCLES > 0
                    and sms_cycle >= config.SMS_MAX_CYCLES):
                print("  SMS max cycles reached — giving up.")
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

        print(f"  SMS cycle {cycle_tag} failed — retrying in "
              f"{config.SMS_CYCLE_PAUSE}s...")
        time.sleep(config.SMS_CYCLE_PAUSE)

        if (config.SMS_MAX_CYCLES > 0
                and sms_cycle >= config.SMS_MAX_CYCLES):
            print("  SMS max cycles reached — giving up.")
            break

    print("-----------------------------------------")

    # ── Step 3: Log event ────────────────────────────────────────────
    print()
    print("[STEP 3/4] FILE LOGGING")
    print("-----------------------------------------")
    if sms_ok:
        logger.log_event("SUCCESS", lat, lng, utc_time)
    else:
        logger.log_event("FAILED — SMS Send Error", lat, lng, utc_time)
    print("-----------------------------------------")

    # ── Step 4: Feedback ─────────────────────────────────────────────
    print()
    print("[STEP 4/4] FINAL STATUS")
    print("-----------------------------------------")

    led.all_off()

    if sms_ok:
        print("✓ PANIC ALERT SENT SUCCESSFULLY")
        print("  Emergency contacts have been notified")
        print("  Location shared via SMS")
        led.green_on()
        buzzer.success_sound()
        time.sleep(0.5)
    else:
        print("✗ PANIC ALERT FAILED")
        print("  Unable to send SMS to contacts")
        print("  Check SIM card and network signal")
        led.red_on()
        buzzer.fail_sound()
        time.sleep(0.5)

    led.all_off()
    print("-----------------------------------------")
    print("System Idle.")
    print("=========================================\n")
    time.sleep(0.5)
