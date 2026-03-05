"""
GT-U7 GPS Module Driver — NMEA Parser
=======================================
Handles serial NMEA communication with the GT-U7 (u-blox NEO-6M clone)
GPS module via the Raspberry Pi GPIO UART (/dev/serial0).

The GT-U7 is an always-on GPS receiver that continuously outputs NMEA-0183
sentences ($GPRMC, $GPGGA, etc.) at 9600 baud. No AT commands needed —
we just read and parse the stream.

Used as the backup GPS source alongside the A7670E's built-in GNSS.

Dependencies: pyserial
"""

import serial
import time


class GTU7:
    """
    Driver for GT-U7 (u-blox NEO-6M) GPS module over GPIO UART.
    Reads NMEA-0183 sentences and extracts lat/lng/time.
    """

    def __init__(self, port, baud=9600, timeout=1.0):
        """
        Store configuration. Does not open the serial port yet —
        call enable() to begin communication.

        Args:
            port: Serial port path (e.g. '/dev/serial0')
            baud: Baud rate (GT-U7 default: 9600)
            timeout: Serial read timeout in seconds
        """
        self.port = port
        self.baud = baud
        self.timeout = timeout
        self.ser = None
        self._enabled = False

    @property
    def is_enabled(self):
        """True if the serial port is open and ready."""
        return self._enabled and self.ser is not None and self.ser.is_open

    def enable(self):
        """
        Open the serial port and begin listening for NMEA data.

        Returns:
            True if the port opened successfully
        """
        if self.is_enabled:
            return True

        try:
            self.ser = serial.Serial(
                self.port, self.baud, timeout=self.timeout,
                xonxoff=False, rtscts=False, dsrdtr=False,
            )
            self._enabled = True
            print(f"[GT-U7] Opened {self.port} at {self.baud} baud")
            return True
        except serial.SerialException as e:
            print(f"[GT-U7] Serial error: {e}")
            self._enabled = False
            return False

    def disable(self):
        """Close the serial port."""
        if self.ser and self.ser.is_open:
            self.ser.close()
        self._enabled = False
        print("[GT-U7] Serial port closed")

    def close(self):
        """Alias for disable() — matches A7670E interface."""
        self.disable()

    def warmup_check(self, duration=2.0):
        """
        Check if the GT-U7 is alive by reading for NMEA sentences.

        Opens the port (if needed), reads for `duration` seconds,
        and checks whether any $GPRMC or $GPGGA sentence was received.

        Args:
            duration: Seconds to listen for NMEA data

        Returns:
            True if at least one valid NMEA sentence was detected
        """
        if not self.is_enabled:
            if not self.enable():
                return False

        self.ser.reset_input_buffer()
        deadline = time.time() + duration
        buffer = ""

        while time.time() < deadline:
            if self.ser.in_waiting:
                chunk = self.ser.read(self.ser.in_waiting).decode("ascii", errors="ignore")
                buffer += chunk

                if "$GPRMC" in buffer or "$GPGGA" in buffer:
                    return True

            time.sleep(0.05)

        return False

    def poll_fix(self):
        """
        Single non-blocking poll: read the NMEA buffer and look for a valid fix.

        Reads all available data (plus a short wait for more), extracts
        $GPRMC and $GPGGA sentences, and returns the first valid fix found.
        Prefers $GPRMC (has date+time) over $GPGGA.

        Returns:
            (lat, lng, utc_time) on success, or (None, None, None) if no fix
        """
        if not self.is_enabled:
            return (None, None, None)

        # Read everything currently in the buffer
        buffer = ""
        try:
            # Short wait to accumulate a full sentence (~1s of NMEA at 9600)
            time.sleep(0.2)
            while self.ser.in_waiting:
                chunk = self.ser.read(self.ser.in_waiting).decode("ascii", errors="ignore")
                buffer += chunk
                time.sleep(0.05)
        except serial.SerialException as e:
            print(f"[GT-U7] Read error: {e}")
            return (None, None, None)

        if not buffer:
            return (None, None, None)

        # Split into lines and process NMEA sentences
        lines = buffer.replace("\r", "").split("\n")

        # Try $GPRMC first (has date + time)
        for line in lines:
            line = line.strip()
            if line.startswith("$GPRMC") or line.startswith("$GNRMC"):
                if not _verify_checksum(line):
                    continue
                result = _parse_gprmc(line)
                if result[0] is not None:
                    return result

        # Fall back to $GPGGA
        for line in lines:
            line = line.strip()
            if line.startswith("$GPGGA") or line.startswith("$GNGGA"):
                if not _verify_checksum(line):
                    continue
                result = _parse_gpgga(line)
                if result[0] is not None:
                    return result

        return (None, None, None)


# ══════════════════════════════════════════════════════════════════════════
# NMEA Parsing Helpers (module-level)
# ══════════════════════════════════════════════════════════════════════════

def _verify_checksum(sentence):
    """
    Verify NMEA-0183 XOR checksum.

    Format: $GPRMC,...*HH
    The checksum is XOR of all bytes between '$' and '*' (exclusive).

    Args:
        sentence: Full NMEA sentence string including $ and *HH

    Returns:
        True if checksum is valid (or if sentence has no checksum)
    """
    if "*" not in sentence:
        return False

    try:
        body, checksum_str = sentence.rsplit("*", 1)
        body = body.lstrip("$")
        checksum_str = checksum_str.strip()

        if len(checksum_str) < 2:
            return False

        expected = int(checksum_str[:2], 16)
        computed = 0
        for ch in body:
            computed ^= ord(ch)

        return computed == expected
    except (ValueError, IndexError):
        return False


def _nmea_to_decimal(raw, hemisphere):
    """
    Convert NMEA coordinate (DDMM.MMMMMM or DDDMM.MMMMMM) to decimal degrees.

    Examples:
        1435.9707, 'N' → 14.599512
        12059.0533, 'E' → 120.984222

    Args:
        raw: Float NMEA coordinate value
        hemisphere: 'N', 'S', 'E', or 'W'

    Returns:
        Decimal degrees (float), negative for S/W
    """
    degrees = int(raw / 100)
    minutes = raw - degrees * 100
    decimal = degrees + minutes / 60.0

    if hemisphere in ("S", "W"):
        decimal = -decimal

    return decimal


def _parse_gprmc(sentence):
    """
    Parse $GPRMC sentence for position and time.

    Format:
      $GPRMC,HHMMSS.SS,A,DDMM.MMMM,N,DDDMM.MMMM,E,speed,course,DDMMYY,,,mode*CS
             [1]       [2][3]       [4][5]         [6]                [9]

    Field 2: A=Active (valid fix), V=Void (no fix)

    Returns:
        (lat, lng, utc_time) or (None, None, None)
    """
    try:
        # Strip checksum for field splitting
        data = sentence.split("*")[0]
        fields = data.split(",")

        if len(fields) < 10:
            return (None, None, None)

        status = fields[2].strip()
        if status != "A":
            return (None, None, None)

        lat_str = fields[3].strip()
        lat_hem = fields[4].strip()
        lng_str = fields[5].strip()
        lng_hem = fields[6].strip()

        if not lat_str or not lng_str:
            return (None, None, None)

        lat = _nmea_to_decimal(float(lat_str), lat_hem)
        lng = _nmea_to_decimal(float(lng_str), lng_hem)

        # Sanity check — reject 0,0
        if lat == 0.0 and lng == 0.0:
            return (None, None, None)

        # Build UTC time string from HHMMSS.SS + DDMMYY
        utc_raw = fields[1].strip()
        date_raw = fields[9].strip()
        utc_time = None
        if utc_raw and date_raw and len(utc_raw) >= 6 and len(date_raw) >= 6:
            utc_time = (f"{date_raw[4:6]}/{date_raw[2:4]}/{date_raw[0:2]} "
                        f"{utc_raw[0:2]}:{utc_raw[2:4]}:{utc_raw[4:6]} UTC")

        return (lat, lng, utc_time)

    except (IndexError, ValueError) as e:
        print(f"  [GT-U7] GPRMC parse error: {e}")
        return (None, None, None)


def _parse_gpgga(sentence):
    """
    Parse $GPGGA sentence for position and time.

    Format:
      $GPGGA,HHMMSS.SS,DDMM.MMMM,N,DDDMM.MMMM,E,Q,numSV,HDOP,alt,M,...*CS
             [1]       [2]       [3][4]         [5][6]

    Field 6: 0=no fix, 1=GPS fix, 2=DGPS fix

    Returns:
        (lat, lng, utc_time) or (None, None, None)
    """
    try:
        data = sentence.split("*")[0]
        fields = data.split(",")

        if len(fields) < 7:
            return (None, None, None)

        fix_quality = fields[6].strip()
        if fix_quality == "0" or not fix_quality:
            return (None, None, None)

        lat_str = fields[2].strip()
        lat_hem = fields[3].strip()
        lng_str = fields[4].strip()
        lng_hem = fields[5].strip()

        if not lat_str or not lng_str:
            return (None, None, None)

        lat = _nmea_to_decimal(float(lat_str), lat_hem)
        lng = _nmea_to_decimal(float(lng_str), lng_hem)

        if lat == 0.0 and lng == 0.0:
            return (None, None, None)

        # GGA only has time, no date
        utc_raw = fields[1].strip()
        utc_time = None
        if utc_raw and len(utc_raw) >= 6:
            utc_time = f"{utc_raw[0:2]}:{utc_raw[2:4]}:{utc_raw[4:6]} UTC"

        return (lat, lng, utc_time)

    except (IndexError, ValueError) as e:
        print(f"  [GT-U7] GPGGA parse error: {e}")
        return (None, None, None)
