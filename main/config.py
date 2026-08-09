"""
Panic Button Emergency Locator - Configuration
================================================
Hardware constants live here. Private owner and contact details are loaded from an
untracked JSON deployment file.

Port of: USER CONFIGURATION, PIN CONFIGURATION, TIMING CONSTANTS
         sections in main.ino (lines 14-78)
"""

import json
import os
from pathlib import Path

# ==============================================================
# OWNER INFORMATION
# ==============================================================

OWNER_NAME = os.getenv("PEL_OWNER_NAME", "PEL Device")

# ==============================================================
# EMERGENCY CONTACTS
# Copy config/contacts.example.json to config/contacts.json and edit it locally.
# Override the location with PEL_CONTACTS_FILE when deploying through systemd.
# ==============================================================

_DEFAULT_CONTACTS_FILE = Path(__file__).resolve().parents[1] / "config" / "contacts.json"
PEL_CONTACTS_FILE = Path(os.getenv("PEL_CONTACTS_FILE", _DEFAULT_CONTACTS_FILE))


def _load_contacts(path):
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("PEL contacts file must contain a JSON array")
    contacts = []
    for index, contact in enumerate(data, start=1):
        if not isinstance(contact, dict):
            raise ValueError(f"PEL contact {index} must be an object")
        name = str(contact.get("name", "")).strip()
        number = str(contact.get("number", "")).strip()
        if not name or not number.startswith("+") or not number[1:].isdigit():
            raise ValueError(f"PEL contact {index} must have a name and E.164 number")
        contacts.append({"name": name, "number": number})
    return contacts


CONTACTS = _load_contacts(PEL_CONTACTS_FILE)

# ==============================================================
# SMS MESSAGE TEMPLATE
# Available placeholders: {contact_name}, {owner_name}, {map_link}
# ==============================================================

SMS_TEMPLATE = (
    "EMERGENCY! {owner_name} pressed the panic button.\n"
    "{contact_name}, please check on them immediately.\n\n"
    "GPS: {map_link}\n"
    "(Paste into Google Maps)"
)
# Filled example (147 chars):
# EMERGENCY! PEL Device pressed the panic button.
# Primary Contact, please check on them immediately.
# GPS: 14.599512, 120.984222
# (Paste into Google Maps)

# ==============================================================
# GPIO PIN CONFIGURATION (BCM numbering)
# Match these to your physical wiring.
# ==============================================================

PIN_GREEN_LED = 17      # Green LED anode (via 220-330 ohm resistor)
PIN_RED_LED   = 27      # Red LED anode (via 220-330 ohm resistor)
PIN_RELAY     = 18      # Relay module IN pin (Active LOW -- buzzer)
PIN_BUTTON    = 22      # Push button (internal pull-up, press = LOW)
PIN_PWRKEY    = 4       # A7670E PWRKEY pin (pulse LOW 1.5s to power on)

# ==============================================================
# A7670E SERIAL CONFIGURATION
# ==============================================================
# Connection method: "usb" or "gpio"
#   usb  — A7670E micro-USB cable to Pi USB port (recommended)
#          Creates /dev/ttyUSB0..3 — AT port is auto-detected.
#   gpio — A7670E TX/RX wired to Pi GPIO 14/15 (UART)
#          Uses /dev/serial0.
# ==============================================================

SERIAL_MODE    = "usb"            # "usb" (recommended) or "gpio"
SERIAL_PORT    = "auto"           # "auto" to detect, or explicit path
                                  # e.g. "/dev/ttyUSB2", "/dev/serial0"
SERIAL_BAUD    = 115200           # Primary baud rate
SERIAL_FALLBACK_BAUD = 9600      # Fallback if 115200 fails
SERIAL_TIMEOUT = 1.0              # Serial read timeout (seconds)

# ==============================================================
# GT-U7 GPS MODULE (Backup GPS)
# ==============================================================
# Connected via GPIO UART: GT-U7 TX → Pi GPIO 15 (RX)
#                          GT-U7 RX → Pi GPIO 14 (TX)  (optional)
#                          GT-U7 GND → Pi GND
#                          GT-U7 VCC → Pi 3.3V or 5V
# NOTE: Requires enable_uart=1 and dtoverlay=disable-bt in
#       /boot/firmware/config.txt. Reboot after changes.
# ==============================================================

GTU7_ENABLED      = True              # Set False to disable backup GPS
GTU7_PORT         = "/dev/serial0"    # GPIO UART port
GTU7_BAUD         = 9600              # GT-U7 default baud rate
GTU7_TIMEOUT      = 1.0              # Serial read timeout (seconds)

# ==============================================================
# GPS BACKGROUND POLLER
# ==============================================================
# Continuously polls both GPS modules in background so a fix is
# already cached when the panic button is pressed.
# ==============================================================

GPS_BG_ENABLED       = True    # Enable 24/7 background GPS polling
GPS_BG_POLL_INTERVAL = 5       # Seconds between background polls
GPS_BG_MAX_AGE       = 60      # Max fix age (seconds) to accept as "fresh"

# ==============================================================
# TIMING CONSTANTS
# ==============================================================

GPS_TIMEOUT       = 30     # Seconds to wait for GNSS fix per cycle
GPS_POLL_INTERVAL = 5      # Seconds between AT+CGNSINF polls
GPS_MAX_CYCLES    = 0      # Max GPS retry cycles (0 = unlimited — never give up)
GPS_CYCLE_PAUSE   = 5      # Seconds pause between GPS retry cycles
ARM_HOLD_TIME     = 3.0    # Seconds button must be held to arm
CANCEL_WINDOW     = 3.0    # Seconds user has to cancel after arming
SMS_RETRY_COUNT   = 3      # Retries per contact per SMS cycle
SMS_MAX_CYCLES    = 0      # Max SMS send cycles (0 = unlimited — never give up)
SMS_CYCLE_PAUSE   = 5      # Seconds pause between SMS retry cycles
MODEM_WAKE_ATTEMPTS = 10   # Max AT pings to wake an idle modem
KEEPALIVE_INTERVAL  = 120  # Seconds between idle keepalive pings (0 = off)
DEBOUNCE_DELAY    = 0.05   # Button debounce delay (50ms)

# ==============================================================
# LOGGING
# ==============================================================

LOG_FILE = "logs.txt"       # Log file path (relative to working dir)

# ==============================================================
# RELAY LOGIC
# Set to True if your relay activates on LOW signal (most common).
# Set to False if your relay activates on HIGH signal.
# NOTE: If your buzzer is on the NC (Normally Closed) terminal,
#       flip this setting so "off" energizes the relay (opening NC).
# ==============================================================

RELAY_ACTIVE_LOW = False
