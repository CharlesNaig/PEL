#!/usr/bin/env python3
"""
A7670E Diagnostic Test Suite
==============================
Interactive test script for verifying A7670E module connectivity,
SIM, signal, network registration, GNSS, and SMS.

Includes pre-flight checks for UART config, serial port, and PWRKEY.

Port of: tests/test_a7670e/test_a7670e.ino (9-test diagnostic + interactive AT)
Run with:  sudo python3 test_a7670e.py
"""

import sys
import os
import time
import subprocess
import serial

# Allow running from tests/ directory -- add parent for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "main"))

import RPi.GPIO as GPIO
from a7670e import A7670E
import config


# -- Colour helpers for terminal output ---------------------------------------
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"

PASS = f"{GREEN}PASS{RESET}"
FAIL = f"{RED}FAIL{RESET}"
WARN = f"{YELLOW}WARN{RESET}"
INFO = f"{CYAN}INFO{RESET}"


def header(title):
    print(f"\n{CYAN}{'=' * 50}")
    print(f"  {title}")
    print(f"{'=' * 50}{RESET}")


def divider():
    print("-" * 50)


# -- Pre-flight checks -------------------------------------------------------

def preflight_check_uart_config():
    """Check /boot/config.txt for UART enable and BT disable."""
    header("PRE-FLIGHT: UART Configuration")
    issues = []

    # Check /boot/config.txt (try both Pi OS paths)
    config_path = None
    for path in ["/boot/firmware/config.txt", "/boot/config.txt"]:
        if os.path.exists(path):
            config_path = path
            break

    if config_path is None:
        print(f"  {WARN}: Cannot find /boot/config.txt")
        return False

    print(f"  Config file: {config_path}")

    with open(config_path, "r") as f:
        content = f.read()

    # Check for disable-bt
    if "dtoverlay=disable-bt" in content:
        print(f"  dtoverlay=disable-bt ... {PASS}")
    else:
        print(f"  dtoverlay=disable-bt ... {FAIL} (missing!)")
        issues.append("Add 'dtoverlay=disable-bt' to " + config_path)

    # Check for enable_uart
    if "enable_uart=1" in content:
        print(f"  enable_uart=1        ... {PASS}")
    else:
        print(f"  enable_uart=1        ... {FAIL} (missing!)")
        issues.append("Add 'enable_uart=1' to " + config_path)

    # Check /boot/cmdline.txt for serial console
    cmdline_path = config_path.replace("config.txt", "cmdline.txt")
    if os.path.exists(cmdline_path):
        with open(cmdline_path, "r") as f:
            cmdline = f.read()
        if "console=serial0" in cmdline:
            print(f"  cmdline.txt console  ... {FAIL} (serial console active!)")
            issues.append(f"Remove 'console=serial0,115200' from {cmdline_path}")
        else:
            print(f"  cmdline.txt console  ... {PASS} (not using serial)")

    if issues:
        print()
        print(f"  {RED}Action required:{RESET}")
        for issue in issues:
            print(f"    -> {issue}")
        print(f"    -> Reboot after changes: sudo reboot")
        return False

    return True


def preflight_check_serial_port():
    """Check if /dev/serial0 exists and is accessible."""
    header("PRE-FLIGHT: Serial Port")
    port = config.SERIAL_PORT

    if not os.path.exists(port):
        print(f"  {port} ... {FAIL} (does not exist!)")
        print()
        print(f"  {RED}Possible causes:{RESET}")
        print(f"    -> UART not enabled (check /boot/firmware/config.txt)")
        print(f"    -> Bluetooth not disabled on Pi 3/4/5")
        print(f"    -> Need reboot after config changes")
        # Check what serial devices exist
        import glob
        serial_devs = glob.glob("/dev/serial*") + glob.glob("/dev/ttyS*") + glob.glob("/dev/ttyAMA*")
        if serial_devs:
            print(f"\n  Available serial devices:")
            for dev in sorted(serial_devs):
                real = os.path.realpath(dev)
                print(f"    {dev} -> {real}")
        return False

    real_path = os.path.realpath(port)
    print(f"  {port} -> {real_path} ... {PASS}")

    # Warn if pointing to mini UART (ttyS0) instead of PL011 (ttyAMA0)
    if "ttyS0" in real_path:
        print(f"  UART type            ... {WARN} (mini UART / ttyS0)")
        print(f"    Mini UART is unreliable (clock tied to CPU freq).")
        print(f"    Add 'dtoverlay=disable-bt' to /boot/firmware/config.txt")
        print(f"    and reboot so serial0 -> ttyAMA0 (PL011).")
    elif "ttyAMA0" in real_path:
        print(f"  UART type            ... {PASS} (PL011 / ttyAMA0)")

    # Check if we can open it
    try:
        s = serial.Serial(port, 9600, timeout=0.1)
        s.close()
        print(f"  Open/close test      ... {PASS}")
    except serial.SerialException as e:
        print(f"  Open/close test      ... {FAIL}")
        print(f"    Error: {e}")
        if "Permission" in str(e):
            print(f"    -> Run with: sudo python3 {sys.argv[0]}")
        return False

    return True


def preflight_check_wiring():
    """Display wiring reference and ask user to verify."""
    header("PRE-FLIGHT: Wiring Check")
    print(f"  {BOLD}Required A7670E -> Raspberry Pi wiring:{RESET}")
    print()
    print(f"    A7670E     Pi Pin     Pi GPIO    Purpose")
    print(f"    ------     ------     -------    -------")
    print(f"    T (TX)  -> Pin 10     GPIO 15    Module sends to Pi RX")
    print(f"    R (RX)  -> Pin 8      GPIO 14    Pi sends to Module RX")
    print(f"    G (GND) -> Pin 6      GND        Common ground")
    print(f"    V (VCC) -> {YELLOW}Ext 5V 2A{RESET}  ---        Dedicated power supply")
    print(f"    K (KEY) -> Pin 7      GPIO 4     Power on/off pulse")
    print()
    print(f"  {YELLOW}IMPORTANT:{RESET}")
    print(f"    - T and R must CROSS: module TX -> Pi RX, module RX -> Pi TX")
    print(f"    - K (PWRKEY) MUST be connected to power on the module")
    print(f"    - V (VCC) ideally from dedicated 5V 2A supply, not Pi 5V pin")
    print()
    return True


def preflight_pwrkey_pulse():
    """
    Pulse the PWRKEY pin to ensure the A7670E module is powered on.
    SIMCOM modules require a ~1.5s LOW pulse on PWRKEY to toggle power.
    """
    header("PRE-FLIGHT: PWRKEY Power-On Pulse")

    pin = config.PIN_PWRKEY
    print(f"  PWRKEY GPIO: {pin} (BCM)")

    try:
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        GPIO.setup(pin, GPIO.OUT)

        # Drive HIGH first (idle state), then pulse LOW
        GPIO.output(pin, GPIO.HIGH)
        time.sleep(0.1)

        print(f"  Pulsing PWRKEY LOW for 1.5 seconds...")
        GPIO.output(pin, GPIO.LOW)
        time.sleep(1.5)
        GPIO.output(pin, GPIO.HIGH)

        print(f"  Waiting 3 seconds for module boot...")
        time.sleep(3.0)

        print(f"  PWRKEY pulse complete ... {PASS}")
        return True

    except Exception as e:
        print(f"  PWRKEY pulse ... {FAIL}")
        print(f"    Error: {e}")
        return False


def raw_serial_sniff(port, bauds=None, duration=2.0):
    """
    Try to read any raw bytes at various baud rates.
    Helps diagnose if the module is alive but at an unexpected baud.
    """
    header("PRE-FLIGHT: Raw Serial Sniff")
    if bauds is None:
        bauds = [115200, 9600, 57600, 38400, 19200, 4800]

    found_baud = None

    for baud in bauds:
        try:
            s = serial.Serial(port, baud, timeout=0.5)
            s.reset_input_buffer()

            # Send AT and see if we get anything back
            s.write(b"AT\r\n")
            time.sleep(0.5)

            data = s.read(s.in_waiting or 256)
            s.close()

            if data:
                text = data.decode("ascii", errors="replace")
                readable = text.strip()
                if "OK" in text:
                    print(f"  {baud:>6} baud: {GREEN}GOT 'OK' response!{RESET}")
                    found_baud = baud
                    break
                elif readable:
                    # Got data but not OK -- might be garbled (wrong baud)
                    preview = readable[:60].replace("\n", "\\n").replace("\r", "\\r")
                    print(f"  {baud:>6} baud: got data -> {YELLOW}{preview}{RESET}")
                else:
                    print(f"  {baud:>6} baud: got {len(data)} bytes (non-printable/empty)")
            else:
                print(f"  {baud:>6} baud: {RED}no response{RESET}")

        except serial.SerialException as e:
            print(f"  {baud:>6} baud: error -> {e}")

    if found_baud:
        print(f"\n  {GREEN}Module responding at {found_baud} baud!{RESET}")
        return found_baud
    else:
        print(f"\n  {RED}No response at any baud rate.{RESET}")
        print(f"  Possible causes:")
        print(f"    1. TX/RX wires swapped (most common)")
        print(f"    2. Module not powered on (PWRKEY not pulsed)")
        print(f"    3. Module not powered (check VCC and GND)")
        print(f"    4. UART not enabled on Pi (/boot/config.txt)")
        return None


# -- Test functions -----------------------------------------------------------

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
    print(f"  PWRKEY GPIO:   {config.PIN_PWRKEY}")
    divider()

    # ---- PRE-FLIGHT CHECKS ----
    print(f"\n{BOLD}Running pre-flight checks...{RESET}")

    uart_ok = preflight_check_uart_config()
    port_ok = preflight_check_serial_port()
    preflight_check_wiring()

    if not port_ok:
        print(f"\n{RED}FATAL: Serial port not available. Fix the above issues first.{RESET}")
        return

    if not uart_ok:
        print(f"\n{YELLOW}WARNING: UART config issues detected. Continuing anyway...{RESET}")

    # ---- PWRKEY PULSE ----
    preflight_pwrkey_pulse()

    # ---- RAW SNIFF ----
    detected_baud = raw_serial_sniff(config.SERIAL_PORT)

    if detected_baud is None:
        print(f"\n{RED}FATAL: Cannot communicate with A7670E at any baud rate.{RESET}")
        print(f"\n{BOLD}Troubleshooting checklist:{RESET}")
        print(f"  [ ] TX/RX wires: module T -> Pi pin 10, module R -> Pi pin 8")
        print(f"  [ ] K (PWRKEY) connected to GPIO {config.PIN_PWRKEY} (Pi pin 7)")
        print(f"  [ ] GND connected between module and Pi")
        print(f"  [ ] VCC: module has 5V power (status LED on module?)")
        print(f"  [ ] /boot/config.txt has dtoverlay=disable-bt + enable_uart=1")
        print(f"  [ ] Rebooted after config changes")
        print()

        try:
            choice = input("Try again? [y/N] ").strip().lower()
            if choice == "y":
                print("Retrying PWRKEY pulse + sniff...")
                preflight_pwrkey_pulse()
                detected_baud = raw_serial_sniff(config.SERIAL_PORT)
                if detected_baud is None:
                    print(f"\n{RED}Still no response. Check wiring and power.{RESET}")
                    return
        except (EOFError, KeyboardInterrupt):
            print()
            return

    # ---- USE DETECTED BAUD ----
    use_baud = detected_baud if detected_baud else config.SERIAL_BAUD

    # ---- CONNECT ----
    header("CONNECTING TO A7670E")
    modem = A7670E(
        port=config.SERIAL_PORT,
        baud=use_baud,
        fallback_baud=config.SERIAL_FALLBACK_BAUD,
        timeout=config.SERIAL_TIMEOUT,
    )

    if not modem.is_connected:
        print(f"\n{RED}FATAL: Cannot communicate with A7670E.{RESET}")
        print("Check: wiring, power supply, serial port.")
        modem.close()
        return

    results = {}

    results["1. AT Comm"]      = test_1_connection(modem)
    results["2. Module Info"]  = test_2_module_info(modem)
    results["3. SIM Card"]     = test_3_sim_status(modem)
    results["4. Signal"]       = test_4_signal(modem)
    results["5. Registration"] = test_5_registration(modem)
    results["6. Operator"]     = test_6_operator(modem)
    results["7. GNSS Enable"]  = test_7_gnss_enable(modem)
    results["8. GPS Fix"]      = test_8_gnss_fix(modem, timeout=20)
    results["9. SMS Send"]     = test_9_sms(modem)

    # ---- Summary ----
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

    # ---- Offer interactive mode ----
    try:
        choice = input("Enter interactive AT terminal? [y/N] ").strip().lower()
        if choice == "y":
            interactive_mode(modem)
    except (EOFError, KeyboardInterrupt):
        pass

    # Cleanup
    modem.disable_gnss()
    modem.close()
    GPIO.cleanup()
    print("Done.")


if __name__ == "__main__":
    run_all_tests()
