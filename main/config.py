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
    "EMERGENCY ALERT!\n"
    "\n"
    "Hey {contact_name}, I'm letting you know that the emergency "
    "panic button has been pressed by {owner_name}.\n"
    "\n"
    "I've got his/her location from the GPS device. "
    "Here is the Google Maps link:\n"
    "\n"
    "{map_link}\n"
    "\n"
    "Please respond immediately and check on his/her safety."
)

# ==============================================================
# GPIO PIN CONFIGURATION (BCM numbering)
# Match these to your physical wiring.
# ==============================================================

PIN_GREEN_LED = 17      # Green LED anode (via 220-330 ohm resistor)
PIN_RED_LED   = 27      # Red LED anode (via 220-330 ohm resistor)
PIN_RELAY     = 18      # Relay module IN pin (Active LOW — buzzer)
PIN_BUTTON    = 22      # Push button (internal pull-up, press = LOW)

# ==============================================================
# A7670E UART CONFIGURATION
# ==============================================================

SERIAL_PORT    = "/dev/serial0"   # Hardware UART on Pi GPIO 14/15
SERIAL_BAUD    = 115200           # Primary baud rate
SERIAL_FALLBACK_BAUD = 9600      # Fallback if 115200 fails
SERIAL_TIMEOUT = 1.0              # Serial read timeout (seconds)

# ==============================================================
# TIMING CONSTANTS
# ==============================================================

GPS_TIMEOUT       = 30     # Seconds to wait for GNSS fix
GPS_POLL_INTERVAL = 5      # Seconds between AT+CGNSINF polls
ARM_HOLD_TIME     = 3.0    # Seconds button must be held to arm
CANCEL_WINDOW     = 3.0    # Seconds user has to cancel after arming
SMS_RETRY_COUNT   = 3      # Retries per contact on SMS failure
DEBOUNCE_DELAY    = 0.05   # Button debounce delay (50ms)

# ==============================================================
# LOGGING
# ==============================================================

LOG_FILE = "logs.txt"       # Log file path (relative to working dir)

# ==============================================================
# RELAY LOGIC
# Set to True if your relay activates on LOW signal (most common).
# Set to False if your relay activates on HIGH signal.
# ==============================================================

RELAY_ACTIVE_LOW = True
