#!/usr/bin/env python3
"""
Dual GPS Integration Test — A7670E + GT-U7
=============================================
Tests both GPS modules running simultaneously, exactly as they would
during a real panic sequence. First module to return a valid fix wins.

Wiring required:
  - A7670E connected via USB (/dev/ttyUSB*)
  - GT-U7 connected via GPIO UART (/dev/serial0)

Run with:  sudo python3 test_dual_gps.py
"""

import sys
import os
import time

# Add main/ to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "main"))

import config
from a7670e import A7670E, find_usb_at_port
from gtu7 import GTU7


def init_a7670e():
    """Initialize A7670E modem and enable GNSS."""
    print("Initializing A7670E...")

    port = config.SERIAL_PORT
    if config.SERIAL_MODE == "usb" and port == "auto":
        detected = find_usb_at_port()
        if detected:
            port = detected
        else:
            print("  A7670E not detected on USB")
            return None

    pwrkey = config.PIN_PWRKEY if config.SERIAL_MODE == "gpio" else None

    modem = A7670E(
        port=port,
        baud=config.SERIAL_BAUD,
        fallback_baud=config.SERIAL_FALLBACK_BAUD,
        timeout=config.SERIAL_TIMEOUT,
        pwrkey_pin=pwrkey,
    )

    if not modem.is_connected:
        print("  A7670E: FAIL — not responding")
        return None

    modem.init_module()
    print("  A7670E: OK")
    return modem


def init_gtu7():
    """Initialize GT-U7 module."""
    print("Initializing GT-U7...")

    gtu7 = GTU7(
        port=config.GTU7_PORT,
        baud=config.GTU7_BAUD,
        timeout=config.GTU7_TIMEOUT,
    )

    if gtu7.warmup_check(duration=2.0):
        print("  GT-U7: OK — NMEA data received")
        return gtu7

    print("  GT-U7: FAIL — not detected")
    gtu7.close()
    return None


def dual_poll_test(modem, gtu7, duration=60):
    """
    Run the dual GPS poll loop for the given duration.
    Mirrors the logic in panic.py execute_panic().
    """
    print(f"\n{'='*50}")
    print(f"DUAL GPS POLL TEST ({duration}s)")
    print(f"{'='*50}")

    sources = []
    if modem:
        sources.append("A7670E")
    if gtu7:
        sources.append("GT-U7")

    if not sources:
        print("No GPS modules available — cannot test")
        return

    print(f"Active sources: {', '.join(sources)}")
    print()

    # Enable A7670E GNSS
    if modem:
        modem.enable_gnss()
        time.sleep(1.0)

    start = time.time()
    poll_count = 0

    while (time.time() - start) < duration:
        poll_count += 1
        remaining = duration - (time.time() - start)
        print(f"  Poll #{poll_count}  ({remaining:.0f}s remaining)")

        # Poll A7670E
        if modem:
            lat, lng, utc_time = modem.poll_gnss_once()
            if lat is not None:
                elapsed = time.time() - start
                print(f"\n  ✓ GPS FIX via A7670E! ({elapsed:.1f}s)")
                print(f"    Latitude:  {lat:.6f}")
                print(f"    Longitude: {lng:.6f}")
                if utc_time:
                    print(f"    UTC Time:  {utc_time}")
                return "A7670E", lat, lng, utc_time

        # Poll GT-U7
        if gtu7:
            lat, lng, utc_time = gtu7.poll_fix()
            if lat is not None:
                elapsed = time.time() - start
                print(f"\n  ✓ GPS FIX via GT-U7! ({elapsed:.1f}s)")
                print(f"    Latitude:  {lat:.6f}")
                print(f"    Longitude: {lng:.6f}")
                if utc_time:
                    print(f"    UTC Time:  {utc_time}")
                return "GT-U7", lat, lng, utc_time

        print("    No fix from either module...")
        time.sleep(config.GPS_POLL_INTERVAL)

    print(f"\n  ✗ No fix from either module in {duration}s")
    print("    (Normal indoors — GPS needs clear sky view)")
    return None


def main():
    print("Dual GPS Integration Test")
    print("=" * 50)
    print(f"A7670E: USB serial ({config.SERIAL_MODE})")
    print(f"GT-U7:  {config.GTU7_PORT} @ {config.GTU7_BAUD} baud")
    print()

    modem = init_a7670e()
    gtu7 = init_gtu7()

    if not modem and not gtu7:
        print("\nBoth modules unavailable — nothing to test.")
        return

    # Verify no serial port conflict
    print(f"\n{'='*50}")
    print("SERIAL PORT CHECK")
    print(f"{'='*50}")
    if modem:
        print(f"  A7670E port: {modem.port}")
    if gtu7:
        print(f"  GT-U7 port:  {gtu7.port}")
    if modem and gtu7 and modem.port == gtu7.port:
        print("  ✗ CONFLICT — both on same port!")
        print("  A7670E should be USB, GT-U7 on GPIO UART")
    else:
        print("  ✓ No conflicts — different ports")

    # Run dual poll
    result = dual_poll_test(modem, gtu7, duration=60)

    # Summary
    print(f"\n{'='*50}")
    print("TEST SUMMARY")
    print(f"{'='*50}")
    print(f"  A7670E:  {'available' if modem else 'not available'}")
    print(f"  GT-U7:   {'available' if gtu7 else 'not available'}")
    if result:
        source, lat, lng, utc_time = result
        print(f"  Winner:  {source}")
        print(f"  Fix:     {lat:.6f}, {lng:.6f}")
    else:
        print("  Winner:  none (no fix obtained)")
    print(f"{'='*50}")

    # Cleanup
    if modem:
        modem.disable_gnss()
        modem.close()
    if gtu7:
        gtu7.close()

    print("\nDone.")


if __name__ == "__main__":
    main()
