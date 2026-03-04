#!/usr/bin/env python3
"""
A7670E Windows USB Test Script
===============================
Connect the BK-A7670 module to your PC via micro-USB cable.
This script auto-detects the COM port and runs AT command tests.

Requirements:
    pip install pyserial

Usage:
    python tests/test_a7670e_windows.py
    python tests/test_a7670e_windows.py --port COM5
    python tests/test_a7670e_windows.py --interactive
"""

import serial
import serial.tools.list_ports
import sys
import time
import argparse

# ── Colours for Windows terminal ──────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

BAUD_RATE = 115200
TIMEOUT   = 2


def coloured(text, colour):
    return f"{colour}{text}{RESET}"


def find_com_ports():
    """List all available COM ports with descriptions."""
    ports = serial.tools.list_ports.comports()
    return sorted(ports, key=lambda p: p.device)


def pick_port(preferred=None):
    """Find the right COM port for the A7670E."""
    ports = find_com_ports()

    if not ports:
        print(coloured("  No COM ports found!", RED))
        print("  Make sure:")
        print("    1. The micro-USB cable is plugged into the A7670E board")
        print("    2. The other end is plugged into your PC")
        print("    3. The USB driver is installed (check Device Manager)")
        print()
        print("  Driver info:")
        print("    - If using CH340 chip: https://sparks.gogo.co.nz/ch340.html")
        print("    - If using CP210x chip: https://www.silabs.com/developers/usb-to-uart-bridge-vcp-drivers")
        return None

    if preferred:
        for p in ports:
            if p.device.upper() == preferred.upper():
                return p.device
        print(coloured(f"  Port {preferred} not found!", RED))

    # Show all ports
    print(f"  Found {len(ports)} COM port(s):")
    print()
    a7670_candidates = []
    for i, p in enumerate(ports, 1):
        desc = p.description or "Unknown"
        hwid = p.hwid or ""
        marker = ""
        # SIMCOM modules typically show as "USB Serial Device" or contain
        # vendor IDs like 1E0E (SIMCOM)
        if "1E0E" in hwid.upper() or "SIMCOM" in desc.upper():
            marker = coloured(" ← A7670E!", GREEN)
            a7670_candidates.append(p.device)
        print(f"    [{i}] {p.device:8s}  {desc}  {marker}")
        if hwid:
            print(f"        HWID: {hwid}")
    print()

    if a7670_candidates:
        # SIMCOM USB usually creates 3 ports: Diag, NMEA, AT
        # The AT command port is typically the last one (highest number)
        best = a7670_candidates[-1]
        print(coloured(f"  Auto-selected: {best} (SIMCOM device)", GREEN))
        return best

    # No auto-detect, ask user
    print("  Could not auto-detect A7670E port.")
    print("  Tip: Unplug the USB, note which ports disappear, replug and pick the new one.")
    print()
    while True:
        choice = input("  Enter port number [1-{}] or COM name (e.g. COM5): ".format(len(ports)))
        choice = choice.strip()
        if not choice:
            continue
        if choice.upper().startswith("COM"):
            return choice.upper()
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(ports):
                return ports[idx].device
        except ValueError:
            pass
        print(coloured("  Invalid choice, try again.", RED))


def send_at(ser, cmd, wait=2, show=True):
    """Send an AT command and return the response."""
    # Drain any pending data
    ser.reset_input_buffer()

    full_cmd = cmd + "\r\n"
    ser.write(full_cmd.encode())
    ser.flush()

    time.sleep(wait)

    response = ""
    while ser.in_waiting:
        response += ser.read(ser.in_waiting).decode(errors="replace")
        time.sleep(0.1)

    if show:
        # Print command and response nicely
        print(f"    → {coloured(cmd, CYAN)}")
        for line in response.strip().split("\n"):
            line = line.strip()
            if line:
                if "OK" == line:
                    print(f"    ← {coloured(line, GREEN)}")
                elif "ERROR" in line:
                    print(f"    ← {coloured(line, RED)}")
                else:
                    print(f"    ← {line}")
        print()

    return response


def test_basic(ser):
    """Test 1: Basic AT communication."""
    print(coloured("── Test 1: Basic AT Communication ──", BOLD))
    resp = send_at(ser, "AT")
    if "OK" in resp:
        print(coloured("  ✓ Module responds to AT commands!", GREEN))
        return True
    else:
        print(coloured("  ✗ No response to AT. Check port/cable.", RED))
        return False


def test_module_info(ser):
    """Test 2: Module identification."""
    print(coloured("── Test 2: Module Information ──", BOLD))
    send_at(ser, "ATI")                      # Module ID
    send_at(ser, "AT+CGMM")                  # Model
    send_at(ser, "AT+CGMR")                  # Firmware version
    send_at(ser, "AT+GSN")                   # IMEI
    return True


def test_sim(ser):
    """Test 3: SIM card status."""
    print(coloured("── Test 3: SIM Card ──", BOLD))
    resp = send_at(ser, "AT+CPIN?")
    if "READY" in resp:
        print(coloured("  ✓ SIM card is ready!", GREEN))
        send_at(ser, "AT+CCID")              # SIM ICCID
        return True
    elif "SIM PIN" in resp:
        print(coloured("  ! SIM requires PIN code.", YELLOW))
        return False
    elif "SIM not inserted" in resp or "ERROR" in resp:
        print(coloured("  ✗ No SIM card detected.", RED))
        return False
    return False


def test_network(ser):
    """Test 4: Network registration."""
    print(coloured("── Test 4: Network Registration ──", BOLD))
    resp = send_at(ser, "AT+CREG?")
    # +CREG: 0,1 = registered home, 0,5 = registered roaming
    if ",1" in resp or ",5" in resp:
        print(coloured("  ✓ Registered on network!", GREEN))
    else:
        print(coloured("  ! Not registered yet (may take a moment).", YELLOW))

    send_at(ser, "AT+COPS?")                 # Operator name
    send_at(ser, "AT+CSQ")                   # Signal quality
    resp_csq = send_at(ser, "AT+CSQ", show=False)
    # Parse signal: +CSQ: 18,0  → 18 = good
    try:
        val = int(resp_csq.split(":")[1].split(",")[0].strip())
        if val == 99:
            print(coloured("  ! Signal: unknown (99)", YELLOW))
        elif val < 10:
            print(coloured(f"  ! Signal: weak ({val}/31)", YELLOW))
        elif val < 20:
            print(coloured(f"  ✓ Signal: moderate ({val}/31)", GREEN))
        else:
            print(coloured(f"  ✓ Signal: strong ({val}/31)", GREEN))
    except (IndexError, ValueError):
        pass
    return True


def test_sms(ser):
    """Test 5: SMS configuration (does NOT send a message)."""
    print(coloured("── Test 5: SMS Configuration ──", BOLD))
    send_at(ser, "AT+CMGF=1")                # Text mode
    resp = send_at(ser, "AT+CSCA?")           # SMS center number
    send_at(ser, "AT+CPMS?")                  # Message storage
    if "OK" in resp:
        print(coloured("  ✓ SMS subsystem ready.", GREEN))
    return True


def test_gnss(ser):
    """Test 6: GNSS (GPS) functionality."""
    print(coloured("── Test 6: GNSS (GPS) ──", BOLD))

    # Turn on GNSS
    resp_on = send_at(ser, "AT+CGNSSPWR=1", wait=3)
    if "ERROR" in resp_on:
        print(coloured("  ! GNSS power-on returned error. May already be on.", YELLOW))
        send_at(ser, "AT+CGNSSPWR?")

    # Check GNSS info
    print("  Requesting GNSS data (this may take up to 60s for first fix)...")
    resp = send_at(ser, "AT+CGNSSINFO", wait=3)
    if "+CGNSSINFO:" in resp:
        parts = resp.split(":")[1].strip()
        if parts and parts[0] != "," and parts.strip(","):
            print(coloured("  ✓ GNSS has a fix!", GREEN))
        else:
            print(coloured("  ! GNSS powered on but no fix yet (need clear sky view).", YELLOW))
    return True


def test_data(ser):
    """Test 7: Data/internet connectivity."""
    print(coloured("── Test 7: Data Connection ──", BOLD))
    send_at(ser, "AT+CGATT?")                 # GPRS attach status
    send_at(ser, "AT+CGDCONT?")               # PDP context
    send_at(ser, "AT+CGACT?")                 # PDP context activation
    return True


def send_sms(ser):
    """Interactive SMS sending with the two-step AT+CMGS flow."""
    print()
    print(coloured("── Send SMS ──", BOLD))
    print("  Enter the phone number with country code.")
    print("  Example: +639171234567")
    print()

    try:
        number = input("  Phone number: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\n  Cancelled.")
        return

    if not number:
        print(coloured("  No number entered. Cancelled.", RED))
        return

    # Basic validation
    if not number.startswith("+") and not number.isdigit():
        print(coloured("  ✗ Invalid number. Use format: +639171234567", RED))
        return

    try:
        message = input("  Message text: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\n  Cancelled.")
        return

    if not message:
        print(coloured("  No message entered. Cancelled.", RED))
        return

    print()
    print(f"    To:      {coloured(number, CYAN)}")
    print(f"    Message: {coloured(message, CYAN)}")
    print()

    try:
        confirm = input("  Send? y/n: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\n  Cancelled.")
        return

    if confirm not in ("y", "yes"):
        print("  Cancelled.")
        return

    print()

    # Step 1: Set text mode and drain everything
    ser.reset_input_buffer()
    ser.write(b"AT+CMGF=1\r\n")
    ser.flush()
    time.sleep(1)
    while ser.in_waiting:
        ser.read(ser.in_waiting)
        time.sleep(0.1)

    # Step 2: Send AT+CMGS="number"\r
    cmd = f'AT+CMGS="{number}"\r'
    print(f"    → AT+CMGS=\"{number}\"")
    ser.reset_input_buffer()
    ser.write(cmd.encode())
    ser.flush()

    # Wait for the ">" prompt (up to 5 seconds)
    prompt_resp = b""
    start = time.time()
    while time.time() - start < 5:
        time.sleep(0.2)
        if ser.in_waiting:
            prompt_resp += ser.read(ser.in_waiting)
        if b">" in prompt_resp:
            break
        if b"ERROR" in prompt_resp:
            break

    prompt_text = prompt_resp.decode(errors="replace")
    if ">" not in prompt_text:
        print(coloured(f"  ✗ Did not get '>' prompt. Got: {repr(prompt_text)}", RED))
        ser.write(b"\x1B")  # ESC to cancel
        ser.flush()
        return

    print(coloured("    ← > (ready for message)", GREEN))

    # Step 3: Send message text + Ctrl+Z (0x1A)
    payload = message.encode() + b"\x1A"
    ser.write(payload)
    ser.flush()
    print(f"    → {message} [Ctrl+Z]")

    # Step 4: Wait for +CMGS or ERROR (up to 30 seconds — network can be slow)
    print("    Waiting for network response (up to 30s)...")
    full_resp = b""
    start = time.time()
    while time.time() - start < 30:
        time.sleep(0.5)
        if ser.in_waiting:
            full_resp += ser.read(ser.in_waiting)
        decoded = full_resp.decode(errors="replace")
        # Look for final result (ignore echoed message text)
        if "+CMGS:" in decoded and "OK" in decoded:
            break
        if "ERROR" in decoded and decoded.strip().endswith("ERROR"):
            break
        if "+CMS ERROR" in decoded:
            break

    decoded = full_resp.decode(errors="replace")
    elapsed = time.time() - start

    print()
    # Filter out the echoed message text from the response
    for line in decoded.split("\n"):
        line = line.strip("\r\n\t ")
        if not line or line == message:
            continue
        if "+CMGS:" in line:
            print(f"    ← {coloured(line, GREEN)}")
        elif "OK" == line:
            print(f"    ← {coloured(line, GREEN)}")
        elif "ERROR" in line:
            print(f"    ← {coloured(line, RED)}")
        else:
            print(f"    ← {line}")

    print()
    if "+CMGS:" in decoded and "OK" in decoded:
        print(coloured(f"  ✓ SMS sent successfully! ({elapsed:.1f}s)", GREEN))
    elif "+CMS ERROR" in decoded:
        # Extract the specific CMS error
        for line in decoded.split("\n"):
            if "+CMS ERROR" in line:
                print(coloured(f"  ✗ {line.strip()}", RED))
        print()
        print("  Possible causes:")
        print("    - No load/credits on the SIM")
        print("    - Data-only SIM (cannot send SMS)")
        print("    - Invalid phone number")
        print("    - Network congestion — try again in a minute")
    elif "ERROR" in decoded:
        print(coloured(f"  ✗ SMS failed. Module returned ERROR.", RED))
    else:
        print(coloured(f"  ? No final response after {elapsed:.1f}s", YELLOW))
        print(f"    Raw: {repr(decoded)}")
    print()


def check_balance(ser):
    """Send USSD code *143# to check Globe balance and wait for async response."""
    print()
    print(coloured("── Check Balance (USSD) ──", BOLD))
    ser.reset_input_buffer()
    ser.write(b'AT+CUSD=1,"*143#",15\r\n')
    ser.flush()
    print(f"    → AT+CUSD=1,\"*143#\",15")

    # USSD result comes asynchronously — wait up to 15 seconds
    print("    Waiting for network response (up to 15s)...")
    full_resp = b""
    start = time.time()
    while time.time() - start < 15:
        time.sleep(0.5)
        if ser.in_waiting:
            full_resp += ser.read(ser.in_waiting)
        decoded = full_resp.decode(errors="replace")
        if "+CUSD:" in decoded:
            # Give a bit more time for full response
            time.sleep(1)
            if ser.in_waiting:
                full_resp += ser.read(ser.in_waiting)
            break

    decoded = full_resp.decode(errors="replace")
    print()
    if "+CUSD:" in decoded:
        for line in decoded.split("\n"):
            line = line.strip()
            if "+CUSD:" in line:
                # The balance info is in quotes: +CUSD: 0,"Your balance is...",15
                print(f"    ← {coloured(line, GREEN)}")
            elif line and line != "OK":
                print(f"    ← {line}")
        print()
        print(coloured("  ✓ Balance info received!", GREEN))
    elif "OK" in decoded:
        print(coloured("  ! Got OK but no balance yet. Type 'wait' to check for delayed response.", YELLOW))
    else:
        print(coloured(f"  ? No response. Raw: {repr(decoded)}", YELLOW))
    print()


def read_pending(ser):
    """Read any pending/async data from the module."""
    print()
    print(coloured("── Reading pending data (5s) ──", BOLD))
    full_resp = b""
    start = time.time()
    while time.time() - start < 5:
        time.sleep(0.5)
        if ser.in_waiting:
            full_resp += ser.read(ser.in_waiting)
    decoded = full_resp.decode(errors="replace")
    if decoded.strip():
        for line in decoded.strip().split("\n"):
            line = line.strip()
            if line:
                print(f"    ← {line}")
    else:
        print("    (no pending data)")
    print()


def interactive_mode(ser):
    """Interactive AT command shell."""
    print()
    print(coloured("═══════════════════════════════════════", BOLD))
    print(coloured("  Interactive AT Command Mode", BOLD))
    print(coloured("  Commands:", BOLD))
    print(coloured("    sms     — Send an SMS message", BOLD))
    print(coloured("    balance — Check SIM balance (Globe *143#)", BOLD))
    print(coloured("    wait    — Read pending/async responses", BOLD))
    print(coloured("    help    — Show commands", BOLD))
    print(coloured("    quit    — Exit", BOLD))
    print(coloured("    Or type any AT command directly", BOLD))
    print(coloured("═══════════════════════════════════════", BOLD))
    print()

    while True:
        try:
            cmd = input(f"  {coloured('AT>', CYAN)} ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not cmd:
            continue
        if cmd.lower() in ("quit", "exit", "q"):
            break
        if cmd.lower() == "sms":
            try:
                send_sms(ser)
            except Exception as e:
                print(coloured(f"  Error: {e}", RED))
            continue
        if cmd.lower() in ("balance", "bal"):
            try:
                check_balance(ser)
            except Exception as e:
                print(coloured(f"  Error: {e}", RED))
            continue
        if cmd.lower() in ("wait", "read"):
            try:
                read_pending(ser)
            except Exception as e:
                print(coloured(f"  Error: {e}", RED))
            continue
        if cmd.lower() == "help":
            print()
            print("  Available commands:")
            print(f"    {coloured('sms', CYAN)}      — Send an SMS message (guided)")
            print(f"    {coloured('balance', CYAN)}  — Check SIM balance via USSD *143#")
            print(f"    {coloured('wait', CYAN)}     — Read any pending async responses")
            print(f"    {coloured('help', CYAN)}     — Show this help")
            print(f"    {coloured('quit', CYAN)}     — Exit")
            print(f"    Or type any AT command (e.g. AT+CSQ)")
            print()
            continue

        try:
            send_at(ser, cmd, wait=2)
        except Exception as e:
            print(coloured(f"  Error: {e}", RED))


def main():
    parser = argparse.ArgumentParser(description="A7670E Windows USB Test")
    parser.add_argument("--port", "-p", help="COM port (e.g. COM5)")
    parser.add_argument("--interactive", "-i", action="store_true",
                        help="Go straight to interactive AT mode")
    parser.add_argument("--baud", "-b", type=int, default=BAUD_RATE,
                        help=f"Baud rate (default: {BAUD_RATE})")
    args = parser.parse_args()

    print()
    print(coloured("╔══════════════════════════════════════════╗", BOLD))
    print(coloured("║   A7670E USB Test — Windows Edition      ║", BOLD))
    print(coloured("╚══════════════════════════════════════════╝", BOLD))
    print()

    # ── Step 1: Find COM port ─────────────────────────────────────────────
    print(coloured("── Detecting COM ports ──", BOLD))
    port = pick_port(args.port)
    if not port:
        sys.exit(1)
    print()

    # ── Step 2: Open serial connection ────────────────────────────────────
    print(coloured(f"── Connecting to {port} at {args.baud} baud ──", BOLD))
    try:
        ser = serial.Serial(
            port=port,
            baudrate=args.baud,
            timeout=TIMEOUT,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            xonxoff=False,
            rtscts=False,
            dsrdtr=False,
        )
        print(coloured(f"  ✓ Opened {port}", GREEN))
    except serial.SerialException as e:
        print(coloured(f"  ✗ Cannot open {port}: {e}", RED))
        sys.exit(1)
    print()

    # Drain any boot messages
    time.sleep(1)
    boot_data = b""
    while ser.in_waiting:
        boot_data += ser.read(ser.in_waiting)
        time.sleep(0.1)
    if boot_data:
        print(coloured("── Boot messages from module ──", BOLD))
        for line in boot_data.decode(errors="replace").strip().split("\n"):
            line = line.strip()
            if line:
                print(f"    {line}")
        print()

    # ── Step 3: Interactive mode or full test suite ───────────────────────
    if args.interactive:
        # Quick AT check with retries (USB port may need a moment)
        ok = False
        for attempt in range(1, 4):
            resp = send_at(ser, "AT", show=False)
            if "OK" in resp:
                ok = True
                break
            print(f"  Attempt {attempt}/3 — no response, retrying...")
            time.sleep(1)
        if ok:
            print(coloured("  ✓ Module is responding!", GREEN))
        else:
            print(coloured("  ! No response after 3 attempts — try a different port?", YELLOW))
        interactive_mode(ser)
    else:
        # Run all tests
        results = {}

        results["Basic AT"] = test_basic(ser)
        print()

        if not results["Basic AT"]:
            print(coloured("Module is not responding. Troubleshooting:", RED))
            print("  1. Try a different COM port (there may be 2-3 ports)")
            print("  2. Check Device Manager for the correct port")
            print("  3. Make sure the module is powered on (LED blinking)")
            print("  4. Try unplugging and replugging the USB cable")
            ser.close()
            sys.exit(1)

        results["Module Info"] = test_module_info(ser)
        print()
        results["SIM Card"]    = test_sim(ser)
        print()
        results["Network"]     = test_network(ser)
        print()
        results["SMS"]         = test_sms(ser)
        print()
        results["GNSS"]        = test_gnss(ser)
        print()
        results["Data"]        = test_data(ser)
        print()

        # ── Summary ──────────────────────────────────────────────────────
        print(coloured("═══════════════════════════════════════", BOLD))
        print(coloured("  Test Summary", BOLD))
        print(coloured("═══════════════════════════════════════", BOLD))
        for name, passed in results.items():
            status = coloured("PASS", GREEN) if passed else coloured("FAIL", RED)
            print(f"    {name:20s} [{status}]")
        print()

        # Offer interactive mode
        try:
            ans = input("  Enter interactive AT mode? [y/N] ").strip().lower()
            if ans in ("y", "yes"):
                interactive_mode(ser)
        except (EOFError, KeyboardInterrupt):
            pass

    ser.close()
    print(coloured("  Done. Port closed.", GREEN))


if __name__ == "__main__":
    main()
