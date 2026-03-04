#!/usr/bin/env python3
"""
Buzzer / Relay Test Script
============================
Runs through all buzzer patterns to verify relay wiring and active-low logic.

Port of: tests/test_buzzer_relay/test_buzzer_relay.ino (5 pattern tests)
Run with:  sudo python3 test_buzzer_relay.py
"""

import sys
import os
import time

# Allow running from tests/ directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "main"))

import RPi.GPIO as GPIO
import config
import buzzer


def header(title):
    print(f"\n{'=' * 40}")
    print(f"  {title}")
    print(f"{'=' * 40}")


def wait_and_label(label, seconds=2.0):
    print(f"\n  >>> {label}")
    time.sleep(0.3)


def main():
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    buzzer.setup()

    header("BUZZER / RELAY TEST")
    print(f"  Relay pin:  GPIO {config.PIN_RELAY} (BCM)")
    print(f"  Active LOW: {config.RELAY_ACTIVE_LOW}")
    print()
    print("  You should hear each buzzer pattern in sequence.")
    print("  Press Ctrl+C to abort at any time.")
    print()

    try:
        # Test 1: Single tick
        wait_and_label("Test 1/6: Single tick (50ms)")
        buzzer.tick()
        time.sleep(1.0)

        # Test 2: Double beep
        wait_and_label("Test 2/6: Double beep (2x100ms)")
        buzzer.double_beep()
        time.sleep(1.0)

        # Test 3: Cancel sound
        wait_and_label("Test 3/6: Cancel sound (2x400ms)")
        buzzer.cancel_sound()
        time.sleep(1.0)

        # Test 4: Success sound
        wait_and_label("Test 4/6: Success sound (200ms+500ms)")
        buzzer.success_sound()
        time.sleep(1.0)

        # Test 5: Fail sound
        wait_and_label("Test 5/6: Fail sound (800ms)")
        buzzer.fail_sound()
        time.sleep(1.0)

        # Test 6: Manual ON/OFF (hold 2 seconds)
        wait_and_label("Test 6/6: Continuous ON for 2 seconds")
        buzzer.buzzer_on()
        time.sleep(2.0)
        buzzer.buzzer_off()

        print()
        print("  All buzzer patterns complete!")
        print()

    except KeyboardInterrupt:
        print("\n  Aborted by user.")
        buzzer.buzzer_off()

    finally:
        buzzer.buzzer_off()
        GPIO.cleanup()
        print("  GPIO cleaned up. Done.")


if __name__ == "__main__":
    main()
