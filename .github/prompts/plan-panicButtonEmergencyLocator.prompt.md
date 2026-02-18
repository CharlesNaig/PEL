# Panic Button Emergency Locator

## Production Prototype Functional Plan

---

## 1. System Overview

The Panic Button Emergency Locator is a portable embedded emergency device built using Arduino Nano.

When the panic button is pressed:

1. System validates button press (debounced).
2. GPS module retrieves real-time latitude and longitude.
3. Coordinates are processed into a Google Maps link.
4. SMS message containing the emergency alert and location link is sent to three predefined emergency contacts using SIM800L.
5. Event details (date, time, coordinates, status) are logged into MicroSD card.
6. Buzzer and LED provide confirmation feedback.
7. Error handling manages failures (GPS timeout, GSM failure, SD write failure).

The system is battery-powered and designed for real-world emergency deployment.

---

# 2. Final Pin Configuration

## Arduino Nano Pin Map

| Pin | Component    | Function                            |
| --- | ------------ | ----------------------------------- |
| D2  | GPS TX       | Receives GPS data                   |
| D3  | GPS RX       | Sends data to GPS                   |
| D4  | Push Button  | Panic trigger (INPUT_PULLUP)        |
| D5  | Green LED    | Success indicator                   |
| D6  | Red LED      | Error indicator                     |
| D7  | Relay Module | Controls active buzzer (ACTIVE LOW) |
| D8  | SIM800L TXD  | GSM transmit to Arduino             |
| D9  | SIM800L RXD  | GSM receive (via voltage divider)   |
| D10 | SD Card CS   | Chip Select                         |
| D11 | SD Card MOSI | SPI Data                            |
| D12 | SD Card MISO | SPI Data                            |
| D13 | SD Card SCK  | SPI Clock                           |

---

# 3. Wiring Summary

## GPS Module

* VCC → 5V
* GND → GND
* TX → D2
* RX → D3

## SIM800L (5VIN version)

* 5VIN → Arduino 5V
* GND → Arduino GND
* TXD → D8
* RXD → D9 (via 10k/20k voltage divider)
* VDD → Not connected
* RST → Not connected (optional)

## SD Card Module (SPI)

* VCC → 5V
* GND → GND
* CS → D10
* MOSI → D11
* MISO → D12
* SCK → D13

## Relay Module

* VCC → 5V
* GND → GND
* IN → D7 (Active LOW)

## Push Button

* One side → D4
* Other side → GND

---

# 4. Power Architecture

Battery: 7.4V Li-ion

* 7.4V → Arduino VIN
* Arduino 5V rail powers:

  * GPS
  * SIM800L (5VIN version only)
  * SD module
  * Relay

All modules share common GND.

Add 1000µF capacitor across SIM800L VCC and GND for stability.

---

# 5. Core Functional Workflow

## Step 1: Button Activation (Long Press to Arm)

The system uses a deliberate long-press activation to prevent accidental triggers.

### Phase 1 — Hold to Arm (3 seconds)

* User presses and **holds** the D4 button
* During the hold:
  * Red LED blinks rapidly (every 200ms) — visual cue: "arming..."
  * Buzzer gives 3 short ticks (one per second) — audio cue: "arming..."
* If button is **released early** (before 3 seconds):
  * Everything resets to idle — **no action taken**
  * Serial: "Cancelled — button released too early"

### Phase 2 — Armed Confirmation (beep + LEDs)

* After 3-second hold is complete:
  * Buzzer gives a confirmation double-beep (short-short)
  * Both Green + Red LEDs flash together once — "armed!"
  * Serial: "Armed! Release to execute, or press again within 3s to cancel"

### Phase 3 — Cancellation Window (3 seconds)

* A 3-second countdown begins after arming
* During this window:
  * Green LED blinks slowly (every 500ms) — visual cue: "about to execute..."
  * User can **press the button once** to **cancel**
* If **cancelled**:
  * Red LED turns ON for 1 second
  * Buzzer gives 2 long beeps — audio cue: "cancelled"
  * Serial: "Panic cancelled by user"
  * System returns to idle
* If **not cancelled** (3 seconds pass with no press):
  * System proceeds to execute the panic routine

### Phase 4 — Panic Execution

* Green LED ON solid
* Buzzer short-long pattern (success start indicator)
* GPS acquisition begins
* SMS sent to emergency contacts
* SD card logs the event
* Success/failure feedback as defined in Section 11

## Step 2: GPS Acquisition

* Wait for valid GPS fix
* Timeout after 30 seconds
* If no fix → trigger error state

## Step 3: Coordinate Processing

Extract:

* Latitude
* Longitude

Format:

```
https://maps.google.com/?q=LATITUDE,LONGITUDE
```

Example:

```
https://maps.google.com/?q=14.5995,120.9842
```

No Google API required for simple location link.

---

# 6. Optional Google Maps API Configuration (If Reverse Geocoding Needed)

If converting coordinates into readable address:

## Google Cloud Configuration

1. Create project in Google Cloud Console.
2. Enable Maps Geocoding API.
3. Generate API key.
4. Restrict key to HTTP usage.

Store in firmware:

```
#define GOOGLE_API_KEY "YOUR_API_KEY_HERE"
```

Reverse Geocode Request Format:

```
https://maps.googleapis.com/maps/api/geocode/json?latlng=LAT,LONG&key=API_KEY
```

Note: SIM800L must support HTTP GET for this feature.

---

# 7. Emergency Contact Configuration

Store numbers in firmware:

```
String emergencyNumbers[3] = {
  "+639XXXXXXXXX",
  "+639XXXXXXXXX",
  "+639XXXXXXXXX"
};
```

---

# 8. SMS Message Format

Message template:

```
EMERGENCY ALERT!

The panic button has been activated.

Live Location:
https://maps.google.com/?q=LAT,LONG

Please respond immediately.
```

Optional:
Include timestamp from RTC or GPS time.

---

# 9. SD Card Log Format

File: `logs.txt`

Log entry format:

```
[YYYY-MM-DD HH:MM:SS]
Latitude: xx.xxxxxx
Longitude: xx.xxxxxx
Status: SUCCESS / FAILED
--------------------------------
```

If failure:

```
Error: GPS Timeout
Error: GSM Send Failed
Error: SD Write Failed
```

---

# 10. Error Handling System

## GPS Timeout (30 seconds)

* Red LED ON
* Long buzzer alert
* Log error
* Do not send SMS

## GSM Failure

* Retry 3 times
* If still failed:

  * Log failure
  * Red LED ON

## SD Card Failure

* Continue SMS
* Indicate error with LED blink pattern
* Store temporary flag in RAM

## Network Not Registered

* Check SIM status using:
  AT+CREG?
* Wait for registration before sending SMS

---

# 11. System Feedback Patterns

## Arming Phase (holding button for 3 seconds)

* Red LED: Blinks rapidly every 200ms
* Buzzer: 1 short tick per second (3 ticks total)
* Meaning: "System is arming, keep holding..."

## Armed Confirmation (3-second hold complete)

* Both LEDs: Flash together once
* Buzzer: Double short beep (100ms + 100ms)
* Meaning: "Armed! Release button."

## Cancellation Window (3 seconds after arming)

* Green LED: Blinks slowly every 500ms
* Meaning: "Press button now to cancel"

## Cancelled

* Red LED: Solid ON for 1 second
* Buzzer: 2 long beeps (400ms each)
* Meaning: "Panic cancelled, returning to idle"

## Execute — Success

* Short beep (200ms)
* Pause (100ms)
* Long beep (500ms)
* Green LED ON during pattern

## Execute — Failure

* Single long buzz (800ms)
* Red LED ON

## Idle

* All outputs OFF

---

# 12. Production Considerations

* Use proper enclosure
* Secure antenna placement for GPS and GSM
* Add power switch
* Use thick power wires for SIM800L
* Use watchdog timer for system recovery
* Protect battery with BMS

---

# 13. Deployment Objective

The final prototype shall:

* Provide real-time emergency location via SMS
* Log emergency events locally
* Operate reliably on battery power
* Handle communication and GPS errors safely
* Be portable and suitable for field deployment
