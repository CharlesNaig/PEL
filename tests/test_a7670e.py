#!/usr/bin/env python3
"""
A7670E Diagnostic Test Suite
==============================
Interactive test script for verifying A7670E module connectivity,
SIM, signal, network registration, GNSS, and SMS.

Supports two connection modes:
  USB  -- A7670E micro-USB cable to Pi USB port (recommended)
  GPIO -- A7670E TX/RX wired to Pi GPIO 14/15

Port of: tests/test_a7670e/test_a7670e.ino (9-test diagnostic + interactive AT)
Reference: tests/test_a7670e_windows.py (working USB test -- SMS verified)

Run with:
  USB mode:   python3 test_a7670e.py
  USB (pick): python3 test_a7670e.py --port /dev/ttyUSB2
  GPIO mode:  sudo python3 test_a7670e.py --mode gpio
  Interactive: python3 test_a7670e.py --interactive
"""

import sys
import os
import time
import serial
import argparse

# Allow running from tests/ directory -- add parent for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "main"))

from a7670e import A7670E, find_usb_at_port
import config

# Conditional GPIO import -- only needed for GPIO mode
GPIO = None


# -- Colour helpers for terminal output ----------------------------------------
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

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


def coloured(text, colour):
    return f"{colour}{text}{RESET}"


# =============================================================================
#  PRE-FLIGHT CHECKS -- GPIO mode only
# =============================================================================

def preflight_check_uart_config():
    """Check /boot/config.txt for UART enable and BT disable."""
    header("PRE-FLIGHT: UART Configuration")
    issues = []

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

    if "dtoverlay=disable-bt" in content:
        print(f"  dtoverlay=disable-bt ... {PASS}")
    else:
        print(f"  dtoverlay=disable-bt ... {FAIL} (missing!)")
        issues.append("Add 'dtoverlay=disable-bt' to " + config_path)

    if "enable_uart=1" in content:
        print(f"  enable_uart=1        ... {PASS}")
    else:
        print(f"  enable_uart=1        ... {FAIL} (missing!)")
        issues.append("Add 'enable_uart=1' to " + config_path)

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

    if "ttyS0" in real_path:
        print(f"  UART type            ... {WARN} (mini UART / ttyS0)")
        print(f"    Mini UART is unreliable. Add 'dtoverlay=disable-bt' and reboot.")
    elif "ttyAMA0" in real_path:
        print(f"  UART type            ... {PASS} (PL011 / ttyAMA0)")

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
    """Display GPIO wiring reference."""
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
    return True


def preflight_pwrkey_pulse():
    """Pulse PWRKEY to power on the A7670E module."""
    header("PRE-FLIGHT: PWRKEY Power-On Pulse")
    pin = config.PIN_PWRKEY
    print(f"  PWRKEY GPIO: {pin} (BCM)")

    try:
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        GPIO.setup(pin, GPIO.OUT)
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
    """Try reading raw bytes at various baud rates to find the module."""
    header("PRE-FLIGHT: Raw Serial Sniff")
    if bauds is None:
        bauds = [115200, 9600, 57600, 38400, 19200, 4800]

    found_baud = None
    for baud in bauds:
        try:
            s = serial.Serial(port, baud, timeout=0.5)
            s.reset_input_buffer()
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
                    preview = readable[:60].replace("\n", "\\n").replace("\r", "\\r")
                    print(f"  {baud:>6} baud: got data -> {YELLOW}{preview}{RESET}")
                else:
                    print(f"  {baud:>6} baud: got {len(data)} bytes (non-printable)")
            else:
                print(f"  {baud:>6} baud: {RED}no response{RESET}")
        except serial.SerialException as e:
            print(f"  {baud:>6} baud: error -> {e}")

    if found_baud:
        print(f"\n  {GREEN}Module responding at {found_baud} baud!{RESET}")
    else:
        print(f"\n  {RED}No response at any baud rate.{RESET}")
        print(f"  Check: TX/RX wiring, PWRKEY, VCC, /boot/config.txt")
    return found_baud


# =============================================================================
#  PRE-FLIGHT CHECK -- USB mode
# =============================================================================

def preflight_usb_detect(override_port=None):
    """
    Detect SIMCOM USB ports and select the AT-command port.
    Returns (port_path, baud) or (None, None) on failure.
    """
    header("PRE-FLIGHT: USB Port Detection")

    if override_port:
        print(f"  Using user-specified port: {override_port}")
        try:
            s = serial.Serial(override_port, config.SERIAL_BAUD, timeout=1)
            s.write(b"AT\r\n")
            time.sleep(0.5)
            data = s.read(s.in_waiting or 256)
            s.close()
            if b"OK" in data:
                print(f"  AT response ... {PASS}")
                return override_port, config.SERIAL_BAUD
            else:
                print(f"  AT response ... {FAIL} (no OK)")
                return override_port, config.SERIAL_BAUD  # try anyway
        except serial.SerialException as e:
            print(f"  {FAIL}: {e}")
            return None, None

    # Auto-detect using find_usb_at_port()
    print(f"  Scanning for SIMCOM USB devices (VID 0x1E0E)...")

    try:
        import serial.tools.list_ports
        ports = list(serial.tools.list_ports.comports())
        simcom = [p for p in ports if p.vid == 0x1E0E]

        if not simcom:
            print(f"  {FAIL}: No SIMCOM USB devices found.")
            print(f"  Check: USB cable connected, module powered on")
            if ports:
                print(f"\n  Available ports:")
                for p in ports:
                    vid = f"0x{p.vid:04X}" if p.vid else "----"
                    print(f"    {p.device}  VID={vid}  {p.description}")
            return None, None

        print(f"  Found {len(simcom)} SIMCOM port(s):")
        for p in simcom:
            print(f"    {p.device}  {p.description}")

    except ImportError:
        print(f"  {WARN}: serial.tools.list_ports not available")

    # Use find_usb_at_port() to probe for AT-capable port
    at_port = find_usb_at_port()
    if at_port:
        print(f"\n  AT command port: {GREEN}{at_port}{RESET}")
        print(f"  Auto-detect ... {PASS}")
        return at_port, config.SERIAL_BAUD
    else:
        print(f"\n  {FAIL}: Could not find AT-capable SIMCOM USB port.")
        print(f"  Try: python3 test_a7670e.py --port /dev/ttyUSB2")
        return None, None


# =============================================================================
#  DIAGNOSTIC TESTS (mode-independent)
# =============================================================================

def test_1_connection(modem):
    """Test 1: Basic AT communication."""
    header("TEST 1 -- AT Communication")
    resp = modem.send_command("AT", timeout=2.0)
    ok = "OK" in resp
    print(f"  Response: {resp}")
    print(f"  Result:   {PASS if ok else FAIL}")
    return ok


def test_2_module_info(modem):
    """Test 2: Module identification."""
    header("TEST 2 -- Module Info")
    cmds = [
        ("Manufacturer", "AT+CGMI"),
        ("Model",        "AT+CGMM"),
        ("Revision",     "AT+CGMR"),
        ("IMEI",         "AT+GSN"),
    ]
    for label, cmd in cmds:
        resp = modem.send_command(cmd, timeout=2.0)
        lines = [l.strip() for l in resp.splitlines()
                 if l.strip() and l.strip() != "OK"]
        info = lines[0] if lines else "N/A"
        print(f"  {label}: {info}")
    return True


def test_3_sim_status(modem):
    """Test 3: SIM card status."""
    header("TEST 3 -- SIM Card")
    status = modem.check_sim()
    ok = status == "READY"
    print(f"  SIM Status: {status}")
    print(f"  Result:     {PASS if ok else FAIL}")
    return ok


def test_4_signal(modem):
    """Test 4: Signal quality."""
    header("TEST 4 -- Signal Quality")
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

    if rssi != 99:
        dbm = -113 + 2 * rssi
        print(f"  RSSI: {rssi}/31 (~{dbm} dBm) -- {quality}")
    else:
        print(f"  RSSI: {rssi} -- {quality}")
    print(f"  Result: {PASS if ok else FAIL}")
    return ok


def test_5_registration(modem):
    """Test 5: Network registration."""
    header("TEST 5 -- Network Registration")
    reg = modem.check_registration()
    ok = reg in ("home", "roaming")
    print(f"  Status: {reg}")
    print(f"  Result: {PASS if ok else FAIL}")
    return ok


def test_6_operator(modem):
    """Test 6: Operator info."""
    header("TEST 6 -- Operator")
    resp = modem.send_command("AT+COPS?", timeout=3.0)
    for line in resp.splitlines():
        if "+COPS:" in line:
            print(f"  {line.strip()}")
            return True
    print("  No operator info")
    print(f"  Result: {WARN}")
    return False


def test_7_sms_config(modem):
    """Test 7: SMS configuration."""
    header("TEST 7 -- SMS Config")
    resp1 = modem.send_command("AT+CMGF=1", timeout=2.0)
    ok1 = "OK" in resp1
    print(f"  Text mode (CMGF=1): {PASS if ok1 else FAIL}")

    resp2 = modem.send_command('AT+CSCS="GSM"', timeout=2.0)
    ok2 = "OK" in resp2
    print(f"  Charset GSM:        {PASS if ok2 else FAIL}")
    return ok1 and ok2


def test_8_gnss(modem):
    """Test 8: GNSS enable + quick fix attempt."""
    header("TEST 8 -- GNSS")
    ok = modem.enable_gnss()
    print(f"  GNSS power on: {PASS if ok else FAIL}")
    if not ok:
        return False

    print(f"  Attempting fix (20s timeout)...")
    lat, lng, utc = modem.acquire_gps(timeout=20, poll_interval=3)
    if lat is not None:
        link = modem.build_map_link(lat, lng)
        print(f"  Lat: {lat:.6f}  Lng: {lng:.6f}  UTC: {utc}")
        print(f"  Map: {link}")
        print(f"  GPS fix: {PASS}")
    else:
        print(f"  GPS fix: {WARN} (no fix -- try outdoors)")
    return True


def test_9_sms_send(modem):
    """Test 9: Send test SMS to first contact."""
    header("TEST 9 -- SMS Send")

    if not config.CONTACTS:
        print(f"  {FAIL}: No contacts in config.py")
        return False

    contact = config.CONTACTS[0]
    print(f"  To: {contact['name']} ({contact['number']})")
    print(f"  (Ctrl+C to skip)")

    try:
        message = (
            f"[PEL TEST] Diagnostic SMS from Panic Button. "
            f"Owner: {config.OWNER_NAME}. "
            f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}"
        )
        ok = modem.send_sms(contact["number"], message, retries=2)
        print(f"  Result: {PASS if ok else FAIL}")
        return ok
    except KeyboardInterrupt:
        print(f"\n  {WARN}: Skipped by user")
        return False


# =============================================================================
#  INTERACTIVE FEATURES (ported from test_a7670e_windows.py)
# =============================================================================

def send_at_raw(modem, cmd, timeout=5.0):
    """Send raw AT command via modem.ser, return decoded response."""
    ser = modem.ser
    ser.reset_input_buffer()
    ser.write((cmd + "\r\n").encode())
    time.sleep(0.1)

    deadline = time.time() + timeout
    buf = b""
    while time.time() < deadline:
        n = ser.in_waiting
        if n:
            buf += ser.read(n)
            if b"OK" in buf or b"ERROR" in buf or b">" in buf:
                break
        time.sleep(0.05)

    # Drain any remaining bytes
    time.sleep(0.1)
    n = ser.in_waiting
    if n:
        buf += ser.read(n)
    return buf.decode("ascii", errors="replace")


def send_sms_interactive(modem):
    """
    Send SMS interactively using raw serial -- matches working Windows script.
    Uses prompt polling (wait for '>') then Ctrl-Z to send.
    """
    header("SEND SMS")

    if config.CONTACTS:
        print(f"  Configured contacts:")
        for i, c in enumerate(config.CONTACTS):
            print(f"    {i+1}. {c['name']} ({c['number']})")
        print()

    number = input(f"  Phone number (or contact #): ").strip()

    # Allow selecting by contact index
    if number.isdigit() and 1 <= int(number) <= len(config.CONTACTS):
        contact = config.CONTACTS[int(number) - 1]
        number = contact["number"]
        print(f"  -> {contact['name']} ({number})")

    if not number.startswith("+"):
        print(f"  {WARN}: Number should start with + (e.g. +639XXXXXXXXX)")

    message = input(f"  Message: ").strip()
    if not message:
        message = f"[PEL TEST] SMS from diagnostic suite. Time: {time.strftime('%H:%M:%S')}"
        print(f"  Using default: {message}")

    print(f"\n  Sending to {number}...")

    ser = modem.ser
    ser.reset_input_buffer()

    # Set text mode + GSM charset + text parameters (all required for CMGS)
    ser.write(b"AT+CMGF=1\r\n")
    time.sleep(1)
    ser.read(ser.in_waiting or 256)

    ser.write(b'AT+CSCS="GSM"\r\n')
    time.sleep(0.5)
    ser.read(ser.in_waiting or 256)

    ser.write(b"AT+CSMP=17,167,0,0\r\n")
    time.sleep(0.5)
    ser.read(ser.in_waiting or 256)

    # Send CMGS command (use \r only, not \r\n — matches working Windows script)
    cmd = f'AT+CMGS="{number}"\r'
    ser.write(cmd.encode())

    # Wait for > prompt (up to 5 seconds)
    print(f"  Waiting for '>' prompt...")
    prompt_ok = False
    deadline = time.time() + 5.0
    buf = b""
    while time.time() < deadline:
        n = ser.in_waiting
        if n:
            buf += ser.read(n)
        if b">" in buf:
            prompt_ok = True
            break
        if b"ERROR" in buf:
            break
        time.sleep(0.1)

    if not prompt_ok:
        print(f"  {FAIL}: No '>' prompt (got: {buf.decode('ascii', errors='replace').strip()})")
        ser.write(b"\x1b")  # ESC to cancel
        return False

    print(f"  Got prompt, sending message + Ctrl-Z...")
    ser.write(message.encode() + b"\x1a")  # Ctrl-Z

    # Wait for +CMGS or OK (up to 30 seconds for network delivery)
    print(f"  Waiting for network response (up to 30s)...")
    deadline = time.time() + 30.0
    buf = b""
    while time.time() < deadline:
        n = ser.in_waiting
        if n:
            buf += ser.read(n)
        if b"+CMGS" in buf or b"OK" in buf:
            break
        if b"ERROR" in buf:
            break
        time.sleep(0.2)

    response = buf.decode("ascii", errors="replace")
    print(f"  Response: {response.strip()}")

    if "+CMGS" in response or "OK" in response:
        print(f"  {GREEN}SMS sent successfully!{RESET}")
        return True
    else:
        print(f"  {RED}SMS may have failed.{RESET}")
        return False


def check_balance(modem):
    """Check prepaid balance via USSD *143#."""
    header("CHECK BALANCE")
    print(f"  Sending USSD *143#...")

    ser = modem.ser
    ser.reset_input_buffer()
    ser.write(b'AT+CUSD=1,"*143#"\r\n')

    # USSD responses are async -- wait up to 15 seconds
    print(f"  Waiting for USSD response (up to 15s)...")
    deadline = time.time() + 15.0
    buf = b""
    while time.time() < deadline:
        n = ser.in_waiting
        if n:
            buf += ser.read(n)
        if b"+CUSD" in buf:
            break
        time.sleep(0.2)

    # Drain
    time.sleep(0.5)
    n = ser.in_waiting
    if n:
        buf += ser.read(n)

    response = buf.decode("ascii", errors="replace")
    print(f"  Response:\n{response.strip()}")

    if "+CUSD" not in response:
        print(f"  {WARN}: No USSD response received")


def read_pending(modem, duration=5.0):
    """Read any pending/async data from the module."""
    header(f"READING PENDING DATA ({duration}s)")
    ser = modem.ser
    deadline = time.time() + duration
    buf = b""
    while time.time() < deadline:
        n = ser.in_waiting
        if n:
            buf += ser.read(n)
        time.sleep(0.1)

    if buf:
        print(buf.decode("ascii", errors="replace"))
    else:
        print(f"  (no pending data)")


def interactive_mode(modem):
    """
    Enhanced interactive AT terminal with SMS, balance, and helper commands.
    Ported from test_a7670e_windows.py.
    """
    header("INTERACTIVE AT TERMINAL")
    print(f"  Commands:")
    print(f"    sms      -- Send SMS interactively")
    print(f"    balance  -- Check prepaid balance (USSD *143#)")
    print(f"    wait     -- Read pending async data (5s)")
    print(f"    help     -- Show this help")
    print(f"    exit     -- Quit interactive mode")
    print(f"  Or type any AT command directly (e.g. AT+CSQ)")
    print()

    while True:
        try:
            cmd = input(f"{CYAN}AT> {RESET}").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not cmd:
            continue

        low = cmd.lower()
        if low in ("exit", "quit", "q"):
            break
        elif low == "sms":
            send_sms_interactive(modem)
        elif low == "balance":
            check_balance(modem)
        elif low == "wait":
            read_pending(modem)
        elif low == "help":
            print(f"  sms / balance / wait / help / exit")
            print(f"  Or type any AT command")
        else:
            # Raw AT command
            resp = send_at_raw(modem, cmd, timeout=5.0)
            print(resp)
        print()


# =============================================================================
#  MAIN -- run_all_tests with USB / GPIO branching
# =============================================================================

def run_all_tests(mode="usb", port_override=None, go_interactive=False):
    """
    Run the full diagnostic suite.

    Parameters
    ----------
    mode : str
        "usb" or "gpio"
    port_override : str or None
        Force a specific serial port path
    go_interactive : bool
        Jump straight to interactive mode after connection
    """
    global GPIO

    header("A7670E DIAGNOSTIC TEST SUITE")
    print(f"  Mode:          {BOLD}{mode.upper()}{RESET}")
    print(f"  Config baud:   {config.SERIAL_BAUD}")
    if port_override:
        print(f"  Port override: {port_override}")
    divider()

    port = port_override
    use_baud = config.SERIAL_BAUD

    if mode == "usb":
        # ---- USB pre-flight ----
        at_port, at_baud = preflight_usb_detect(port_override)
        if at_port is None:
            print(f"\n{RED}FATAL: No SIMCOM USB device found. Check cable and power.{RESET}")
            return
        port = at_port
        use_baud = at_baud

    elif mode == "gpio":
        # ---- GPIO pre-flight ----
        try:
            import RPi.GPIO as _GPIO
            GPIO = _GPIO
        except ImportError:
            print(f"\n{RED}FATAL: RPi.GPIO not available. Are you on a Raspberry Pi?{RESET}")
            return

        print(f"\n{BOLD}Running GPIO pre-flight checks...{RESET}")
        uart_ok = preflight_check_uart_config()
        port_ok = preflight_check_serial_port()
        preflight_check_wiring()

        if not port_ok:
            print(f"\n{RED}FATAL: Serial port not available. Fix above issues.{RESET}")
            return
        if not uart_ok:
            print(f"\n{YELLOW}WARNING: UART config issues. Continuing...{RESET}")

        # PWRKEY pulse
        preflight_pwrkey_pulse()

        # Baud sniff
        port = port or config.SERIAL_PORT
        detected_baud = raw_serial_sniff(port)
        if detected_baud is None:
            print(f"\n{RED}FATAL: No response on {port} at any baud rate.{RESET}")
            try:
                choice = input("Retry with PWRKEY pulse? [y/N] ").strip().lower()
                if choice == "y":
                    preflight_pwrkey_pulse()
                    detected_baud = raw_serial_sniff(port)
                    if detected_baud is None:
                        print(f"\n{RED}Still no response. Check wiring.{RESET}")
                        return
            except (EOFError, KeyboardInterrupt):
                return
        if detected_baud:
            use_baud = detected_baud
    else:
        print(f"{RED}Unknown mode: {mode}{RESET}")
        return

    # ---- CONNECT ----
    header("CONNECTING TO A7670E")
    print(f"  Port: {port}")
    print(f"  Baud: {use_baud}")

    # NOTE: Do NOT pass pwrkey_pin here. In GPIO mode the preflight already
    # pulsed PWRKEY once to power on the module.  A7670E PWRKEY is a *toggle*
    # — a second pulse from the constructor would turn it right back OFF.
    # In USB mode PWRKEY is not used at all.
    modem = A7670E(
        port=port,
        baud=use_baud,
        fallback_baud=config.SERIAL_FALLBACK_BAUD,
        timeout=config.SERIAL_TIMEOUT,
        pwrkey_pin=None,
    )

    if not modem.is_connected:
        print(f"\n{RED}FATAL: Cannot communicate with A7670E.{RESET}")
        modem.close()
        return

    print(f"  Connection ... {PASS}")

    # ---- Interactive-only mode ----
    if go_interactive:
        interactive_mode(modem)
        modem.close()
        if GPIO:
            GPIO.cleanup()
        return

    # ---- RUN TESTS ----
    results = {}
    results["1. AT Comm"]       = test_1_connection(modem)
    results["2. Module Info"]   = test_2_module_info(modem)
    results["3. SIM Card"]      = test_3_sim_status(modem)
    results["4. Signal"]        = test_4_signal(modem)
    results["5. Registration"]  = test_5_registration(modem)
    results["6. Operator"]      = test_6_operator(modem)
    results["7. SMS Config"]    = test_7_sms_config(modem)
    results["8. GNSS"]          = test_8_gnss(modem)
    results["9. SMS Send"]      = test_9_sms_send(modem)

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
        choice = input("Enter interactive mode? [y/N] ").strip().lower()
        if choice == "y":
            interactive_mode(modem)
    except (EOFError, KeyboardInterrupt):
        pass

    # ---- Cleanup ----
    modem.disable_gnss()
    modem.close()
    if GPIO:
        GPIO.cleanup()
    print("Done.")


# =============================================================================
#  Entry point with argparse
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="A7670E Diagnostic Test Suite",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  python3 test_a7670e.py                       # USB auto-detect
  python3 test_a7670e.py --port /dev/ttyUSB2   # USB specific port
  python3 test_a7670e.py --mode gpio            # GPIO UART mode
  python3 test_a7670e.py --interactive          # Skip tests, go to AT terminal
"""
    )
    parser.add_argument(
        "--mode", choices=["usb", "gpio"], default="usb",
        help="Connection mode (default: usb)"
    )
    parser.add_argument(
        "--port", default=None,
        help="Serial port override (e.g. /dev/ttyUSB2, COM20)"
    )
    parser.add_argument(
        "--interactive", "-i", action="store_true",
        help="Jump straight to interactive AT terminal"
    )
    parser.add_argument(
        "--baud", type=int, default=None,
        help="Override baud rate"
    )

    args = parser.parse_args()

    # Override config baud if specified
    if args.baud:
        config.SERIAL_BAUD = args.baud

    run_all_tests(
        mode=args.mode,
        port_override=args.port,
        go_interactive=args.interactive,
    )


if __name__ == "__main__":
    main()
