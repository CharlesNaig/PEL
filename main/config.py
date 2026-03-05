"""
Panic Button Emergency Locator - Configuration
================================================
All user-configurable constants in one place.
Edit this file before deployment to match your hardware and contacts.

Port of: USER CONFIGURATION, PIN CONFIGURATION, TIMING CONSTANTS
         sections in main.ino (lines 14-78)
"""

# ==============================================================
# OWNER INFORMATION
# ==============================================================

OWNER_NAME = "Charles"

# ==============================================================
# EMERGENCY CONTACTS
# Add/remove contacts as needed. Each entry needs a name and number.
# Numbers must include country code (e.g. +63 for Philippines).
# ==============================================================

CONTACTS = [
    {"name": "Andrew Felipe", "number": "+639154693904"},
    {"name": "Naig",          "number": "+639391445673"},
]

# ==============================================================
# SMS MESSAGE TEMPLATE
# Available placeholders: {contact_name}, {owner_name}, {map_link}
# ==============================================================

SMS_TEMPLATE = (
    "EMERGENCY! {owner_name} pressed the panic button.\n"
    "{contact_name}, please check on them immediately.\n"
    "GPS: {map_link}\n"
    "(Paste into Google Maps)"
)
# Filled example (147 chars):
# EMERGENCY! Charles pressed the panic button.
# Andrew Felipe, please check on them immediately.
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
