#!/usr/bin/env python3
"""
A7670E Diagnostic Test Suite
==============================
Interactive test script for verifying A7670E module connectivity,
SIM, signal, network registration, GNSS, and SMS.

Port of: tests/test_a7670e/test_a7670e.ino (9-test diagnostic + interactive AT)
Run with:  sudo python3 test_a7670e.py
"""

import sys
import os
import time

# Allow running from tests/ directory — add parent for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "main"))

from a7670e import A7670E
import config


# ── Colour helpers for terminal output ──────────────────────────────────────
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
RESET = "\033[0m"

PASS = f"{GREEN}PASS{RESET}"
FAIL = f"{RED}FAIL{RESET}"
WARN = f"{YELLOW}WARN{RESET}"


def header(title):
    print(f"\n{CYAN}{'=' * 50}")
    print(f"  {title}")
    print(f"{'=' * 50}{RESET}")


def divider():
    print("-" * 50)


# ── Test functions ──────────────────────────────────────────────────────────

def test_1_connection(modem):
    """Test 1: Basic AT communication."""
    header("TEST 1 — AT Communication")
    resp = modem.send_command("AT", timeout=2.0)
    ok = "OK" in resp
    print(f"  Response: {resp}")
    print(f"  Result:   {PASS if ok else FAIL}")
    return ok


def test_2_module_info(modem):
    """Test 2: Module identification."""
    header("TEST 2 — Module Info")

    cmds = [
        ("Manufacturer", "AT+CGMI"),
        ("Model",        "AT+CGMM"),
        ("Revision",     "AT+CGMR"),
        ("IMEI",         "AT+GSN"),
    ]
    for label, cmd in cmds:
        resp = modem.send_command(cmd, timeout=2.0)
        # Extract useful line (skip echo and OK)
        lines = [l.strip() for l in resp.splitlines()
                 if l.strip() and l.strip() != "OK"]
        info = lines[0] if lines else "N/A"
        print(f"  {label}: {info}")

    return True


def test_3_sim_status(modem):
    """Test 3: SIM card status."""
    header("TEST 3 — SIM Card")
    status = modem.check_sim()
    ok = status == "READY"
    print(f"  SIM Status: {status}")
    print(f"  Result:     {PASS if ok else FAIL}")
    return ok


def test_4_signal(modem):
    """Test 4: Signal quality."""
    header("TEST 4 — Signal Quality")
    rssi = modem.get_signal_quality()

    if rssi == 99:
        quality = "No signal"
        ok = False
    elif rssi >= 20:
        quality = "Excellent"
        ok = True
    elif rssi >= 15:
        quality = "Good"
        ok = True
    elif rssi >= 10:
        quality = "Fair"
        ok = True
    else:
        quality = "Weak"
        ok = True

    # Approximate dBm conversion: -113 + 2*RSSI
    if rssi != 99:
        dbm = -113 + 2 * rssi
        print(f"  RSSI: {rssi}/31 (~{dbm} dBm) — {quality}")
    else:
        print(f"  RSSI: {rssi} — {quality}")

    print(f"  Result: {PASS if ok else FAIL}")
    return ok


def test_5_registration(modem):
    """Test 5: Network registration."""
    header("TEST 5 — Network Registration")
    reg = modem.check_registration()
    ok = reg in ("home", "roaming")
    print(f"  Status: {reg}")
    print(f"  Result: {PASS if ok else FAIL}")
    return ok


def test_6_operator(modem):
    """Test 6: Operator info."""
    header("TEST 6 — Operator")
    resp = modem.send_command("AT+COPS?", timeout=3.0)
    for line in resp.splitlines():
        if "+COPS:" in line:
            print(f"  {line.strip()}")
            return True
    print("  No operator info")
    print(f"  Result: {WARN}")
    return False


def test_7_gnss_enable(modem):
    """Test 7: GNSS power on."""
    header("TEST 7 — GNSS Enable")
    ok = modem.enable_gnss()
    print(f"  Result: {PASS if ok else FAIL}")
    return ok


def test_8_gnss_fix(modem, timeout=20):
    """Test 8: Acquire GPS fix (short timeout for quick test)."""
    header(f"TEST 8 — GPS Fix (timeout: {timeout}s)")
    print("  This test may take a while outdoors...")

    lat, lng, utc = modem.acquire_gps(
        timeout=timeout,
        poll_interval=3,
    )

    if lat is not None:
        link = modem.build_map_link(lat, lng)
        print()
        print(f"  Latitude:  {lat:.6f}")
        print(f"  Longitude: {lng:.6f}")
        print(f"  UTC Time:  {utc}")
        print(f"  Map Link:  {link}")
        print(f"  Result:    {PASS}")
        return True
    else:
        print(f"  Result:    {FAIL} — No fix (try outdoor)")
        return False


def test_9_sms(modem):
    """Test 9: Send test SMS to first contact."""
    header("TEST 9 — SMS Send")

    if not config.CONTACTS:
        print(f"  {FAIL}: No contacts configured in config.py")
        return False

    contact = config.CONTACTS[0]
    print(f"  Sending test SMS to: {contact['name']} ({contact['number']})")
    print("  (Press Ctrl+C to skip)")

    try:
        message = (
            f"[PEL TEST] This is a test message from the "
            f"Panic Button Emergency Locator device. "
            f"Owner: {config.OWNER_NAME}. "
            f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}"
        )
        ok = modem.send_sms(contact["number"], message, retries=2)
        print(f"  Result: {PASS if ok else FAIL}")
        return ok

    except KeyboardInterrupt:
        print(f"\n  {WARN}: Skipped by user")
        return False


# ── Interactive AT terminal ─────────────────────────────────────────────────

def interactive_mode(modem):
    """
    Direct AT command terminal — type commands, see raw responses.
    Port of: interactive serial passthrough in test_a7670e.ino
    """
    header("INTERACTIVE AT TERMINAL")
    print("  Type AT commands directly. Enter 'exit' or 'quit' to leave.")
    print("  Examples: AT+CSQ, AT+CGNSINF, AT+CMGF=1")
    print()

    while True:
        try:
            cmd = input(f"{CYAN}AT> {RESET}").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if cmd.lower() in ("exit", "quit", "q"):
            break
        if not cmd:
            continue

        resp = modem.send_command(cmd, timeout=5.0)
        print(resp)
        print()


# ── Main ────────────────────────────────────────────────────────────────────

def run_all_tests():
    header("A7670E DIAGNOSTIC TEST SUITE")
    print(f"  Port:          {config.SERIAL_PORT}")
    print(f"  Primary baud:  {config.SERIAL_BAUD}")
    print(f"  Fallback baud: {config.SERIAL_FALLBACK_BAUD}")
    divider()

    modem = A7670E(
        port=config.SERIAL_PORT,
        baud=config.SERIAL_BAUD,
        fallback_baud=config.SERIAL_FALLBACK_BAUD,
        timeout=config.SERIAL_TIMEOUT,
    )

    if not modem.is_connected:
        print(f"\n{RED}FATAL: Cannot communicate with A7670E.{RESET}")
        print("Check: wiring, power supply, serial port.")
        modem.close()
        return

    results = {}

    results["1. AT Comm"]     = test_1_connection(modem)
    results["2. Module Info"] = test_2_module_info(modem)
    results["3. SIM Card"]    = test_3_sim_status(modem)
    results["4. Signal"]      = test_4_signal(modem)
    results["5. Registration"] = test_5_registration(modem)
    results["6. Operator"]    = test_6_operator(modem)
    results["7. GNSS Enable"] = test_7_gnss_enable(modem)
    results["8. GPS Fix"]     = test_8_gnss_fix(modem, timeout=20)
    results["9. SMS Send"]    = test_9_sms(modem)

    # ── Summary ─────────────────────────────────────────────────────
    header("TEST SUMMARY")
    passed = 0
    total = len(results)
    for name, ok in results.items():
        status = PASS if ok else FAIL
        print(f"  {name:.<30s} {status}")
        if ok:
            passed += 1
    divider()
    colour = GREEN if passed == total else (YELLOW if passed >= 6 else RED)
    print(f"  {colour}{passed}/{total} tests passed{RESET}")
    print()

    # ── Offer interactive mode ──────────────────────────────────────
    try:
        choice = input("Enter interactive AT terminal? [y/N] ").strip().lower()
        if choice == "y":
            interactive_mode(modem)
    except (EOFError, KeyboardInterrupt):
        pass

    # Cleanup
    modem.disable_gnss()
    modem.close()
    print("Done.")


if __name__ == "__main__":
    run_all_tests()
