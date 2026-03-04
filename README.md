# Panic Button Emergency Locator (PEL)

A Raspberry Pi–based panic button system that sends emergency SMS alerts with real-time GPS location to predefined contacts.

When the button is pressed and held, the device acquires a GPS fix via the **SIMCOM A7670E** LTE module's built-in GNSS, builds a Google Maps link, and sends personalized SMS messages to all configured emergency contacts.

---

## Features

- **One-button operation** — press and hold for 3 seconds to arm, with a cancel window
- **Real-time GPS** — GNSS coordinates via A7670E built-in receiver
- **LTE SMS delivery** — sends alerts over LTE Cat-1 (no 2G dependency)
- **Multi-contact support** — configurable list of emergency contacts
- **Customizable SMS template** — personalized messages with contact name, owner name, and map link
- **Audio/visual feedback** — buzzer patterns and LED indicators for every state
- **Local event logging** — all panic events logged to file with timestamps and coordinates
- **4-phase safety sequence** — hold-to-arm → confirmation → cancel window → execute

---

## Hardware Requirements

| Component | Specification |
|---|---|
| **Microcontroller** | Raspberry Pi (any model with GPIO — Pi 3/4/5 recommended) |
| **LTE + GPS Module** | SIMCOM A7670E (LTE Cat-1 with built-in GNSS) |
| **Relay Module** | 5V relay module (Active LOW) with buzzer |
| **Green LED** | Standard LED + 220Ω–330Ω resistor |
| **Red LED** | Standard LED + 220Ω–330Ω resistor |
| **Push Button** | Momentary push button (normally open) |
| **SIM Card** | Nano/Micro SIM with SMS plan and data (for LTE registration) |
| **Power Supply** | 5V 2A dedicated supply for A7670E (**not** from Pi GPIO 5V pin) |

---

## Wiring Diagram

### GPIO Pin Map (BCM Numbering)

| BCM Pin | Component | Function |
|---|---|---|
| GPIO 14 (TXD) | A7670E RXD | Pi transmits AT commands to module |
| GPIO 15 (RXD) | A7670E TXD | Module sends responses to Pi |
| GPIO 17 | Green LED | Success / status indicator |
| GPIO 27 | Red LED | Error / arming indicator |
| GPIO 18 | Relay IN | Controls active buzzer (Active LOW) |
| GPIO 22 | Push Button | Panic trigger (internal pull-up, press = LOW) |

### A7670E Module

| A7670E Pin | Connect To | Notes |
|---|---|---|
| TXD | GPIO 15 (Pi RXD) | A7670E sends data to Pi |
| RXD | GPIO 14 (Pi TXD) | Pi sends AT commands to A7670E |
| GND | Pi GND | Common ground |
| VCC / 5V | **Dedicated 5V 2A supply** | Do **NOT** power from Pi 5V pin |

> **Important:** The A7670E draws up to 2A during transmission bursts. Use a dedicated regulated 5V supply. Share a common GND with the Pi.

### Relay Module (Buzzer)

| Relay Pin | Connect To | Notes |
|---|---|---|
| VCC | 5V | Power |
| GND | Pi GND | Common ground |
| IN | GPIO 18 | Active LOW (configurable in `config.py`) |

### LEDs

| LED | Anode (+) | Cathode (−) | Notes |
|---|---|---|---|
| Green | GPIO 17 | Pi GND | Via 220Ω–330Ω resistor |
| Red | GPIO 27 | Pi GND | Via 220Ω–330Ω resistor |

### Push Button

| Pin | Connect To | Notes |
|---|---|---|
| One side | GPIO 22 | Internal pull-up enabled in software |
| Other side | Pi GND | Press = LOW signal |

---

## Raspberry Pi Setup

### 1. Enable Hardware UART

The A7670E communicates over the Pi's hardware UART. On Pi 3/4/5, Bluetooth uses this UART by default and must be disabled.

Add to `/boot/config.txt`:

```
dtoverlay=disable-bt
enable_uart=1
```

Edit `/boot/cmdline.txt` and **remove** `console=serial0,115200` if present.

Reboot after making these changes:

```bash
sudo reboot
```

### 2. Disable Bluetooth Service (Optional)

```bash
sudo systemctl disable hciuart
```

### 3. Verify UART

After reboot, confirm `/dev/serial0` exists:

```bash
ls -la /dev/serial0
```

---

## Installation

### 1. Clone the Repository

```bash
git clone https://github.com/CharlesNaig/PEL.git
cd PEL
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

This installs:
- `pyserial` — UART communication with A7670E
- `RPi.GPIO` — GPIO control for LEDs, relay, and button

### 3. Configure

Edit [main/config.py](main/config.py) before first run:

```python
# Your name
OWNER_NAME = "Charles"

# Emergency contacts (add/remove as needed)
CONTACTS = [
    {"name": "Andrew Felipe", "number": "+639154693904"},
    {"name": "Naig",          "number": "+639391445673"},
]

# Customize the SMS message
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
```

Available SMS placeholders: `{contact_name}`, `{owner_name}`, `{map_link}`

### 4. Verify GPIO Pins

If your wiring differs from the default, update the pin assignments in [main/config.py](main/config.py):

```python
PIN_GREEN_LED = 17
PIN_RED_LED   = 27
PIN_RELAY     = 18
PIN_BUTTON    = 22
```

---

## Usage

### Run the Main Application

```bash
sudo python3 main/main.py
```

> `sudo` is required for GPIO access on most Pi configurations.

### How the Panic Sequence Works

The system uses a **4-phase safety sequence** to prevent accidental triggers:

| Phase | Action | Feedback |
|---|---|---|
| **1 — Hold to Arm** | Press and hold button for 3 seconds | Red LED blinks, buzzer ticks once per second |
| **2 — Armed Confirm** | System confirms arm state | Both LEDs flash, double beep |
| **3 — Cancel Window** | Release button; 3-second window to press again to cancel | Green LED blinks fast |
| **4 — Execute** | GPS acquisition → SMS to all contacts → log event | Green = success, Red = failure |

**To cancel:** Press the button during Phase 3 (the cancel window). You'll hear a cancel sound and see both LEDs turn off.

### Idle State

During idle, the green LED is solid ON, indicating the system is ready. The main loop polls the button every 50ms.

---

## Configuration Reference

All settings are in [main/config.py](main/config.py):

| Setting | Default | Description |
|---|---|---|
| `OWNER_NAME` | `"Charles"` | Name included in SMS messages |
| `CONTACTS` | 2 contacts | List of `{name, number}` dicts with country code |
| `SMS_TEMPLATE` | Emergency alert | Message template with placeholders |
| `PIN_GREEN_LED` | `17` | BCM pin for green LED |
| `PIN_RED_LED` | `27` | BCM pin for red LED |
| `PIN_RELAY` | `18` | BCM pin for relay/buzzer |
| `PIN_BUTTON` | `22` | BCM pin for push button |
| `SERIAL_PORT` | `"/dev/serial0"` | UART device path |
| `SERIAL_BAUD` | `115200` | Primary baud rate (fallback: 9600) |
| `GPS_TIMEOUT` | `30` | Seconds to wait for GNSS fix |
| `ARM_HOLD_TIME` | `3.0` | Seconds button must be held to arm |
| `CANCEL_WINDOW` | `3.0` | Seconds to cancel after arming |
| `SMS_RETRY_COUNT` | `3` | SMS send retries per contact |
| `LOG_FILE` | `"logs.txt"` | Event log file path |
| `RELAY_ACTIVE_LOW` | `True` | Set `False` if relay activates on HIGH |

---

## Project Structure

```
PEL/
├── main/
│   ├── main.py          # Application entry point (setup, loop, shutdown)
│   ├── config.py         # All user-configurable settings
│   ├── a7670e.py         # A7670E LTE driver (AT commands, GNSS, SMS)
│   ├── buzzer.py         # Relay/buzzer control (patterns, Active LOW)
│   ├── led.py            # LED control (solid, blink, threaded patterns)
│   ├── logger.py         # File-based event logging
│   └── panic.py          # 4-phase panic state machine
├── tests/
│   ├── test_a7670e.py    # A7670E 9-test diagnostic suite + AT terminal
│   ├── test_buzzer_relay.py  # Buzzer pattern verification (6 tests)
│   └── test_led.py       # LED pattern verification (8 tests)
├── requirements.txt      # Python dependencies
└── README.md
```

### Module Descriptions

| Module | Lines | Purpose |
|---|---|---|
| [main/a7670e.py](main/a7670e.py) | ~590 | Full A7670E driver — serial init with auto baud detection, AT command engine, SIM/signal/registration checks, GNSS enable/disable/acquire/parse, SMS send with retry logic |
| [main/panic.py](main/panic.py) | ~215 | Core state machine — Phase 1 (hold-to-arm), Phase 2 (confirmation), Phase 3 (cancel window), Phase 4 (GPS → SMS → log → feedback) |
| [main/led.py](main/led.py) | ~165 | LED helpers with threaded non-blocking blink — `blink_red()`, `blink_green()`, `blink_both()`, `solid_green()`, etc. |
| [main/main.py](main/main.py) | ~115 | Entry point — GPIO setup, A7670E initialization, button polling loop, graceful shutdown with `GPIO.cleanup()` |
| [main/buzzer.py](main/buzzer.py) | ~105 | Relay/buzzer patterns — `tick()`, `double_beep()`, `cancel_sound()`, `success_sound()`, `fail_sound()` |
| [main/config.py](main/config.py) | ~95 | All deployment settings — contacts, pins, timings, UART, SMS template |
| [main/logger.py](main/logger.py) | ~75 | Event logger — writes structured log entries with GNSS or system timestamps |

---

## Test Scripts

Run these to verify individual hardware components before full deployment.

### A7670E Diagnostic Suite

```bash
sudo python3 tests/test_a7670e.py
```

Runs 9 sequential tests:
1. AT communication
2. Module information
3. SIM card status
4. Signal quality (RSSI)
5. Network registration
6. Operator info
7. GNSS power on
8. GPS fix acquisition
9. SMS send (interactive)

After tests complete, enters an **interactive AT terminal** for manual commands.

### Buzzer/Relay Test

```bash
sudo python3 tests/test_buzzer_relay.py
```

Tests 6 buzzer patterns: tick, double beep, cancel sound, success sound, fail sound, and continuous ON.

### LED Test

```bash
sudo python3 tests/test_led.py
```

Tests 8 LED patterns: solid green, solid red, solid both, red blink fast, green blink slow, green blink fast, alternating, and rapid cycle.

---

## Troubleshooting

### A7670E Not Responding

- Verify `/dev/serial0` exists (`ls -la /dev/serial0`)
- Confirm `dtoverlay=disable-bt` and `enable_uart=1` are in `/boot/config.txt`
- Check that `console=serial0,115200` is removed from `/boot/cmdline.txt`
- Ensure the A7670E has a dedicated 5V 2A power supply
- Run `sudo python3 tests/test_a7670e.py` for diagnostics

### No GPS Fix

- Ensure clear sky view (GNSS needs line-of-sight to satellites)
- First cold fix may take 30–60 seconds; subsequent fixes are faster
- Check that the A7670E's GNSS antenna is connected
- Increase `GPS_TIMEOUT` in [main/config.py](main/config.py) if needed

### SMS Not Sending

- Verify SIM card is inserted and has SMS credit
- Check signal quality: RSSI should be > 10 (run test_a7670e.py, Test 4)
- Ensure network registration shows "home" or "roaming" (Test 5)
- Verify contact numbers include country code (e.g., `+63` for Philippines)

### Button Not Detected

- Confirm GPIO 22 wiring: one side to GPIO 22, other side to GND
- The software enables an internal pull-up resistor; no external pull-up needed
- Check `PIN_BUTTON` value in [main/config.py](main/config.py)

### Relay/Buzzer Not Working

- Check `RELAY_ACTIVE_LOW` in [main/config.py](main/config.py) matches your relay module
- Verify relay module has separate 5V power
- Run `sudo python3 tests/test_buzzer_relay.py` to test patterns

### Permission Denied

- GPIO access requires root: use `sudo python3 main/main.py`
- Alternatively, add your user to the `gpio` group: `sudo usermod -aG gpio $USER`

---

## Running on Boot (Optional)

To start PEL automatically when the Pi boots, create a systemd service:

```bash
sudo nano /etc/systemd/system/pel.service
```

```ini
[Unit]
Description=Panic Button Emergency Locator
After=multi-user.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 /home/pi/PEL/main/main.py
WorkingDirectory=/home/pi/PEL
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl enable pel.service
sudo systemctl start pel.service
```

Check status:

```bash
sudo systemctl status pel.service
```

---

## License

This project is for personal/educational use.
