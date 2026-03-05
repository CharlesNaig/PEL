"""
A7670E LTE Cat-1 Module Driver — SMS + GNSS
=============================================
Handles all communication with the SIMCOM A7670E via UART AT commands.
Replaces both SIM800L (GSM) and GTU-7 (GPS) from the Arduino version.

Supports two connection methods:
  - USB: A7670E micro-USB → Pi USB port (auto-detects AT port)
  - GPIO UART: A7670E TX/RX → Pi GPIO 14/15

Port of:
  - initGSM(), sendSMS(), waitForResponse() from main.ino (lines 474-594)
  - acquireGPS(), buildMapLink() from main.ino (lines 400-468)
  - AT command patterns from tests/test_a7670e/test_a7670e.ino

Dependencies: pyserial
"""

import serial
import serial.tools.list_ports
import time
import glob

try:
    import RPi.GPIO as GPIO
except ImportError:
    GPIO = None


def find_usb_at_port():
    """
    Auto-detect the A7670E AT command port when connected via USB.

    On Linux (Pi), SIMCOM A7670E creates four /dev/ttyUSB* ports:
      ttyUSB0 = Diag, ttyUSB1 = NMEA/GPS, ttyUSB2 = AT, ttyUSB3 = Modem
    The AT port is typically index 2 (third port).

    Falls back to probing each port with 'AT' if the index guess fails.
    Returns the port path string, or None if not found.
    """
    # Method 1: Look for SIMCOM by USB VID (0x1E0E)
    simcom_ports = []
    for p in serial.tools.list_ports.comports():
        if p.vid == 0x1E0E:
            simcom_ports.append(p.device)
    simcom_ports.sort()

    if simcom_ports:
        print(f"[A7670E] Found SIMCOM USB ports: {simcom_ports}")
        # AT port is typically the 3rd one (index 2)
        if len(simcom_ports) >= 3:
            at_candidate = simcom_ports[2]
            print(f"[A7670E] Trying AT port candidate: {at_candidate}")
            return at_candidate
        # If fewer ports, try the last one
        return simcom_ports[-1]

    # Method 2: Check for /dev/ttyUSB* ports generically
    usb_ports = sorted(glob.glob("/dev/ttyUSB*"))
    if usb_ports:
        print(f"[A7670E] Found USB serial ports: {usb_ports}")
        # Probe each port for AT response
        for port_path in usb_ports:
            try:
                test_ser = serial.Serial(port_path, 115200, timeout=1)
                test_ser.reset_input_buffer()
                test_ser.write(b"AT\r\n")
                time.sleep(0.5)
                resp = test_ser.read(test_ser.in_waiting or 64).decode(errors="replace")
                test_ser.close()
                if "OK" in resp:
                    print(f"[A7670E] AT responded on {port_path}")
                    return port_path
            except (serial.SerialException, OSError):
                continue
        # If probe fails, try the 3rd port (common AT index)
        if len(usb_ports) >= 3:
            return usb_ports[2]
        return usb_ports[0]

    print("[A7670E] No USB serial ports found. Is the module plugged in?")
    return None


class A7670E:
    """
    Driver for SIMCOM A7670E LTE Cat-1 module.
    Handles: module init, GNSS (GPS), and SMS over a single UART.
    """

    def __init__(self, port, baud, fallback_baud=9600, timeout=1.0,
                 pwrkey_pin=None):
        """
        Open serial connection to A7670E.
        If pwrkey_pin is provided, pulses PWRKEY LOW for 1.5 s to ensure the
        module is powered on before attempting serial communication.
        Tries primary baud rate first, falls back if no response.

        Port of: baud detection in test_a7670e.ino setup()

        Args:
            port: Serial port path (e.g. '/dev/serial0')
            baud: Primary baud rate (e.g. 115200)
            fallback_baud: Fallback baud rate (e.g. 9600)
            timeout: Serial read timeout in seconds
            pwrkey_pin: BCM GPIO pin connected to A7670E PWRKEY (None to skip)
        """
        self.port = port
        self.timeout = timeout
        self._baud = baud
        self.ser = None
        self._connected = False
        self._pwrkey_pin = pwrkey_pin

        # Pulse PWRKEY to power on the module
        if pwrkey_pin is not None:
            self._pwrkey_pulse(pwrkey_pin)

        # Try primary baud
        print(f"[A7670E] Opening {port} at {baud} baud...")
        try:
            self.ser = serial.Serial(
                port, baud, timeout=timeout,
                xonxoff=False, rtscts=False, dsrdtr=False,
            )
            time.sleep(0.5)
            self._flush()

            if self._probe():
                print(f"[A7670E] Connected at {baud} baud")
                self._connected = True
                return
        except serial.SerialException as e:
            print(f"[A7670E] Serial error at {baud}: {e}")

        # Fallback baud
        print(f"[A7670E] No response at {baud}. Trying {fallback_baud}...")
        try:
            if self.ser and self.ser.is_open:
                self.ser.close()
            self.ser = serial.Serial(
                port, fallback_baud, timeout=timeout,
                xonxoff=False, rtscts=False, dsrdtr=False,
            )
            time.sleep(0.5)
            self._flush()

            if self._probe():
                print(f"[A7670E] Connected at {fallback_baud} baud")
                self._baud = fallback_baud
                self._connected = True
                return
        except serial.SerialException as e:
            print(f"[A7670E] Serial error at {fallback_baud}: {e}")

        print("[A7670E] ERROR: No response at any baud rate.")
        print("[A7670E] Check wiring and power supply.")
        self._connected = False

    @property
    def is_connected(self):
        """True if modem responded during init."""
        return self._connected

    def close(self):
        """Close serial port."""
        if self.ser and self.ser.is_open:
            self.ser.close()
            print("[A7670E] Serial port closed")

    # ==========================================================
    # Connection recovery helpers
    # ==========================================================

    def _reopen_serial(self):
        """
        Close and reopen the serial port at the last-known baud rate.
        Used to recover from stale/hung connections after long idle periods.
        """
        try:
            if self.ser and self.ser.is_open:
                self.ser.close()
            time.sleep(1.0)
            self.ser = serial.Serial(
                self.port, self._baud, timeout=self.timeout,
                xonxoff=False, rtscts=False, dsrdtr=False,
            )
            time.sleep(0.5)
            self._flush()
            print("[A7670E] Serial port reopened")
        except serial.SerialException as e:
            print(f"[A7670E] Reopen error: {e}")

    def wake(self, max_attempts=10):
        """
        Ensure the module is responsive after a long idle period.

        Strategy (per attempt):
          1. Send AT — if OK, module is alive.
          2. Reopen serial port and retry AT.
          3. (GPIO mode) Pulse PWRKEY to power-cycle the module.

        Args:
            max_attempts: Maximum wake cycles before giving up

        Returns:
            True if module is responsive
        """
        for attempt in range(max_attempts):
            # Quick AT ping
            try:
                resp = self.send_command("AT", timeout=2.0)
                if "OK" in resp:
                    if attempt > 0:
                        print(f"[A7670E] Module awake (attempt {attempt + 1})")
                    return True
            except Exception:
                pass

            print(f"[A7670E] No response — waking "
                  f"(attempt {attempt + 1}/{max_attempts})")

            # Reopen serial and retry
            self._reopen_serial()
            time.sleep(0.5)
            try:
                resp = self.send_command("AT", timeout=2.0)
                if "OK" in resp:
                    print("[A7670E] Awake after serial reopen")
                    self._connected = True
                    return True
            except Exception:
                pass

            # GPIO mode: pulse PWRKEY to power-cycle
            if self._pwrkey_pin is not None:
                print("[A7670E] Pulsing PWRKEY to restart module...")
                self._pwrkey_pulse(self._pwrkey_pin)
                time.sleep(3.0)
                try:
                    resp = self.send_command("AT", timeout=2.0)
                    if "OK" in resp:
                        print("[A7670E] Awake after PWRKEY pulse")
                        self._connected = True
                        return True
                except Exception:
                    pass

            time.sleep(2.0)

        print(f"[A7670E] FAILED to wake after {max_attempts} attempts")
        return False

    # ==========================================================
    # Low-level AT helpers
    # Port of: waitForResponse() and serial read logic in main.ino
    # ==========================================================

    def _flush(self):
        """Drain any pending data from the serial buffer."""
        if self.ser and self.ser.is_open:
            self.ser.reset_input_buffer()

    def _probe(self):
        """Send AT and check for OK response (used for baud detection)."""
        try:
            self.ser.write(b"AT\r\n")
            time.sleep(0.5)
            response = self.ser.read(self.ser.in_waiting or 128).decode("ascii", errors="ignore")
            return "OK" in response
        except Exception:
            return False

    @staticmethod
    def _pwrkey_pulse(pin):
        """
        Pulse PWRKEY LOW for 1.5 s then release HIGH.
        The A7670E requires this to power on / toggle power state.
        Waits 3 s after pulse for the module to boot.
        """
        if GPIO is None:
            print("[A7670E] WARNING: RPi.GPIO not available, skipping PWRKEY pulse")
            return
        print(f"[A7670E] PWRKEY pulse on GPIO {pin} ...")
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(pin, GPIO.OUT, initial=GPIO.HIGH)
        time.sleep(0.1)
        GPIO.output(pin, GPIO.LOW)
        time.sleep(1.5)
        GPIO.output(pin, GPIO.HIGH)
        print("[A7670E] PWRKEY released — waiting 3 s for boot ...")
        time.sleep(3.0)

    def send_command(self, cmd, timeout=2.0):
        """
        Send AT command, return full response string.

        Args:
            cmd: AT command string (e.g. 'AT+CSQ')
            timeout: Max seconds to wait for response

        Returns:
            Response string from modem
        """
        if not self.ser or not self.ser.is_open:
            return ""

        self._flush()
        self.ser.write((cmd + "\r\n").encode("ascii"))
        time.sleep(0.1)

        response = ""
        deadline = time.time() + timeout

        while time.time() < deadline:
            if self.ser.in_waiting:
                chunk = self.ser.read(self.ser.in_waiting).decode("ascii", errors="ignore")
                response += chunk
                # Stop early if we got OK or ERROR
                if "OK" in response or "ERROR" in response:
                    break
            time.sleep(0.05)

        return response.strip()

    def wait_for(self, expected, timeout=2.0):
        """
        Wait for expected substring in serial stream.
        Direct port of: waitForResponse(expected, timeout) in main.ino

        Args:
            expected: Substring to look for
            timeout: Max seconds to wait

        Returns:
            True if expected string found within timeout
        """
        response = ""
        deadline = time.time() + timeout

        while time.time() < deadline:
            if self.ser.in_waiting:
                chunk = self.ser.read(self.ser.in_waiting).decode("ascii", errors="ignore")
                response += chunk
                if expected in response:
                    return True
            time.sleep(0.01)

        return False

    def wait_for_prompt(self, timeout=5.0):
        """
        Wait for '>' prompt (used before SMS body).
        Port of: waitForPrompt() in test_a7670e.ino

        Returns:
            True if '>' received within timeout
        """
        deadline = time.time() + timeout

        while time.time() < deadline:
            if self.ser.in_waiting:
                data = self.ser.read(self.ser.in_waiting).decode("ascii", errors="ignore")
                if ">" in data:
                    return True
                if "ERROR" in data:
                    return False
            time.sleep(0.01)

        return False

    # ==========================================================
    # Module initialization
    # Port of: initGSM() in main.ino + Tests 1-6 in test_a7670e.ino
    # ==========================================================

    def init_module(self):
        """
        Initialize A7670E: AT, ATE0, check SIM, signal, registration.

        Returns:
            True if module is ready for operation

        AT commands: AT, ATE0, AT+CPIN?, AT+CSQ, AT+CREG?, AT+COPS?
        Maps to: initGSM() in main.ino
        """
        if not self._connected:
            print("[A7670E] Cannot init — not connected")
            return False

        print("[A7670E] Initializing module...")

        # Basic AT check
        resp = self.send_command("AT", timeout=2.0)
        if "OK" not in resp:
            print("[A7670E] ERROR: Module not responding")
            return False
        print("[A7670E] AT OK")

        # Disable echo for cleaner responses
        self.send_command("ATE0", timeout=1.0)
        print("[A7670E] Echo disabled")

        # Check SIM
        sim_status = self.check_sim()
        print(f"[A7670E] SIM: {sim_status}")
        if sim_status != "READY":
            print(f"[A7670E] WARNING: SIM not ready ({sim_status})")
            return False

        # Signal quality
        rssi = self.get_signal_quality()
        if rssi == 99:
            print("[A7670E] WARNING: No signal (RSSI=99)")
        elif rssi >= 20:
            print(f"[A7670E] Signal: {rssi}/31 (Excellent)")
        elif rssi >= 15:
            print(f"[A7670E] Signal: {rssi}/31 (Good)")
        elif rssi >= 10:
            print(f"[A7670E] Signal: {rssi}/31 (Fair)")
        else:
            print(f"[A7670E] Signal: {rssi}/31 (Weak)")

        # Network registration
        reg_status = self.check_registration()
        print(f"[A7670E] Network: {reg_status}")
        if reg_status not in ("home", "roaming"):
            print("[A7670E] WARNING: Not registered on network")
            # Don't return False — may register shortly

        # Operator
        resp = self.send_command("AT+COPS?", timeout=3.0)
        for line in resp.splitlines():
            if "+COPS:" in line:
                print(f"[A7670E] Operator: {line.strip()}")
                break

        # Set SMS text mode
        resp = self.send_command("AT+CMGF=1", timeout=2.0)
        if "OK" in resp:
            print("[A7670E] SMS text mode set")
        else:
            print("[A7670E] WARNING: Could not set SMS text mode")

        print("[A7670E] Module initialized")
        return True

    def check_sim(self):
        """
        Check SIM card status.
        Maps to: checkSIMStatus() in test_a7670e.ino

        Returns:
            'READY', 'PIN', 'PUK', 'NOT INSERTED', or 'UNKNOWN'
        """
        resp = self.send_command("AT+CPIN?", timeout=2.0)

        if "READY" in resp:
            return "READY"
        elif "SIM PIN" in resp:
            return "PIN"
        elif "SIM PUK" in resp:
            return "PUK"
        elif "NOT INSERTED" in resp or "NOT READY" in resp:
            return "NOT INSERTED"
        else:
            return "UNKNOWN"

    def get_signal_quality(self):
        """
        Get RSSI value (0-31, 99=unknown).
        Maps to: checkSignal() in test_a7670e.ino

        Returns:
            Integer RSSI value
        """
        resp = self.send_command("AT+CSQ", timeout=2.0)

        for line in resp.splitlines():
            if "+CSQ:" in line:
                try:
                    # Format: +CSQ: <rssi>,<ber>
                    parts = line.split(":")[1].strip().split(",")
                    return int(parts[0].strip())
                except (IndexError, ValueError):
                    pass
        return 99

    def check_registration(self):
        """
        Check network registration status.
        Maps to: checkRegistration() in test_a7670e.ino

        Returns:
            'home', 'roaming', 'searching', 'denied', or 'unknown'
        """
        resp = self.send_command("AT+CREG?", timeout=2.0)

        for line in resp.splitlines():
            if "+CREG:" in line:
                if ",1" in line:
                    return "home"
                elif ",5" in line:
                    return "roaming"
                elif ",2" in line:
                    return "searching"
                elif ",3" in line:
                    return "denied"
        return "unknown"

    # ==========================================================
    # GNSS (GPS) functions
    # Replaces: acquireGPS(), buildMapLink() in main.ino
    # Uses: AT+CGNSPWR=1, AT+CGNSINF from test_a7670e.ino
    # ==========================================================

    def enable_gnss(self):
        """
        Power on GNSS engine: AT+CGNSPWR=1
        Maps to: Test 7 in test_a7670e.ino

        Returns:
            True if GNSS powered on successfully
        """
        resp = self.send_command("AT+CGNSPWR=1", timeout=2.0)
        success = "OK" in resp
        if success:
            print("[A7670E] GNSS engine powered on")
        else:
            print("[A7670E] WARNING: Failed to enable GNSS")
        return success

    def disable_gnss(self):
        """Power off GNSS engine to save power."""
        resp = self.send_command("AT+CGNSPWR=0", timeout=2.0)
        return "OK" in resp

    def acquire_gps(self, timeout=30, poll_interval=5, progress_callback=None):
        """
        Poll AT+CGNSINF until valid fix or timeout.

        Args:
            timeout: Max seconds to wait for fix
            poll_interval: Seconds between polls
            progress_callback: Optional callable(elapsed, timeout) for progress

        Returns:
            (lat, lng, utc_time) on success, or (None, None, None) on timeout

        Maps to: acquireGPS(float* lat, float* lng) in main.ino
                 waitForGPSFix() + parseGNSSInfo() in test_a7670e.ino
        """
        print(f"[A7670E] Searching for GPS satellites (timeout: {timeout}s)...")
        start = time.time()
        poll_count = 0

        while (time.time() - start) < timeout:
            poll_count += 1
            elapsed = time.time() - start
            remaining = timeout - elapsed

            print(f"  GPS poll #{poll_count}  ({remaining:.0f}s remaining)")

            resp = self.send_command("AT+CGNSINF", timeout=2.0)
            fix_status, lat, lng, utc_time = self.parse_gnss_response(resp)

            if fix_status == 1 and lat is not None and lng is not None:
                elapsed_final = time.time() - start
                print(f"  Lock acquired in {elapsed_final:.1f} seconds")
                return (lat, lng, utc_time)

            print("  No fix yet...")

            if progress_callback:
                progress_callback(elapsed, timeout)

            # Wait before next poll, but check timeout
            wait_end = time.time() + poll_interval
            while time.time() < wait_end and (time.time() - start) < timeout:
                time.sleep(0.1)

        print("[A7670E] GPS TIMEOUT — No fix obtained")
        return (None, None, None)

    def parse_gnss_response(self, response):
        """
        Parse +CGNSINF response into components.
        Port of: parseGNSSInfo() in test_a7670e.ino

        Format: +CGNSINF: <run>,<fix>,<utc>,<lat>,<lon>,<alt>,<speed>,<course>,...

        Args:
            response: Raw AT response string

        Returns:
            (fix_status, lat, lng, utc_time) — fix_status=1 means valid fix
        """
        for line in response.splitlines():
            if "+CGNSINF:" not in line:
                continue

            try:
                # Extract data after "+CGNSINF: "
                data = line.split(":")[1].strip()
                fields = data.split(",")

                if len(fields) < 5:
                    return (0, None, None, None)

                # Field 0: GNSS run status
                # Field 1: Fix status (1=valid)
                fix_status = int(fields[1].strip())

                if fix_status != 1:
                    return (0, None, None, None)

                # Field 2: UTC datetime
                utc_time = fields[2].strip() if len(fields) > 2 else None

                # Field 3: Latitude
                lat = float(fields[3].strip())

                # Field 4: Longitude
                lng = float(fields[4].strip())

                # Sanity check
                if lat == 0.0 and lng == 0.0:
                    return (0, None, None, None)

                return (fix_status, lat, lng, utc_time)

            except (IndexError, ValueError) as e:
                print(f"  GNSS parse error: {e}")
                return (0, None, None, None)

        return (0, None, None, None)

    @staticmethod
    def build_map_link(lat, lng):
        """
        Build plain-text GPS coordinates string.

        NOTE: Philippine carriers (Smart/Globe) silently drop SMS
        containing URLs. We send raw coordinates instead — the
        recipient can paste them into Google Maps or any map app.

        Args:
            lat: Latitude (float)
            lng: Longitude (float)

        Returns:
            Coordinate string, e.g. "14.599512, 120.984222"
        """
        return f"{lat:.6f}, {lng:.6f}"

    # ==========================================================
    # SMS functions
    # Replaces: sendSMS() in main.ino
    # Uses: AT+CMGF=1, AT+CMGS from test_a7670e.ino
    # ==========================================================

    def send_sms(self, number, message, retries=3):
        """
        Send an SMS to a single phone number.

        Args:
            number: Phone number with country code (e.g. '+639154693904')
            message: Full SMS body text
            retries: Number of retry attempts on failure

        Returns:
            True if SMS sent successfully

        AT sequence: AT+CMGF=1 -> AT+CMGS="number" -> wait '>' -> body -> Ctrl+Z
        Maps to: sendSMS() in main.ino (lines 500-560)
        """
        for attempt in range(retries):
            try:
                # Ensure module is responsive (recovers from idle timeout)
                if not self.wake(max_attempts=3):
                    print(f"    Module unresponsive (attempt {attempt + 1}/{retries})")
                    continue

                # Set SMS text mode + GSM charset + text params
                self.send_command("AT+CMGF=1", timeout=1.0)
                self.send_command('AT+CSCS="GSM"', timeout=1.0)
                self.send_command("AT+CSMP=17,167,0,0", timeout=1.0)
                time.sleep(0.3)

                # Set recipient
                self._flush()
                cmd = f'AT+CMGS="{number}"'
                self.ser.write((cmd + "\r").encode("ascii"))
                time.sleep(0.5)

                # Wait for '>' prompt
                if not self.wait_for_prompt(timeout=5.0):
                    print(f"    No '>' prompt (attempt {attempt + 1}/{retries})")
                    self.ser.write(b"\x1B")  # ESC to cancel
                    time.sleep(1.0)
                    continue

                # Send message body
                self.ser.write(message.encode("ascii", errors="replace"))
                time.sleep(0.1)

                # Ctrl+Z to send
                self.ser.write(b"\x1A")
                time.sleep(1.0)

                # Wait for confirmation (OK or +CMGS)
                if self.wait_for("OK", timeout=15.0):
                    return True

                print(f"    No confirmation (attempt {attempt + 1}/{retries})")

            except Exception as e:
                print(f"    SMS error: {e} (attempt {attempt + 1}/{retries})")

            if attempt < retries - 1:
                time.sleep(2.0)

        return False

    def send_sms_to_contact(self, number, contact_name, map_link, owner_name,
                            sms_template, retries=3):
        """
        Build personalized emergency SMS and send to one contact.

        Args:
            number: Phone number
            contact_name: Recipient name (for personalization)
            map_link: Google Maps URL string
            owner_name: Name of device owner
            sms_template: Message template with {contact_name}, {owner_name}, {map_link}
            retries: Number of retry attempts

        Returns:
            True if sent successfully

        Maps to: sendSMS(number, contactName, mapLink) in main.ino
        """
        message = sms_template.format(
            contact_name=contact_name,
            owner_name=owner_name,
            map_link=map_link,
        )
        return self.send_sms(number, message, retries=retries)

    def send_to_all_contacts(self, contacts, map_link, owner_name, sms_template,
                             retries=3):
        """
        Send SMS to all emergency contacts.

        Args:
            contacts: List of dicts with 'name' and 'number' keys
            map_link: Google Maps URL
            owner_name: Device owner name
            sms_template: Message template string
            retries: Retries per contact

        Returns:
            True if at least one SMS succeeded

        Maps to: for-loop in executePanic() main.ino lines 329-353
        """
        any_sent = False
        total = len(contacts)

        for i, contact in enumerate(contacts):
            name = contact["name"]
            number = contact["number"]

            print(f"\n  [{i + 1}/{total}] {name} ({number})")

            if self.send_sms_to_contact(number, name, map_link, owner_name,
                                        sms_template, retries):
                print(f"      -> SMS SENT")
                any_sent = True
            else:
                print(f"      -> SMS FAILED")

        return any_sent
