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
    Initialize all peripherals. Returns A7670E modem instance.
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

    print("=================================")
    print(" Panic Button Emergency Locator")
    print(" Raspberry Pi + A7670E Edition")
    print("=================================")

    # ── A7670E modem ────────────────────────────────────────────────────
    print()
    print("Modem: ", end="")

    modem = A7670E(
        port=config.SERIAL_PORT,
        baud=config.SERIAL_BAUD,
        fallback_baud=config.SERIAL_FALLBACK_BAUD,
        timeout=config.SERIAL_TIMEOUT,
    )

    if modem.is_connected:
        if modem.init_module():
            print("Modem: OK")
        else:
            print("Modem: WARNING — check SIM / signal")
    else:
        print("Modem: NOT CONNECTED — check wiring")

    print("---------------------------------")
    print(f"Owner:    {config.OWNER_NAME}")
    print(f"Contacts: {len(config.CONTACTS)}")
    for c in config.CONTACTS:
        print(f"  • {c['name']} ({c['number']})")
    print(f"Log file: {config.LOG_FILE}")
    print("---------------------------------")
    print("System Ready. Hold button 3s to arm.")
    print()

    # Indicate ready state — solid green LED
    led.solid_green()

    return modem


def loop(modem):
    """
    Main polling loop. Checks for button press and triggers panic sequence.
    Port of: loop() in main.ino (lines 172-178)
    """
    while True:
        if GPIO.input(config.PIN_BUTTON) == GPIO.LOW:
            time.sleep(config.DEBOUNCE_DELAY)
            if GPIO.input(config.PIN_BUTTON) == GPIO.LOW:
                panic.handle_panic_sequence(modem)
                # Re-establish idle state after sequence completes
                led.solid_green()

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
