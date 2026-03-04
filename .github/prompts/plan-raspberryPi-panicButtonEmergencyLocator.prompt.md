# Panic Button Emergency Locator — Raspberry Pi + A7670E

## Conversion Plan: Arduino Nano → Raspberry Pi

---

## 1. System Overview

The Panic Button Emergency Locator is being converted from an **Arduino Nano** (C++/SoftwareSerial) to a **Raspberry Pi** (Python/GPIO) platform.

**Key change:** The SIM800L GSM module and separate GPS (GTU-7) module are **replaced by a single SIMCOM A7670E** module, which provides both **LTE Cat-1 SMS** and **built-in GNSS (GPS)** via AT commands over UART.

When the panic button is pressed:

1. System validates button press (debounced, 3-second hold-to-arm).
2. A7670E GNSS retrieves real-time latitude and longitude via `AT+CGNSINF`.
3. Coordinates are processed into a Google Maps link.
4. SMS containing the emergency alert and location link is sent to predefined emergency contacts via A7670E `AT+CMGS`.
5. Event details (date, time, coordinates, status) are logged to a local file on the Pi's filesystem.
6. Buzzer (via relay) and LEDs provide confirmation feedback.
7. Error handling manages failures (GNSS timeout, SMS failure, file write failure).

---

## 2. Hardware Changes Summary

| Component         | Arduino Version         | Raspberry Pi Version                     |
| ----------------- | ----------------------- | ---------------------------------------- |
| Microcontroller   | Arduino Nano (ATmega328P) | Raspberry Pi (any model with GPIO)     |
| GSM Module        | SIM800L (2G)            | **A7670E** (LTE Cat-1, SMS + GNSS)      |
| GPS Module        | GTU-7 (separate)        | **A7670E built-in GNSS** (no separate GPS) |
| Communication     | SoftwareSerial          | Hardware UART (`/dev/serial0`)           |
| SD Card Logging   | SD card via SPI         | **Local filesystem** (file on Pi SD card) |
| Programming       | Arduino C++ (.ino)      | **Python 3** (RPi.GPIO / gpiozero)      |
| Power             | 7.4V Li-ion → VIN       | 5V via USB-C or regulated supply        |

---

## 3. GPIO Pin Configuration

### Raspberry Pi GPIO Map

| GPIO | BCM Pin | Component        | Function                                 |
| ---- | ------- | ---------------- | ---------------------------------------- |
| 14   | GPIO 14 | A7670E TX (UART) | Pi TXD → A7670E RXD (serial transmit)   |
| 15   | GPIO 15 | A7670E RX (UART) | Pi RXD ← A7670E TXD (serial receive)    |
| 17   | GPIO 17 | Green LED        | Success / status indicator               |
| 18   | GPIO 18 | Relay Module     | Controls active buzzer (Active LOW)      |
| 27   | GPIO 27 | Red LED          | Error / arming indicator                 |
| 22   | GPIO 22 | Push Button      | Panic trigger (GPIO TBD, with pull-up)   |

> **Note:** The push button GPIO pin needs to be assigned. Suggested: **GPIO 22** or **GPIO 23** (free pins, easy to wire). The user should confirm which GPIO they want for the button.

### UART Configuration

- **GPIO 14 (TXD)** and **GPIO 15 (RXD)** are the Pi's hardware UART pins
- Must **disable Bluetooth serial** on Pi 3/4/5 to free `/dev/serial0` for A7670E
- Add to `/boot/config.txt`:
  ```
  dtoverlay=disable-bt
  enable_uart=1
  ```
- Remove `console=serial0,115200` from `/boot/cmdline.txt` if present

---

## 4. Wiring Summary

### A7670E Module (UART — SMS + GPS)

| A7670E Pin | Connect To        | Notes                                  |
| ---------- | ----------------- | -------------------------------------- |
| TXD        | GPIO 15 (Pi RXD)  | A7670E sends data to Pi               |
| RXD        | GPIO 14 (Pi TXD)  | Pi sends AT commands to A7670E         |
| GND        | Pi GND             | Common ground                          |
| VCC / 5V   | 5V 2A supply       | **NOT from Pi 5V pin** — use dedicated supply |

> A7670E requires stable 5V 2A. Use a dedicated power supply, not the Pi's GPIO 5V pin.

### Relay Module (Buzzer)

| Relay Pin  | Connect To   | Notes           |
| ---------- | ------------ | --------------- |
| VCC        | 5V           | Power           |
| GND        | Pi GND       | Common ground   |
| IN         | GPIO 18      | Active LOW      |

### Green LED

| LED Pin    | Connect To   | Notes                      |
| ---------- | ------------ | -------------------------- |
| Anode (+)  | GPIO 17      | Via 220Ω–330Ω resistor     |
| Cathode (−)| Pi GND       | Common ground              |

### Red LED

| LED Pin    | Connect To   | Notes                      |
| ---------- | ------------ | -------------------------- |
| Anode (+)  | GPIO 27      | Via 220Ω–330Ω resistor     |
| Cathode (−)| Pi GND       | Common ground              |

### Push Button

| Button Pin | Connect To          | Notes                              |
| ---------- | ------------------- | ---------------------------------- |
| One side   | GPIO (TBD, e.g. 22) | With internal pull-up enabled     |
| Other side | Pi GND              | Press = LOW                        |

---

## 5. Software Architecture

### Language: Python 3

### Dependencies

| Library          | Purpose                                |
| ---------------- | -------------------------------------- |
| `RPi.GPIO`       | GPIO control (LEDs, relay, button)     |
| `pyserial`       | UART communication with A7670E         |
| `time`           | Delays, timestamps                     |
| `datetime`       | Log timestamps                         |
| `os`             | File I/O for logging                   |
| `threading`      | Non-blocking LED blink patterns        |

### File Structure (Proposed)

```
main/
  main.py              # Main application entry point + loop
  config.py            # User configuration (contacts, pins, timeouts)
  a7670e.py            # A7670E driver (AT commands for SMS + GNSS)
  buzzer.py            # Relay/buzzer helper functions
  led.py               # LED control helpers
  logger.py            # File-based logging (replaces SD card)
  panic.py             # Panic sequence state machine (4 phases)
tests/
  test_a7670e.py       # A7670E module diagnostics
  test_buzzer_relay.py # Relay/buzzer test
  test_led.py          # LED test
```

---

## 5A. Detailed Module Specifications

Each module below maps directly to the logic in the Arduino `main.ino`.

---

### `config.py` — User Configuration

All user-configurable constants in one place. Equivalent to the `USER CONFIGURATION`, `PIN CONFIGURATION`, and `TIMING CONSTANTS` sections at the top of `main.ino`.

```python
# --- Owner ---
OWNER_NAME = "Charles"

# --- Emergency Contacts ---
CONTACTS = [
    {"name": "Andrew Felipe", "number": "+639154693904"},
    {"name": "Naig",          "number": "+639391445673"},
]

# --- GPIO Pins (BCM numbering) ---
PIN_GREEN_LED = 17
PIN_RED_LED   = 27
PIN_RELAY     = 18      # Active LOW — buzzer
PIN_BUTTON    = 22      # User to confirm

# --- A7670E UART ---
SERIAL_PORT = "/dev/serial0"
SERIAL_BAUD = 115200    # Primary baud (fallback to 9600)

# --- Timeouts ---
GPS_TIMEOUT      = 30   # seconds
ARM_HOLD_TIME    = 3.0  # seconds
CANCEL_WINDOW    = 3.0  # seconds
SMS_RETRY_COUNT  = 3
DEBOUNCE_DELAY   = 0.05 # seconds (50ms)

# --- Logging ---
LOG_FILE = "logs.txt"
```

---

### `a7670e.py` — A7670E Driver (SMS + GNSS)

Replaces **both** `initGSM()`, `sendSMS()`, `waitForResponse()` (GSM functions) **and** `acquireGPS()`, `buildMapLink()` (GPS functions) from `main.ino`. Uses the AT command patterns from `tests/test_a7670e/test_a7670e.ino`.

```python
class A7670E:
    """
    Driver for SIMCOM A7670E LTE Cat-1 module.
    Handles: module init, GNSS (GPS), and SMS over a single UART.
    """

    def __init__(self, port, baud):
        """Open serial connection to A7670E.
        Try primary baud, fallback to 9600 if no response.
        Equivalent to: baud detection in test_a7670e.ino setup()
        """

    # --- Low-level AT helpers ---
    # Equivalent to: waitForResponse() and gsmSerial read logic in main.ino

    def send_command(self, cmd, timeout=2.0) -> str:
        """Send AT command, return full response string."""

    def wait_for(self, expected, timeout=2.0) -> bool:
        """Wait for expected substring in response. 
        Direct port of: waitForResponse(expected, timeout) in main.ino"""

    def wait_for_prompt(self, timeout=5.0) -> bool:
        """Wait for '>' prompt (used before SMS body).
        Port of: waitForPrompt() in test_a7670e.ino"""

    # --- Module initialization ---
    # Equivalent to: initGSM() in main.ino + Test 1-6 in test_a7670e.ino

    def init_module(self) -> bool:
        """Initialize A7670E: AT, ATE0, check SIM, signal, registration.
        Returns True if module is ready.
        Maps to: initGSM() in main.ino
        AT commands: AT, ATE0, AT+CPIN?, AT+CSQ, AT+CREG?, AT+COPS?
        """

    def check_sim(self) -> str:
        """Check SIM status. Returns 'READY', 'PIN', 'PUK', 'NOT INSERTED'.
        Maps to: checkSIMStatus() in test_a7670e.ino"""

    def get_signal_quality(self) -> int:
        """Get RSSI value (0-31, 99=unknown).
        Maps to: checkSignal() in test_a7670e.ino"""

    def check_registration(self) -> str:
        """Check network registration status.
        Maps to: checkRegistration() in test_a7670e.ino
        Returns: 'home', 'roaming', 'searching', 'denied', 'unknown'
        """

    # --- GNSS (GPS) functions ---
    # Replaces: acquireGPS(), buildMapLink() in main.ino
    # Uses AT commands from test_a7670e.ino: AT+CGNSPWR=1, AT+CGNSINF

    def enable_gnss(self) -> bool:
        """Power on GNSS engine: AT+CGNSPWR=1
        Maps to: Test 7 in test_a7670e.ino"""

    def acquire_gps(self, timeout=30) -> tuple:
        """Poll AT+CGNSINF until valid fix or timeout.
        Returns (lat, lng) or (None, None) on timeout.
        Maps to: acquireGPS(float* lat, float* lng) in main.ino
                 waitForGPSFix() + parseGNSSInfo() in test_a7670e.ino
        Prints progress every 5 seconds (satellite count, elapsed time).
        Equivalent progress reporting to main.ino lines 406-450.
        """

    def parse_gnss_response(self, response) -> tuple:
        """Parse +CGNSINF response → (fix_status, lat, lng, utc_time).
        Port of: parseGNSSInfo() in test_a7670e.ino
        Format: +CGNSINF: <run>,<fix>,<utc>,<lat>,<lon>,...
        """

    @staticmethod
    def build_map_link(lat, lng) -> str:
        """Build Google Maps URL from coordinates.
        Returns: 'https://maps.google.com/?q=LAT,LNG'
        Port of: buildMapLink() in main.ino / buildMapsLink() in test_a7670e.ino
        """

    # --- SMS functions ---
    # Replaces: sendSMS() in main.ino
    # Uses AT commands from test_a7670e.ino: AT+CMGF=1, AT+CMGS

    def send_sms(self, number, contact_name, map_link, owner_name, retries=3) -> bool:
        """Send personalized emergency SMS to one contact.
        Retry up to `retries` times on failure.
        Maps to: sendSMS(number, contactName, mapLink) in main.ino
        
        Message body (same as main.ino):
            EMERGENCY ALERT!
            Hey {contact_name}, I'm letting you know that the emergency
            panic button has been pressed by {owner_name}.
            ...Google Maps link...
            Please respond immediately and check on her safety.
        
        AT sequence: AT+CMGF=1 → AT+CMGS="number" → wait '>' → body → Ctrl+Z
        """

    def send_to_all_contacts(self, contacts, map_link, owner_name) -> bool:
        """Send SMS to all emergency contacts. Return True if at least one succeeded.
        Maps to: the for-loop in executePanic() main.ino lines 329-353
        """
```

---

### `buzzer.py` — Relay/Buzzer Helpers

Direct port of the `BUZZER HELPERS` section in `main.ino` (lines 86-112). Controls the relay on GPIO 18 (Active LOW).

```python
import RPi.GPIO as GPIO
import time
from config import PIN_RELAY

def setup():
    """Initialize relay pin as output, buzzer OFF.
    Maps to: pinMode(RELAY_PIN, OUTPUT); buzzerOff(); in main.ino setup()"""

def buzzer_on():
    """Activate buzzer (relay LOW). Port of: buzzerOn() in main.ino"""

def buzzer_off():
    """Deactivate buzzer (relay HIGH). Port of: buzzerOff() in main.ino"""

def tick():
    """Short 50ms beep. Port of: buzzerTick() in main.ino"""

def double_beep():
    """Two 100ms beeps with 100ms gap. Port of: buzzerDoubleBeep() in main.ino"""

def cancel_sound():
    """Two 400ms beeps with 150ms gap. Port of: buzzerCancelSound() in main.ino"""

def success_sound():
    """200ms beep + 100ms pause + 500ms beep. Port of: buzzerSuccessSound() in main.ino"""

def fail_sound():
    """Single 800ms buzz. Port of: buzzerFailSound() in main.ino"""
```

---

### `led.py` — LED Control Helpers

Manages Green (GPIO 17) and Red (GPIO 27) LEDs. Equivalent to the `digitalWrite(GREEN_LED, ...)` / `digitalWrite(RED_LED, ...)` calls throughout `main.ino`. Adds threading support for non-blocking blink patterns.

```python
import RPi.GPIO as GPIO
import threading
import time
from config import PIN_GREEN_LED, PIN_RED_LED

def setup():
    """Initialize LED pins as output, both OFF.
    Maps to: pinMode(GREEN_LED, OUTPUT); pinMode(RED_LED, OUTPUT); in main.ino setup()"""

def green_on():
    """Turn green LED on."""

def green_off():
    """Turn green LED off."""

def red_on():
    """Turn red LED on."""

def red_off():
    """Turn red LED off."""

def all_off():
    """Turn both LEDs off + stop any blink threads.
    Port of: allOff() in main.ino (LED portion)"""

def blink_red(interval=0.2):
    """Start non-blocking rapid red LED blink (background thread).
    Used during Phase 1 arming: main.ino line 189
    interval=0.2 → every 200ms"""

def blink_green(interval=0.5):
    """Start non-blocking slow green LED blink (background thread).
    Used during Phase 3 cancel window: main.ino line 222
    interval=0.5 → every 500ms"""

def blink_green_fast(interval=0.3):
    """Start non-blocking green blink for GPS wait.
    Used during GPS acquisition: main.ino line 449
    interval=0.3 → every 300ms"""

def stop_blink():
    """Stop any running blink thread."""
```

---

### `logger.py` — File-Based Logging

Replaces the `SD CARD LOGGING` section in `main.ino` (lines 598-663). Writes to local filesystem instead of SPI SD card.

```python
import os
from datetime import datetime
from config import LOG_FILE

def log_event(status, lat=0.0, lng=0.0, utc_time=None):
    """Write a log entry to LOG_FILE.
    
    Direct port of: logToSD(status, lat, lng) in main.ino
    
    Format (same as main.ino):
        --------------------------------
        [2026-03-04 12:30:45]
        Latitude:  14.599512
        Longitude: 120.984222
        Status:    SUCCESS
        --------------------------------
    
    Uses datetime (from GPS UTC if available, else system time).
    Replaces: GPS timestamp logic in main.ino lines 610-640
    
    On write failure: print warning, blink red LED 3 times.
    Maps to: SD write failure handling in main.ino lines 603-608
    """
```

---

### `panic.py` — Panic Sequence State Machine

The core logic. Direct port of `handlePanicSequence()` and `executePanic()` from `main.ino`. This is the largest module — it orchestrates all other modules.

```python
from config import *
from a7670e import A7670E
import buzzer
import led
import logger
import RPi.GPIO as GPIO
import time

def handle_panic_sequence(modem: A7670E):
    """Full 4-phase panic sequence. 
    Direct port of: handlePanicSequence() in main.ino (lines 160-260)
    
    Phase 1 — Hold to Arm (3 seconds)
        - Read button state in loop
        - Red LED blink fast (via led.blink_red(0.2))
        - Buzzer tick once per second (buzzer.tick() × 3)
        - If released early → return (cancelled)
        Maps to: main.ino lines 170-205
    
    Phase 2 — Armed Confirmation
        - Both LEDs flash + buzzer double beep
        - Wait for button release
        Maps to: main.ino lines 209-220
    
    Phase 3 — Cancellation Window (3 seconds)
        - Green LED blink slow (via led.blink_green(0.5))
        - Check for button press to cancel
        - If cancelled: red LED + cancel sound + log "CANCELLED"
        Maps to: main.ino lines 224-252
    
    Phase 4 — Execute panic
        - Calls execute_panic(modem)
        Maps to: main.ino lines 254-260
    """

def execute_panic(modem: A7670E):
    """Execute the full panic routine: GPS → SMS → Log → Feedback.
    Direct port of: executePanic() in main.ino (lines 266-375)
    
    Step 1/4: GNSS Acquisition
        - modem.enable_gnss()
        - lat, lng = modem.acquire_gps(timeout=GPS_TIMEOUT)
        - Green LED blinks while searching
        - If timeout → red LED + fail sound + log + return
        Maps to: main.ino lines 275-314
    
    Step 2/4: SMS Transmission
        - map_link = A7670E.build_map_link(lat, lng)
        - Loop through CONTACTS, call modem.send_sms() for each
        - Track if at least one SMS succeeded
        Maps to: main.ino lines 316-355
    
    Step 3/4: File Logging
        - logger.log_event("SUCCESS" or "FAILED — SMS Send Error", lat, lng)
        Maps to: main.ino lines 357-366
    
    Step 4/4: Final Feedback
        - Success: green LED + buzzer.success_sound()
        - Failure: red LED + buzzer.fail_sound()
        - Then all off → idle
        Maps to: main.ino lines 368-393
    """
```

---

### `main.py` — Application Entry Point

Equivalent to `setup()` and `loop()` in `main.ino`.

```python
#!/usr/bin/env python3
"""
Panic Button Emergency Locator — Raspberry Pi + A7670E
Main entry point.

Port of: main.ino setup() + loop()
"""

import RPi.GPIO as GPIO
import time
from config import *
from a7670e import A7670E
import buzzer
import led
import panic

def setup() -> A7670E:
    """Initialize all hardware. 
    Port of: setup() in main.ino (lines 118-150)
    
    1. Set GPIO mode (BCM)
    2. Configure button pin with pull-up
       Maps to: pinMode(BTN_PIN, INPUT_PULLUP)
    3. Initialize buzzer (relay pin)
       Maps to: buzzer setup in main.ino
    4. Initialize LEDs
       Maps to: LED setup in main.ino  
    5. All outputs off
       Maps to: allOff() in main.ino
    6. Print startup banner
       Maps to: Serial.println("Panic Button Emergency Locator") in main.ino
    7. Initialize A7670E modem (UART connection + AT init)
       Maps to: gsmSerial.begin() + initGSM() in main.ino
       Also replaces: gpsSerial.begin() since A7670E handles GPS too
    8. Print "System Ready. Hold button 3s to arm."
    
    Returns: initialized A7670E instance
    """

def loop(modem: A7670E):
    """Main loop — poll button, trigger panic sequence.
    Port of: loop() in main.ino (lines 156-163)
    
    - Read button GPIO (with pull-up, pressed = LOW)
    - Debounce (50ms)
    - If still pressed → panic.handle_panic_sequence(modem)
    - Small delay between polls (10ms)
    """

def main():
    """Entry point. Calls setup() then loops forever.
    Wraps in try/finally for GPIO.cleanup() on exit."""

if __name__ == "__main__":
    main()
```

---

### Test Files

#### `tests/test_a7670e.py`

Port of `tests/test_a7670e/test_a7670e.ino`. Runs all 9 diagnostic tests:

```python
"""
A7670E Diagnostic Test — Port of tests/test_a7670e/test_a7670e.ino

Tests:
  1. Basic AT command (baud detection: 115200 → 9600 fallback)
  2. Module identification (ATI)
  3. SIM card status (AT+CPIN?)
  4. Signal quality (AT+CSQ) — with RSSI interpretation
  5. Network registration (AT+CREG?)
  6. Network operator (AT+COPS?)
  7. Enable GNSS (AT+CGNSPWR=1)
  8. Acquire GPS fix (poll AT+CGNSINF with timeout)
  9. Send SMS with Google Maps location link

Interactive mode after tests: type AT commands, 'gps', 'sms', 'signal'
"""
```

#### `tests/test_buzzer_relay.py`

Port of `tests/test_buzzer_relay/test_buzzer_relay.ino`:

```python
"""
Buzzer Relay Test — Port of tests/test_buzzer_relay/test_buzzer_relay.ino

Tests:
  1. Short beep (200ms)
  2. Long beep (800ms)
  3. Double beep (100ms + gap + 100ms)
  4. Short-Long pattern (success sound)
  5. Cancel pattern (400ms + gap + 400ms)
"""
```

#### `tests/test_led.py`

Port of `tests/test_led/test_led.ino`:

```python
"""
LED Test — Port of tests/test_led/test_led.ino

Tests:
  1. Green LED ON (1s)
  2. Red LED ON (1s)
  3. Both ON (1s)
  4. Both OFF (1s)
  5. Green rapid blink (5×)
  6. Red rapid blink (5×)
  7. Alternating blink
"""
```

---

## 6. A7670E AT Command Reference

Based on the existing Arduino test code in `tests/test_a7670e/test_a7670e.ino`:

### Module Initialization

```
AT                  → Check module alive
ATE0                → Disable echo
ATI                 → Module identification
AT+CPIN?            → SIM card status (expect "READY")
AT+CSQ              → Signal quality (RSSI 0-31, 99=unknown)
AT+CREG?            → Network registration (0,1=home, 0,5=roaming)
AT+COPS?            → Current operator
```

### GNSS (GPS) — Replaces separate GPS module

```
AT+CGNSPWR=1        → Power on GNSS engine
AT+CGNSINF          → Query GNSS navigation info
```

**Response format:**

```
+CGNSINF: <run>,<fix>,<utc>,<lat>,<lon>,<alt>,<speed>,<course>,...
```

- `fix = 1` means valid GPS fix
- Parse fields 4 (latitude) and 5 (longitude)
- Example: `+CGNSINF: 1,1,20260304120000.000,14.599512,120.984222,45.0,0.0,0.0,...`

### SMS Sending

```
AT+CMGF=1           → Set SMS text mode
AT+CMGS="<number>"  → Start SMS (wait for '>' prompt)
<message body>      → Type message
Ctrl+Z (0x1A)       → Send the SMS
```

---

## 7. Core Functional Workflow

*(Matching the original Arduino plan — same 4-phase panic sequence)*

### Phase 1 — Hold to Arm (3 seconds)

- User presses and **holds** the button
- During the hold:
  - Red LED (GPIO 27) blinks rapidly (every 200ms)
  - Buzzer (GPIO 18 relay) gives 3 short ticks (one per second)
- If released early → reset to idle, no action

### Phase 2 — Armed Confirmation

- After 3-second hold complete:
  - Buzzer double-beep (short-short)
  - Both Green (GPIO 17) + Red (GPIO 27) LEDs flash together once
  - Print: "Armed! Press button within 3s to cancel"

### Phase 3 — Cancellation Window (3 seconds)

- Green LED blinks slowly (every 500ms)
- User can press button once to cancel
- If cancelled:
  - Red LED solid 1 second
  - Buzzer 2 long beeps (400ms each)
  - Log "CANCELLED"
  - Return to idle
- If not cancelled → proceed to Phase 4

### Phase 4 — Panic Execution

1. **GNSS Acquisition** — `AT+CGNSPWR=1` then poll `AT+CGNSINF` until fix (timeout 30s)
2. **Build Google Maps link** — `https://maps.google.com/?q=LAT,LNG`
3. **Send SMS** to all emergency contacts via `AT+CMGS` (retry up to 3 times per contact)
4. **Log to file** — Write event to `logs.txt` on Pi filesystem
5. **Feedback** — Success (green LED + short-long beep) or Failure (red LED + long buzz)

---

## 8. SMS Message Format

Personalized per contact (matching current Arduino implementation):

```
EMERGENCY ALERT!

Hey {contact_name}, I'm letting you know that the emergency panic button has been pressed by {owner_name}.

I've got her location from the GPS device. Here is the Google Maps link:

https://maps.google.com/?q=LAT,LNG

Please respond immediately and check on her safety.
```

---

## 9. Log File Format

File: `logs.txt` (on Pi filesystem, e.g. `/home/pi/PEL/logs.txt`)

```
--------------------------------
[2026-03-04 12:30:45]
Latitude:  14.599512
Longitude: 120.984222
Status:    SUCCESS
--------------------------------
```

On failure:

```
--------------------------------
[2026-03-04 12:30:45]
Latitude:  0.000000
Longitude: 0.000000
Status:    FAILED — GNSS Timeout
--------------------------------
```

---

## 10. Error Handling

### GNSS Timeout (30 seconds)

- Red LED ON
- Long buzzer alert (800ms)
- Log error
- Do NOT send SMS (no location to share)

### SMS Failure

- Retry up to 3 times per contact
- If all retries fail:
  - Log failure
  - Red LED ON
  - Long buzzer alert

### File Write Failure

- Continue with SMS (non-critical)
- Print warning to console
- Blink red LED 3 times

### A7670E Not Responding

- Check baud rate (try 115200 first, fallback to 9600 — per test code pattern)
- If no response at either baud → halt with error indication

### Network Not Registered

- Check with `AT+CREG?`
- Wait/retry before sending SMS

---

## 11. System Feedback Patterns

*(Same as original Arduino design)*

| State                 | Green LED (GPIO 17) | Red LED (GPIO 27) | Buzzer (GPIO 18 relay) |
| --------------------- | ------------------- | ------------------ | ---------------------- |
| Idle                  | OFF                 | OFF                | OFF                    |
| Arming (3s hold)      | OFF                 | Blink fast (200ms) | 1 tick/sec (3 total)   |
| Armed confirmation    | Flash once          | Flash once         | Double beep            |
| Cancel window (3s)    | Blink slow (500ms)  | OFF                | —                      |
| Cancelled             | OFF                 | Solid 1s           | 2 long beeps (400ms)   |
| Executing (GPS wait)  | Blink (300ms)       | OFF                | —                      |
| Success               | Solid ON            | OFF                | Short-long beep        |
| Failure               | OFF                 | Solid ON           | Long buzz (800ms)      |

---

## 12. User Configuration (config.py)

```python
# --- Owner ---
OWNER_NAME = "Charles"

# --- Emergency Contacts ---
CONTACTS = [
    {"name": "Andrew Felipe", "number": "+639154693904"},
    {"name": "Naig",          "number": "+639391445673"},
]

# --- GPIO Pins (BCM numbering) ---
PIN_GREEN_LED = 17
PIN_RED_LED   = 27
PIN_RELAY     = 18      # Active LOW — buzzer
PIN_BUTTON    = 22      # TBD — user to confirm

# --- A7670E UART ---
SERIAL_PORT = "/dev/serial0"
SERIAL_BAUD = 115200    # Try 115200 first, fallback to 9600

# --- Timeouts ---
GPS_TIMEOUT      = 30   # seconds
ARM_HOLD_TIME    = 3    # seconds
CANCEL_WINDOW    = 3    # seconds
SMS_RETRY_COUNT  = 3
DEBOUNCE_DELAY   = 0.05 # seconds (50ms)

# --- Logging ---
LOG_FILE = "logs.txt"
```

---

## 13. Key Differences from Arduino Version

| Aspect               | Arduino Nano                        | Raspberry Pi                          |
| --------------------- | ----------------------------------- | ------------------------------------- |
| Language              | C++ (.ino)                          | Python 3 (.py)                        |
| Serial                | SoftwareSerial (bit-banged)         | Hardware UART (`/dev/serial0`)        |
| GPS                   | Separate GTU-7 via SoftwareSerial   | A7670E built-in GNSS (AT commands)    |
| GSM                   | SIM800L (2G) via SoftwareSerial     | A7670E (LTE Cat-1) via UART          |
| SD Card               | SPI SD card module                  | Local filesystem on Pi SD card        |
| Multitasking          | Single-threaded (blocking)          | Can use threads for LED blink         |
| GPIO library          | `digitalWrite()` / `digitalRead()`  | `RPi.GPIO` or `gpiozero`             |
| Baud rate             | 9600 (SIM800L)                      | 115200 (A7670E default, fallback 9600)|
| No separate GPS wiring | 2 extra pins (D2, D3)             | Eliminated — A7670E handles GPS       |
| No SD SPI wiring      | 4 SPI pins (D10-D13)               | Eliminated — use filesystem           |

---

## 14. Raspberry Pi Setup Requirements

### Enable UART

```bash
sudo raspi-config
# Interface Options → Serial Port
# Login shell over serial: NO
# Serial port hardware enabled: YES
```

Or manually in `/boot/config.txt`:

```
enable_uart=1
dtoverlay=disable-bt
```

### Install Python Dependencies

```bash
pip install pyserial RPi.GPIO
```

### Auto-Start on Boot (Optional)

Create a systemd service so the panic button script runs on boot:

```bash
sudo nano /etc/systemd/system/pel.service
```

```ini
[Unit]
Description=Panic Emergency Locator
After=multi-user.target

[Service]
ExecStart=/usr/bin/python3 /home/pi/PEL/main/main.py
WorkingDirectory=/home/pi/PEL/main
Restart=always
User=pi

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable pel.service
sudo systemctl start pel.service
```

---

## 15. Migration Steps

1. **Create plan** (this document) — review before implementation
2. **Set up Raspberry Pi** — enable UART, install dependencies
3. **Port A7670E driver** — translate `test_a7670e.ino` AT command logic to Python class
4. **Port GPIO helpers** — buzzer, LED, button (translate from Arduino `digitalWrite` to `RPi.GPIO`)
5. **Port panic sequence** — translate `main.ino` state machine to Python
6. **Port logging** — replace SD card SPI with filesystem writes
7. **Create config module** — extract all user-configurable values
8. **Write test scripts** — Python versions of each Arduino test
9. **Integration test** — full end-to-end panic sequence
10. **Deploy** — auto-start service, enclosure, field test

---

## 16. Open Questions for User

- [ ] **Button GPIO pin** — Which GPIO for the push button? (Suggested: GPIO 22)
- [ ] **Raspberry Pi model** — Which Pi model? (Pi 3B+, Pi 4, Pi Zero 2W, Pi 5?)
- [ ] **A7670E baud rate** — Confirmed working at 115200 or 9600?
- [ ] **Power supply** — Battery-powered or wall-powered? If battery, what voltage/capacity?
- [ ] **Relay logic** — Still Active LOW for the relay on GPIO 18?
