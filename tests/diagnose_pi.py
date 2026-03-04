#!/usr/bin/env python3
"""
Raspberry Pi System Diagnostics for PEL
=========================================
Checks all Pi-side configuration needed for A7670E UART communication.
Inspects: config.txt, cmdline.txt, serial devices, GPIO, kernel modules.

Run with:  python3 diagnose_pi.py
     or:   sudo python3 diagnose_pi.py   (for full GPIO access)
"""

import os
import sys
import subprocess
import glob
import time

# -- Colour helpers -----------------------------------------------------------
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
    print(f"\n{CYAN}{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}{RESET}")


def divider():
    print("-" * 60)


def read_file_safe(path):
    """Read a file and return its contents, or None if not found."""
    try:
        with open(path, "r") as f:
            return f.read()
    except (FileNotFoundError, PermissionError) as e:
        return None


# =============================================================================
# 1. Locate config.txt and cmdline.txt
# =============================================================================

def check_boot_files():
    header("1. BOOT FILE LOCATIONS")

    # Pi OS Bookworm+ uses /boot/firmware/, older uses /boot/
    paths = {
        "config.txt":  ["/boot/firmware/config.txt", "/boot/config.txt"],
        "cmdline.txt": ["/boot/firmware/cmdline.txt", "/boot/cmdline.txt"],
    }

    found = {}

    for name, candidates in paths.items():
        located = None
        for p in candidates:
            if os.path.exists(p):
                # Check if it's a redirect file
                content = read_file_safe(p)
                if content and "has moved to" in content:
                    print(f"  {p} ... {WARN} (redirect file)")
                    redirect_target = None
                    for line in content.splitlines():
                        if "moved to" in line:
                            # Extract path from "has moved to /boot/firmware/..."
                            parts = line.split("moved to")
                            if len(parts) > 1:
                                redirect_target = parts[1].strip()
                    if redirect_target and os.path.exists(redirect_target):
                        print(f"    -> Actual file: {redirect_target}")
                        located = redirect_target
                    continue
                located = p
                break

        if located:
            print(f"  {name:.<30s} {GREEN}{located}{RESET}")
            found[name] = located
        else:
            print(f"  {name:.<30s} {RED}NOT FOUND{RESET}")
            found[name] = None

    return found


# =============================================================================
# 2. Inspect config.txt
# =============================================================================

def check_config_txt(path):
    header("2. CONFIG.TXT ANALYSIS")

    if path is None:
        print(f"  {RED}Cannot check - file not found{RESET}")
        return

    content = read_file_safe(path)
    if content is None:
        print(f"  {RED}Cannot read {path}{RESET}")
        return

    print(f"  File: {path}")
    print(f"  Size: {len(content)} bytes, {len(content.splitlines())} lines")
    divider()

    # Key settings to check
    checks = {
        "enable_uart=1": {
            "required": True,
            "desc": "Enables hardware UART on GPIO 14/15",
        },
        "dtoverlay=disable-bt": {
            "required": True,
            "desc": "Frees PL011 UART from Bluetooth (Pi 3/4/5)",
        },
        "dtoverlay=miniuart-bt": {
            "required": False,
            "desc": "Alternative: moves BT to mini UART",
        },
        "dtoverlay=pi3-miniuart-bt": {
            "required": False,
            "desc": "Legacy alternative for Pi 3",
        },
        "core_freq=250": {
            "required": False,
            "desc": "Fixes mini UART clock (only if using ttyS0)",
        },
    }

    content_lines = content.splitlines()
    # Track active (non-commented) lines
    active_lines = [
        line.strip() for line in content_lines
        if line.strip() and not line.strip().startswith("#")
    ]

    for key, info in checks.items():
        # Check for the exact setting (not commented out)
        found_active = any(key in line for line in active_lines)
        # Check if it's present but commented out
        found_commented = any(
            key in line and line.strip().startswith("#")
            for line in content_lines
        )

        if found_active:
            status = PASS
        elif found_commented:
            status = f"{YELLOW}COMMENTED OUT{RESET}"
        else:
            status = FAIL if info["required"] else f"{YELLOW}not set{RESET}"

        label = "REQUIRED" if info["required"] else "optional"
        print(f"  {key:.<35s} {status}  ({label})")
        if not found_active and info["required"]:
            print(f"    -> {info['desc']}")
            if found_commented:
                print(f"    -> Uncomment this line in {path}")
            else:
                print(f"    -> Add '{key}' to {path}")

    # Show all dtoverlay lines
    divider()
    print(f"\n  {BOLD}All dtoverlay entries in config:{RESET}")
    overlays = [l.strip() for l in content_lines if "dtoverlay" in l.lower()]
    if overlays:
        for o in overlays:
            commented = o.startswith("#")
            tag = f"{YELLOW}(commented){RESET}" if commented else ""
            print(f"    {o} {tag}")
    else:
        print(f"    {YELLOW}(none found){RESET}")

    # Show all UART-related entries
    print(f"\n  {BOLD}All UART-related entries:{RESET}")
    uart_lines = [
        l.strip() for l in content_lines
        if any(k in l.lower() for k in ["uart", "serial", "bluetooth", "bt"])
    ]
    if uart_lines:
        for u in uart_lines:
            commented = u.startswith("#")
            tag = f"{YELLOW}(commented){RESET}" if commented else ""
            print(f"    {u} {tag}")
    else:
        print(f"    {YELLOW}(none found){RESET}")


# =============================================================================
# 3. Inspect cmdline.txt
# =============================================================================

def check_cmdline_txt(path):
    header("3. CMDLINE.TXT ANALYSIS")

    if path is None:
        print(f"  {RED}Cannot check - file not found{RESET}")
        return

    content = read_file_safe(path)
    if content is None:
        print(f"  {RED}Cannot read {path}{RESET}")
        return

    print(f"  File: {path}")
    divider()

    # Show full content
    print(f"\n  {BOLD}Full contents:{RESET}")
    print(f"    {content.strip()}")
    print()

    # Parse kernel parameters
    params = content.strip().split()

    # Check for serial console (bad -- steals UART)
    serial_consoles = [p for p in params if p.startswith("console=") and "serial" in p.lower()]
    tty_consoles = [p for p in params if p.startswith("console=") and "tty" in p.lower()]

    if serial_consoles:
        for sc in serial_consoles:
            print(f"  Serial console: {sc} ... {FAIL}")
            print(f"    -> This steals the UART port from your A7670E!")
            print(f"    -> Remove '{sc}' from {path}")
            print(f"    -> Or run: sudo raspi-config -> Interface -> Serial Port")
            print(f"       Set login shell: No, Hardware serial: Yes")
    else:
        print(f"  Serial console  ... {PASS} (none - UART is free)")

    if tty_consoles:
        for tc in tty_consoles:
            print(f"  TTY console: {tc} ... {INFO} (normal)")

    # Check for other relevant params
    for param in params:
        if "kgdboc" in param:
            print(f"  Kernel debugger: {param} ... {WARN} (may use serial)")


# =============================================================================
# 4. Serial device enumeration
# =============================================================================

def check_serial_devices():
    header("4. SERIAL DEVICES")

    # Enumerate all serial-related devices
    patterns = [
        "/dev/serial*",
        "/dev/ttyS*",
        "/dev/ttyAMA*",
        "/dev/ttyACM*",
        "/dev/ttyUSB*",
    ]

    all_devs = []
    for pat in patterns:
        all_devs.extend(glob.glob(pat))
    all_devs = sorted(set(all_devs))

    if not all_devs:
        print(f"  {RED}No serial devices found!{RESET}")
        print(f"  -> UART is likely not enabled")
        return

    print(f"  Found {len(all_devs)} serial device(s):\n")

    for dev in all_devs:
        real = os.path.realpath(dev)
        is_link = os.path.islink(dev)

        if is_link:
            print(f"    {dev} -> {real}")
        else:
            print(f"    {dev}")

        # Annotate known devices
        if "ttyAMA0" in real:
            print(f"      {GREEN}^ PL011 UART (full hardware UART - recommended){RESET}")
        elif "ttyS0" in real:
            print(f"      {YELLOW}^ Mini UART (unreliable - clock tied to CPU freq){RESET}")
            print(f"      Add 'dtoverlay=disable-bt' to config.txt and reboot")

    # Specific check for /dev/serial0
    divider()
    serial0 = "/dev/serial0"
    if os.path.exists(serial0):
        real = os.path.realpath(serial0)
        if "ttyAMA0" in real:
            print(f"\n  {serial0} -> {real} ... {PASS} (PL011)")
        elif "ttyS0" in real:
            print(f"\n  {serial0} -> {real} ... {WARN} (mini UART)")
        else:
            print(f"\n  {serial0} -> {real} ... {INFO}")
    else:
        print(f"\n  {serial0} ... {FAIL} (does not exist)")


# =============================================================================
# 5. Kernel modules and services
# =============================================================================

def check_kernel_and_services():
    header("5. KERNEL MODULES & SERVICES")

    # Check if serial-getty is active on ttyS0 or ttyAMA0 (would steal UART)
    for tty in ["ttyS0", "ttyAMA0", "serial0"]:
        service = f"serial-getty@{tty}.service"
        try:
            result = subprocess.run(
                ["systemctl", "is-active", service],
                capture_output=True, text=True, timeout=5
            )
            status = result.stdout.strip()
            if status == "active":
                print(f"  {service} ... {FAIL} (ACTIVE - steals UART!)")
                print(f"    -> Stop:    sudo systemctl stop {service}")
                print(f"    -> Disable: sudo systemctl disable {service}")
            elif status == "inactive":
                print(f"  {service} ... {PASS} (inactive)")
            else:
                print(f"  {service} ... {INFO} ({status})")
        except (subprocess.TimeoutExpired, FileNotFoundError):
            print(f"  {service} ... {WARN} (cannot check)")

    divider()

    # Check for Bluetooth services
    try:
        result = subprocess.run(
            ["systemctl", "is-active", "bluetooth.service"],
            capture_output=True, text=True, timeout=5
        )
        bt_status = result.stdout.strip()
        if bt_status == "active":
            print(f"  bluetooth.service    ... {YELLOW}ACTIVE{RESET}")
            print(f"    If dtoverlay=disable-bt is set, BT service may fail.")
            print(f"    This is expected and harmless.")
        else:
            print(f"  bluetooth.service    ... {INFO} ({bt_status})")
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # Check loaded kernel modules
    divider()
    print(f"\n  {BOLD}Relevant kernel modules:{RESET}")
    try:
        result = subprocess.run(
            ["lsmod"], capture_output=True, text=True, timeout=5
        )
        modules = result.stdout
        relevant = ["pl011", "ttyama", "serial", "uart", "8250", "hci_uart", "btbcm", "bluetooth"]
        found_any = False
        for mod_line in modules.splitlines()[1:]:  # skip header
            mod_name = mod_line.split()[0].lower()
            if any(r in mod_name for r in relevant):
                print(f"    {mod_line.strip()}")
                found_any = True
        if not found_any:
            print(f"    {YELLOW}(no UART/serial modules found){RESET}")
    except (subprocess.TimeoutExpired, FileNotFoundError):
        print(f"    {WARN} Cannot run lsmod")


# =============================================================================
# 6. GPIO state check
# =============================================================================

def check_gpio():
    header("6. GPIO STATE (UART + PWRKEY pins)")

    # Try raspi-gpio or pinctrl
    gpio_cmd = None
    for cmd in ["pinctrl", "raspi-gpio"]:
        try:
            subprocess.run([cmd], capture_output=True, timeout=3)
            gpio_cmd = cmd
            break
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue

    if gpio_cmd is None:
        print(f"  {WARN} Neither 'pinctrl' nor 'raspi-gpio' available")
        print(f"  Install with: sudo apt install raspi-gpio")
        return

    pins_of_interest = {
        4:  "PWRKEY",
        14: "TXD (Pi TX -> Module RX)",
        15: "RXD (Pi RX <- Module TX)",
    }

    print(f"  Using: {gpio_cmd}\n")

    for pin, label in pins_of_interest.items():
        try:
            if gpio_cmd == "pinctrl":
                result = subprocess.run(
                    ["pinctrl", "get", str(pin)],
                    capture_output=True, text=True, timeout=5
                )
            else:
                result = subprocess.run(
                    ["raspi-gpio", "get", str(pin)],
                    capture_output=True, text=True, timeout=5
                )
            output = result.stdout.strip()
            if output:
                print(f"  GPIO {pin:>2} ({label}):")
                print(f"    {output}")

                # Check if UART pins have correct alt function
                if pin in (14, 15):
                    out_lower = output.lower()
                    if "alt0" in out_lower or "alt5" in out_lower or "a0" in out_lower:
                        print(f"    -> {PASS} (UART alt function active)")
                    elif "input" in out_lower or "output" in out_lower:
                        print(f"    -> {FAIL} (set as GPIO, not UART!)")
                        print(f"       UART not enabled on this pin")
                    else:
                        print(f"    -> {INFO} (check alt function)")
            print()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            print(f"  GPIO {pin:>2} ({label}): {WARN} cannot read")


# =============================================================================
# 7. Quick serial loopback test
# =============================================================================

def check_serial_loopback():
    header("7. SERIAL PORT READ/WRITE TEST")

    port = "/dev/serial0"
    if not os.path.exists(port):
        print(f"  {RED}{port} not available - skipping{RESET}")
        return

    try:
        import serial as pyserial
    except ImportError:
        print(f"  {WARN} pyserial not installed - skipping")
        return

    # --- Step A: Pulse PWRKEY to ensure module is on ---
    print(f"  Pulsing PWRKEY (GPIO 4) to power on module...")
    try:
        import RPi.GPIO as GPIO
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(4, GPIO.OUT, initial=GPIO.HIGH)
        import time as _t
        _t.sleep(0.1)
        GPIO.output(4, GPIO.LOW)
        _t.sleep(1.5)
        GPIO.output(4, GPIO.HIGH)
        print(f"  PWRKEY pulse done. Waiting 5s for module boot...\n")
        _t.sleep(5.0)
    except Exception as e:
        print(f"  {WARN} PWRKEY pulse failed: {e}")
        print(f"  Continuing without PWRKEY...\n")

    # --- Step B: Drain any boot URCs and display them ---
    print(f"  Port: {port}")
    print(f"  Draining boot messages first...\n")

    try:
        ser = pyserial.Serial(port, 115200, timeout=1)

        # Read any URCs the module sent during boot
        boot_data = b""
        for _ in range(3):
            chunk = ser.read(ser.in_waiting or 256)
            if chunk:
                boot_data += chunk
            time.sleep(0.5)

        if boot_data:
            text = boot_data.decode("ascii", errors="replace").strip()
            print(f"  {BOLD}Boot URCs received ({len(boot_data)} bytes):{RESET}")
            for line in text.splitlines():
                line = line.strip()
                if line:
                    print(f"    <- {line}")
            print()
        else:
            print(f"  No boot messages received.\n")

        # --- Step C: Send AT multiple times with delays ---
        # Try both CR-only and CR+LF, with explicit flush
        at_variants = [
            (b"AT\r",   "AT\\r"),
            (b"AT\r\n", "AT\\r\\n"),
        ]
        print(f"  {BOLD}Sending AT command (5 attempts x 2 formats, 1s apart):{RESET}\n")

        got_ok = False
        all_responses = []
        attempt_num = 0

        for at_cmd, at_label in at_variants:
            if got_ok:
                break
            for _ in range(5):
                attempt_num += 1
                ser.reset_input_buffer()
                written = ser.write(at_cmd)
                ser.flush()                          # <-- force bytes out
                time.sleep(1.0)

                data = ser.read(ser.in_waiting or 256)
                if data:
                    text = data.decode("ascii", errors="replace").strip()
                    hex_preview = " ".join(f"{b:02X}" for b in data[:24])

                    if "OK" in text:
                        print(f"  #{attempt_num:>2} [{at_label:8s}]: {GREEN}'OK' received!{RESET}")
                        print(f"       Hex: {hex_preview}")
                        got_ok = True
                        all_responses.append(("OK", text))
                        break
                    else:
                        clean = text.replace("\r", "\\r").replace("\n", "\\n")[:60]
                        print(f"  #{attempt_num:>2} [{at_label:8s}]: got data -> {YELLOW}{clean}{RESET}")
                        print(f"       Hex: {hex_preview}")
                        all_responses.append(("DATA", text))
                else:
                    print(f"  #{attempt_num:>2} [{at_label:8s}]: {RED}no response{RESET}")
                    all_responses.append(("NONE", ""))

        # --- Step D: Echo test - write raw bytes and report count ---
        if not got_ok:
            print(f"\n  {BOLD}Verifying Pi TX line sends bytes:{RESET}")
            ser.reset_input_buffer()
            n = ser.write(b"AAAAA")
            ser.flush()
            print(f"    ser.write(b'AAAAA') returned {n} bytes written")
            # Check if OS-level UART is actually configured for output
            try:
                result = subprocess.run(
                    ["pinctrl", "get", "14"],
                    capture_output=True, text=True, timeout=3
                )
                pin14_state = result.stdout.strip()
                print(f"    GPIO 14 state right now: {pin14_state}")
            except Exception:
                pass

        ser.close()
        print()

        # --- Step E: Diagnosis ---
        divider()
        has_data = any(r[0] in ("OK", "DATA") for r in all_responses)

        if got_ok:
            print(f"\n  Result: {PASS} - Module responds to AT commands!")

        elif has_data and not got_ok:
            print(f"\n  Result: {WARN} - Module TX works but does NOT reply to AT")
            print()
            print(f"  {BOLD}Diagnosis: Pi TX -> Module RX path is broken.{RESET}")
            print(f"  The module sends data (URCs, boot messages) to the Pi,")
            print(f"  but never receives your AT commands.\n")
            print()
            print(f"  {BOLD}>>> TRY THIS FIRST: SWAP R AND T WIRES <<<{RESET}")
            print()
            print(f"  Some A7670E breakout boards label pins from the HOST")
            print(f"  perspective instead of the module perspective:")
            print(f"    R = 'you Receive from me'  = module TX output")
            print(f"    T = 'you Transmit to me'   = module RX input")
            print()
            print(f"  If that's your board, the correct wiring is:")
            print(f"    {BOLD}T{RESET} (module RX) -> Pi Pin 8  (GPIO 14 / TXD)")
            print(f"    {BOLD}R{RESET} (module TX) -> Pi Pin 10 (GPIO 15 / RXD)")
            print()
            print(f"  {BOLD}Power off, swap R<->T wires, power on, run again.{RESET}")
            print()
            print(f"  If swapping doesn't help, also check:")
            print(f"    1. Voltage levels - A7670E uses 1.8V UART; some boards")
            print(f"       need a level shifter to talk to 3.3V Pi GPIO")
            print(f"    2. Damaged RX trace on breakout board")
            print(f"    3. Try connecting at 9600 baud (some modules default to it)")

        else:
            print(f"\n  Result: {FAIL} - No data received at all")
            print()
            print(f"  {BOLD}Module is completely silent. Check:{RESET}")
            print(f"    1. VCC: Is the module getting 5V power?")
            print(f"    2. GND: Is ground connected between module and Pi?")
            print(f"    3. T (TX) wire must go to Pi Pin 10 (GPIO 15 / RXD)")
            print(f"       (or R if your board labels from host perspective)")
            print(f"    4. PWRKEY: Is K wire connected to Pi Pin 7 (GPIO 4)?")
            print(f"    5. Try unplugging VCC, wait 5s, replug and run again")

    except pyserial.SerialException as e:
        print(f"  {RED}Serial error: {e}{RESET}")
        if "Permission" in str(e):
            print(f"  -> Run with sudo: sudo python3 {sys.argv[0]}")
    except Exception as e:
        print(f"  {RED}Error: {e}{RESET}")


# =============================================================================
# 8. Summary and recommendations
# =============================================================================

def print_summary(boot_files):
    header("SUMMARY & RECOMMENDATIONS")

    issues = []

    # Check config.txt essentials
    cfg_path = boot_files.get("config.txt")
    if cfg_path:
        content = read_file_safe(cfg_path) or ""
        active = [
            l.strip() for l in content.splitlines()
            if l.strip() and not l.strip().startswith("#")
        ]
        active_str = "\n".join(active)
        if "enable_uart=1" not in active_str:
            issues.append(f"Add 'enable_uart=1' to {cfg_path}")
        if "dtoverlay=disable-bt" not in active_str:
            issues.append(f"Add 'dtoverlay=disable-bt' to {cfg_path}")

    # Check serial0
    serial0 = "/dev/serial0"
    if not os.path.exists(serial0):
        issues.append(f"{serial0} does not exist - enable UART and reboot")
    else:
        real = os.path.realpath(serial0)
        if "ttyS0" in real:
            issues.append(f"{serial0} -> ttyS0 (mini UART). Need disable-bt overlay + reboot")

    # Check serial-getty
    for tty in ["ttyS0", "ttyAMA0"]:
        try:
            result = subprocess.run(
                ["systemctl", "is-active", f"serial-getty@{tty}.service"],
                capture_output=True, text=True, timeout=5
            )
            if result.stdout.strip() == "active":
                issues.append(f"serial-getty@{tty}.service is active (disable it)")
        except Exception:
            pass

    if issues:
        print(f"  {RED}{BOLD}Issues found ({len(issues)}):{RESET}")
        for i, issue in enumerate(issues, 1):
            print(f"    {i}. {issue}")
        print()
        print(f"  {BOLD}Quick fix commands:{RESET}")
        if cfg_path:
            for issue in issues:
                if "enable_uart" in issue:
                    print(f"    echo 'enable_uart=1' | sudo tee -a {cfg_path}")
                if "disable-bt" in issue:
                    print(f"    echo 'dtoverlay=disable-bt' | sudo tee -a {cfg_path}")
                if "serial-getty" in issue:
                    svc = issue.split()[0]
                    print(f"    sudo systemctl stop {svc}")
                    print(f"    sudo systemctl disable {svc}")
            print(f"    sudo reboot")
    else:
        print(f"  {GREEN}{BOLD}All system checks passed!{RESET}")
        print()
        print(f"  If A7670E still doesn't respond, the issue is likely:")
        print(f"    1. TX/RX wires swapped")
        print(f"    2. Module not powered (check VCC + PWRKEY)")
        print(f"    3. Module needs more boot time after PWRKEY pulse")
        print(f"    4. Faulty module or broken wire")


# =============================================================================
# Main
# =============================================================================

def main():
    print(f"\n{BOLD}{CYAN}Raspberry Pi System Diagnostics for PEL{RESET}")
    print(f"{'=' * 60}")
    print(f"  Date:     ", end="")
    os.system("date")
    print(f"  Hostname: ", end="")
    os.system("hostname")
    print(f"  User:     {os.environ.get('USER', 'unknown')}")
    print(f"  Sudo:     {'yes' if os.geteuid() == 0 else 'no (some checks may be limited)'}")

    # Run all checks
    boot_files = check_boot_files()
    check_config_txt(boot_files.get("config.txt"))
    check_cmdline_txt(boot_files.get("cmdline.txt"))
    check_serial_devices()
    check_kernel_and_services()
    check_gpio()
    check_serial_loopback()
    print_summary(boot_files)

    print()


if __name__ == "__main__":
    main()
