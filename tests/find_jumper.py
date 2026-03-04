#!/usr/bin/env python3
"""Scan all GPIO pins to find which two are bridged by a jumper wire."""
import RPi.GPIO as GPIO
import time

GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)

# Skip I2C (2,3) and other system-reserved pins to avoid "GPIO busy"
pins = [4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27]

bcm_to_phys = {
    4:7, 5:29, 6:31, 7:26, 8:24, 9:21, 10:19, 11:23,
    12:32, 13:33, 14:8, 15:10, 16:36, 17:11, 18:12, 19:35,
    20:38, 21:40, 22:15, 23:16, 24:18, 25:22, 26:37, 27:13,
}

print("Scanning all GPIO pins to find your jumper wire...")
print("(Keep jumper connected, A7670E disconnected)\n")

found = []

for out_pin in pins:
    try:
        GPIO.setup(out_pin, GPIO.OUT)
        GPIO.output(out_pin, GPIO.LOW)
    except Exception:
        continue

    usable_inputs = []
    for in_pin in pins:
        if in_pin == out_pin:
            continue
        try:
            GPIO.setup(in_pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
            usable_inputs.append(in_pin)
        except Exception:
            pass

    GPIO.output(out_pin, GPIO.HIGH)
    time.sleep(0.05)

    for in_pin in usable_inputs:
        if GPIO.input(in_pin):
            p1 = bcm_to_phys[out_pin]
            p2 = bcm_to_phys[in_pin]
            found.append((out_pin, in_pin, p1, p2))

    GPIO.output(out_pin, GPIO.LOW)
    try:
        GPIO.setup(out_pin, GPIO.IN)
    except Exception:
        pass

GPIO.cleanup()

if found:
    print("FOUND CONNECTION(S):")
    seen = set()
    for bo, bi, p1, p2 in found:
        key = tuple(sorted([bo, bi]))
        if key not in seen:
            seen.add(key)
            print(f"  GPIO {bo} (Physical Pin {p1}) <-> GPIO {bi} (Physical Pin {p2})")

    print()
    seen2 = set()
    for bo, bi, p1, p2 in found:
        key = tuple(sorted([bo, bi]))
        if key not in seen2:
            seen2.add(key)
            if sorted([p1, p2]) == [8, 10]:
                print("  -> This IS Pin 8 <-> Pin 10. UART pins are correct!")
                print("     Your UART hardware may have an issue. Run:")
                print("     sudo dtoverlay -l")
                print("     to check active overlays.")
            else:
                print(f"  -> This is Pin {p1} <-> Pin {p2}, NOT Pin 8 <-> Pin 10!")
                print(f"     Move jumper to Pin 8 (4th down, outer row)")
                print(f"     and Pin 10 (5th down, outer row)")
else:
    print("NO CONNECTION FOUND on any pins.")
    print("Your jumper wire is bad or not plugged in. Try a different wire.")
