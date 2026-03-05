#!/usr/bin/env python3
"""
GT-U7 GPS Module — Standalone Test
====================================
Tests the GT-U7 (u-blox NEO-6M) GPS module on GPIO UART.

Wiring:
  GT-U7 VCC → Pi Pin 1 (3.3V) or Pin 2 (5V)
  GT-U7 GND → Pi Pin 6 (GND)
  GT-U7 TX  → Pi Pin 10 (GPIO 15 / RX)
  GT-U7 RX  → Pi Pin 8  (GPIO 14 / TX)  (optional)

Prerequisites:
  - enable_uart=1 in /boot/firmware/config.txt
  - dtoverlay=disable-bt in /boot/firmware/config.txt
  - Reboot after config changes

Run with:  sudo python3 test_gtu7.py
"""

import sys
import os
import time

# Add main/ to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "main"))

import config
from gtu7 import GTU7


def test_raw_nmea(gtu7, duration=10):
    """Read and print raw NMEA sentences for the given duration."""
    print(f"\n{'='*50}")
    print(f"TEST 1: Raw NMEA stream ({duration}s)")
    print(f"{'='*50}")

    if not gtu7.is_enabled:
        print("FAIL — serial port not open")
        return False

    gtu7.ser.reset_input_buffer()
    start = time.time()
    sentence_count = 0

    while (time.time() - start) < duration:
        if gtu7.ser.in_waiting:
            try:
                line = gtu7.ser.readline().decode("ascii", errors="ignore").strip()
                if line.startswith("$"):
                    sentence_count += 1
                    print(f"  [{sentence_count:3d}] {line}")
            except Exception as e:
                print(f"  Read error: {e}")
        time.sleep(0.01)

    print(f"\nReceived {sentence_count} NMEA sentences in {duration}s")
    return sentence_count > 0


def test_fix_polling(gtu7, duration=30):
    """Poll for a GPS fix for the given duration."""
    print(f"\n{'='*50}")
    print(f"TEST 2: GPS fix polling ({duration}s)")
    print(f"{'='*50}")

    start = time.time()
    poll_count = 0

    while (time.time() - start) < duration:
        poll_count += 1
        remaining = duration - (time.time() - start)
        print(f"\n  Poll #{poll_count} ({remaining:.0f}s remaining)...")

        lat, lng, utc_time = gtu7.poll_fix()

        if lat is not None:
            print(f"\n  ✓ GPS FIX ACQUIRED!")
            print(f"    Latitude:  {lat:.6f}")
            print(f"    Longitude: {lng:.6f}")
            if utc_time:
                print(f"    UTC Time:  {utc_time}")
            elapsed = time.time() - start
            print(f"    Fix time:  {elapsed:.1f}s")
            return True

        print("    No fix yet...")
        time.sleep(2.0)

    print(f"\n  ✗ No fix obtained in {duration}s")
    print("    (Normal indoors — GPS needs clear sky view)")
    return False


def main():
    port = config.GTU7_PORT
    baud = config.GTU7_BAUD
    timeout = config.GTU7_TIMEOUT

    print("GT-U7 GPS Module Test")
    print("=====================")
    print(f"Port: {port}  Baud: {baud}")
    print()

    gtu7 = GTU7(port=port, baud=baud, timeout=timeout)

    # Warm-up check
    print("Warm-up check (2s)...", end=" ")
    if not gtu7.warmup_check(duration=2.0):
        print("FAIL")
        print("\nGT-U7 not detected. Check:")
        print("  - Wiring (VCC, GND, TX→Pi RX)")
        print("  - enable_uart=1 in /boot/firmware/config.txt")
        print("  - dtoverlay=disable-bt in /boot/firmware/config.txt")
        print("  - Reboot after config changes")
        gtu7.close()
        return

    print("OK — NMEA data received")

    # Run tests (5 minutes total: 30s NMEA + 270s fix polling)
    test1_ok = test_raw_nmea(gtu7, duration=30)
    test2_ok = test_fix_polling(gtu7, duration=270)

    # Summary
    print(f"\n{'='*50}")
    print("TEST SUMMARY")
    print(f"{'='*50}")
    print(f"  NMEA stream:  {'PASS' if test1_ok else 'FAIL'}")
    print(f"  GPS fix:      {'PASS' if test2_ok else 'NO FIX (normal indoors)'}")
    print(f"{'='*50}")

    gtu7.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
