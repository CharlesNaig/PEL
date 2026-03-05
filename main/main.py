#!/usr/bin/env python3
"""
Panic Button Emergency Locator — Main Entry Point
====================================================
Raspberry Pi + SIMCOM A7670E production firmware.

Port of: setup() + loop() in main.ino (lines 125-175)
Run with:  sudo python3 main.py
(sudo required for GPIO access on most Pi configurations)
"""

import time
import sys
import RPi.GPIO as GPIO

import config
from a7670e import A7670E
import buzzer
import led
import panic


def setup():
    """
    Initialize all peripherals with warm-up component checks.
    Returns A7670E modem instance (or None if modem unavailable).
    Port of: setup() in main.ino (lines 125-170)
    """
    # ── GPIO global config ──────────────────────────────────────────────
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)

    # ── Button ──────────────────────────────────────────────────────────
    GPIO.setup(config.PIN_BUTTON, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    # ── Peripherals ─────────────────────────────────────────────────────
    buzzer.setup()
    led.setup()

    # ── Power-on confirmation beep ──────────────────────────────────────
    buzzer.tick()

    print("=================================")
    print(" Panic Button Emergency Locator")
    print(" Raspberry Pi + A7670E Edition")
    print("=================================")
    print()

    # ── Component warm-up checks ────────────────────────────────────────
    print("Warming up — checking components...")
    print("---------------------------------")
    all_ok = True

    # 1) Green LED
    led.green_on()
    time.sleep(0.3)
    led.green_off()
    print("  Green LED : OK")

    # 2) Red LED
    led.red_on()
    time.sleep(0.3)
    led.red_off()
    print("  Red LED   : OK")

    # 3) Buzzer (short tick)
    buzzer.tick()
    print("  Buzzer    : OK")

    # 4) Button GPIO (verify it's readable — HIGH when not pressed)
    try:
        btn_state = GPIO.input(config.PIN_BUTTON)
        if btn_state == GPIO.HIGH:
            print("  Button    : OK (idle)")
        else:
            print("  Button    : OK (pressed — release it)")
    except Exception:
        print("  Button    : FAIL")
        all_ok = False

    # 5) A7670E modem
    print("  Modem     : detecting...", end="\r")
    port = config.SERIAL_PORT
    modem = None
    modem_ok = False

    if config.SERIAL_MODE == "usb" and port == "auto":
        from a7670e import find_usb_at_port
        detected = find_usb_at_port()
        if detected:
            port = detected
        else:
            port = None
    elif port == "auto":
        port = "/dev/serial0"

    pwrkey = config.PIN_PWRKEY if config.SERIAL_MODE == "gpio" else None

    if port is not None:
        modem = A7670E(
            port=port,
            baud=config.SERIAL_BAUD,
            fallback_baud=config.SERIAL_FALLBACK_BAUD,
            timeout=config.SERIAL_TIMEOUT,
            pwrkey_pin=pwrkey,
        )

    if modem and modem.is_connected:
        if modem.init_module():
            print("  Modem     : OK                ")
            modem_ok = True
        else:
            print("  Modem     : WARNING — check SIM / signal")
            modem_ok = True  # modem exists but SIM issue
    elif modem:
        print("  Modem     : FAIL — not responding")
        all_ok = False
    else:
        print("  Modem     : FAIL — not detected  ")
        all_ok = False

    # Ensure buzzer is definitely off after warm-up
    buzzer.buzzer_off()

    # ── Status summary ──────────────────────────────────────────────────
    print("---------------------------------")
    print(f"Owner:    {config.OWNER_NAME}")
    print(f"Contacts: {len(config.CONTACTS)}")
    for c in config.CONTACTS:
        print(f"  • {c['name']} ({c['number']})")
    print(f"Log file: {config.LOG_FILE}")
    print("---------------------------------")

    if all_ok:
        print("All components OK — System Ready.")
        print("Hold button 3s to arm.")
        led.solid_green()
        buzzer.double_beep()
    elif modem_ok:
        print("System Ready (modem has warnings).")
        print("Hold button 3s to arm.")
        led.solid_green()
        buzzer.double_beep()
    else:
        print("WARNING: Modem not available!")
        print("SMS/GPS will not work until modem is connected.")
        print("System running in limited mode — hold button 3s to arm.")
        led.blink_red(interval=1.0)
        buzzer.fail_sound()
        buzzer.buzzer_off()   # guarantee buzzer is silent after fail tone

    print()
    return modem


def loop(modem):
    """
    Main polling loop. Checks for button press and triggers panic sequence.
    Sends periodic keepalive AT pings so the module never goes stale.
    Port of: loop() in main.ino (lines 172-178)
    """
    last_keepalive = time.time()

    while True:
        if GPIO.input(config.PIN_BUTTON) == GPIO.LOW:
            time.sleep(config.DEBOUNCE_DELAY)
            if GPIO.input(config.PIN_BUTTON) == GPIO.LOW:
                panic.handle_panic_sequence(modem)
                # Re-establish idle state after sequence completes
                led.solid_green()
                last_keepalive = time.time()

        # Periodic keepalive — prevents the A7670E from becoming
        # unresponsive after long idle periods.
        if (modem and config.KEEPALIVE_INTERVAL > 0
                and (time.time() - last_keepalive) >= config.KEEPALIVE_INTERVAL):
            resp = modem.send_command("AT", timeout=2.0)
            if "OK" not in resp:
                print("[KEEPALIVE] Module unresponsive — waking...")
                modem.wake(max_attempts=config.MODEM_WAKE_ATTEMPTS)
            last_keepalive = time.time()

        time.sleep(0.01)  # ~10ms loop rate, same as delay(10) in Arduino


def main():
    """Application entry point with clean shutdown."""
    modem = None
    try:
        modem = setup()
        loop(modem)

    except KeyboardInterrupt:
        print("\nShutdown requested (Ctrl+C)")

    except Exception as e:
        print(f"\nFATAL ERROR: {e}")
        import traceback
        traceback.print_exc()

    finally:
        print("Cleaning up...")
        led.all_off()
        buzzer.buzzer_off()
        if modem:
            modem.disable_gnss()
            modem.close()
        GPIO.cleanup()
        print("Goodbye.")
        sys.exit(0)


if __name__ == "__main__":
    main()
