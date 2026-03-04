#!/usr/bin/env python3
"""
LED Test Script
=================
Runs through all LED patterns to verify wiring and blink functions.

Port of: tests/test_led/test_led.ino (7 pattern tests)
Run with:  sudo python3 test_led.py
"""

import sys
import os
import time

# Allow running from tests/ directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "main"))

import RPi.GPIO as GPIO
import config
import led


def header(title):
    print(f"\n{'=' * 40}")
    print(f"  {title}")
    print(f"{'=' * 40}")


def test_step(label, seconds=3.0):
    """Print step label, wait for visibility, then auto-advance."""
    print(f"\n  >>> {label}  ({seconds}s)")
    time.sleep(seconds)


def main():
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    led.setup()

    header("LED TEST")
    print(f"  Green LED: GPIO {config.PIN_GREEN_LED} (BCM)")
    print(f"  Red LED:   GPIO {config.PIN_RED_LED} (BCM)")
    print()
    print("  Watch LEDs cycle through all patterns.")
    print("  Press Ctrl+C to abort at any time.")
    print()

    try:
        # Test 1: Green ON solid
        test_step("Test 1/8: Green LED solid ON")
        led.solid_green()
        time.sleep(3.0)
        led.all_off()

        # Test 2: Red ON solid
        test_step("Test 2/8: Red LED solid ON")
        led.solid_red()
        time.sleep(3.0)
        led.all_off()

        # Test 3: Both ON solid
        test_step("Test 3/8: Both LEDs solid ON")
        led.green_on()
        led.red_on()
        time.sleep(3.0)
        led.all_off()

        # Test 4: Red blink fast (arming pattern)
        test_step("Test 4/8: Red blink FAST (200ms — arming)", seconds=0)
        led.blink_red(interval=0.2)
        time.sleep(5.0)
        led.all_off()

        # Test 5: Green blink slow (cancel window)
        test_step("Test 5/8: Green blink SLOW (500ms — cancel window)", seconds=0)
        led.blink_green(interval=0.5)
        time.sleep(5.0)
        led.all_off()

        # Test 6: Green blink fast (GPS search / SMS)
        test_step("Test 6/8: Green blink FAST (300ms — GPS/SMS)", seconds=0)
        led.blink_green_fast(interval=0.3)
        time.sleep(5.0)
        led.all_off()

        # Test 7: Alternating both LEDs
        test_step("Test 7/8: Alternating red/green blink", seconds=0)
        led.blink_both(interval=0.3)
        time.sleep(5.0)
        led.all_off()

        # Test 8: Rapid cycle — green, red, off (3 reps)
        test_step("Test 8/8: Rapid cycle (green → red → off) × 3", seconds=0)
        for _ in range(3):
            led.green_on()
            time.sleep(0.3)
            led.green_off()
            led.red_on()
            time.sleep(0.3)
            led.red_off()
            time.sleep(0.3)

        led.all_off()
        print()
        print("  All LED patterns complete!")
        print()

    except KeyboardInterrupt:
        print("\n  Aborted by user.")
        led.all_off()

    finally:
        led.all_off()
        GPIO.cleanup()
        print("  GPIO cleaned up. Done.")


if __name__ == "__main__":
    main()
