# Dual GPS Plan — A7670E + GT-U7 Teamwork
## Panic Button Emergency Locator (PEL)

### Goal
Both GPS modules (A7670E built-in GNSS and GT-U7) work **simultaneously** 
each poll cycle. First one to return a valid fix wins. If one fails, the 
other keeps trying. No fix is wasted.

---

## Architecture Overview

```
┌─────────────────────────────────────────────┐
│              panic.py (Step 1)               │
│         "GPS ACQUISITION" loop               │
│                                              │
│   Each cycle:                                │
│     1. Poll A7670E GNSS  (AT+CGNSSINFO)     │
│     2. Poll GT-U7 NMEA   ($GPRMC/$GPGGA)    │
│     3. First valid fix → DONE, send SMS      │
│     4. No fix → restart cycle                │
└──────────┬──────────────────┬────────────────┘
           │                  │
    ┌──────▼──────┐    ┌──────▼──────┐
    │  a7670e.py  │    │   gtu7.py   │
    │  USB serial │    │  GPIO UART  │
    │ /dev/ttyUSB2│    │ /dev/serial0│
    │  115200 bd  │    │  9600 baud  │
    └─────────────┘    └─────────────┘
```

---

## Files to Create / Modify

### 1. NEW: `main/gtu7.py` — GT-U7 GPS Driver

Handles serial NMEA communication with the GT-U7 (u-blox NEO-6M) module.

**Responsibilities:**
- Open/close `/dev/serial0` at 9600 baud
- Read NMEA sentences (`$GPRMC`, `$GPGGA`)
- Parse lat/lng from NMEA format (DDMM.MMMMMM → decimal degrees)
- Single-poll method: `poll_fix()` → returns `(lat, lng, utc_time)` or `(None, None, None)`
- `enable()` / `disable()` to open/close the serial port

**Key design decisions:**
- GT-U7 is always-on (no AT commands needed, just reads NMEA stream)
- Non-blocking reads — poll once, check buffer, return immediately
- Same return format as `a7670e.acquire_gps()` for easy integration
- NMEA checksum validation to reject corrupted sentences

**NMEA Parsing:**
```
$GPRMC,083456.00,A,1435.9707,N,12059.0533,E,0.04,0.00,050326,,,A*6B
       ^^^^^^^^  ^ ^^^^^^^^^^ ^ ^^^^^^^^^^^ ^              ^^^^^^
       UTC time  | Latitude   N  Longitude  E              Date
                 A=Valid fix
                 V=No fix

$GPGGA,083456.00,1435.9707,N,12059.0533,E,1,06,1.2,45.3,M,,,,*47
                                           ^ ^^
                                           | Satellites used
                                           1=GPS fix
```

**Coordinate conversion (same as A7670E parser):**
```
Raw:   1435.9707 N  →  14° + (35.9707 / 60) = 14.599512°
Raw:  12059.0533 E  → 120° + (59.0533 / 60) = 120.984222°
```

---

### 2. MODIFY: `main/config.py` — Add GT-U7 Settings

```python
# ==============================================================
# GT-U7 GPS MODULE (Backup GPS)
# ==============================================================
# Connected via GPIO UART: GT-U7 TX → Pi GPIO 15 (RX)
#                          GT-U7 RX → Pi GPIO 14 (TX)  (optional)
#                          GT-U7 GND → Pi GND
#                          GT-U7 VCC → Pi 3.3V or 5V
# ==============================================================

GTU7_ENABLED      = True              # Set False to disable backup GPS
GTU7_PORT         = "/dev/serial0"    # GPIO UART port
GTU7_BAUD         = 9600              # GT-U7 default baud rate
GTU7_TIMEOUT      = 1.0              # Serial read timeout (seconds)
```

---

### 3. MODIFY: `main/panic.py` — Dual GPS Polling in `execute_panic()`

**Current flow (single GPS):**
```
Loop:
  1. Wake modem
  2. Enable A7670E GNSS
  3. Poll AT+CGNSSINFO for 30s
  4. No fix → disable GNSS, restart cycle
```

**New flow (dual GPS):**
```
Loop:
  1. Wake modem
  2. Enable A7670E GNSS
  3. Poll BOTH each interval:
     a. Poll A7670E (AT+CGNSSINFO)
     b. Poll GT-U7 (read NMEA buffer)
     c. If EITHER has a fix → use it, break
  4. No fix from either → restart cycle
```

**What changes in panic.py:**
- Import `gtu7` module
- Accept `gtu7_module` parameter alongside `modem`
- Inside the GPS poll loop, check both sources each iteration
- Print which module got the fix: `"✓ GPS FIX via A7670E"` or `"✓ GPS FIX via GT-U7"`
- If GT-U7 is disabled/unavailable, fall back to A7670E-only (current behavior)

---

### 4. MODIFY: `main/main.py` — Initialize GT-U7 in `setup()`

**Changes:**
- Import `gtu7`
- In `setup()`: initialize GT-U7 with warm-up check (like modem check)
- Print `"  GPS (GT-U7): OK"` or `"  GPS (GT-U7): FAIL — not detected"`
- Pass GT-U7 instance to `panic.handle_panic_sequence(modem, gtu7_module)`
- In `loop()`: pass GT-U7 to panic sequence
- In `finally`: close GT-U7 serial on shutdown

**Warm-up check for GT-U7:**
```
  Open serial port
  Read for 2 seconds
  If any $GPRMC or $GPGGA sentence received → OK (module is alive)
  No NMEA data → FAIL
```

---

### 5. MODIFY: `main/a7670e.py` — Add single-poll method

**Add `poll_gnss_once()` method:**
- Sends `AT+CGNSSINFO` once
- Returns `(lat, lng, utc_time)` or `(None, None, None)` immediately
- Used by the new dual-poll loop in `panic.py` instead of `acquire_gps()`
- The existing `acquire_gps()` stays for backward compatibility

---

## Dual Poll Logic (Core Algorithm)

```python
# In panic.py — replaces the current single-GPS loop

lat, lng, utc_time = None, None, None
gps_source = None

while lat is None or lng is None:
    gps_cycle += 1
    
    # Wake modem & enable A7670E GNSS
    modem.wake(...)
    modem.enable_gnss()
    time.sleep(1.0)
    
    # Poll both GPS sources for GPS_TIMEOUT seconds
    poll_start = time.time()
    poll_count = 0
    
    while (time.time() - poll_start) < config.GPS_TIMEOUT:
        poll_count += 1
        print(f"  GPS poll #{poll_count}  ({remaining}s remaining)")
        
        # Poll A7670E
        lat, lng, utc_time = modem.poll_gnss_once()
        if lat is not None:
            gps_source = "A7670E"
            break
        
        # Poll GT-U7 (if available)
        if gtu7_module:
            lat, lng, utc_time = gtu7_module.poll_fix()
            if lat is not None:
                gps_source = "GT-U7"
                break
        
        print("  No fix yet (both modules)...")
        time.sleep(config.GPS_POLL_INTERVAL)
    
    if lat is not None:
        break
    
    # Cycle failed — restart
    modem.disable_gnss()
    time.sleep(config.GPS_CYCLE_PAUSE)

print(f"✓ GPS FIX via {gps_source}!")
```

---

## Wiring Reference (GT-U7 to Raspberry Pi)

```
GT-U7 Pin    Pi Pin     Purpose
---------    ------     -------
VCC       →  Pin 1      3.3V power (or Pin 2 for 5V)
GND       →  Pin 6      Common ground
TX        →  Pin 10     GT-U7 sends NMEA → Pi GPIO 15 (RX)
RX        →  Pin 8      Pi GPIO 14 (TX) → GT-U7 (optional)
PPS       →  (unused)   Pulse-per-second signal
```

> **NOTE:** Since A7670E uses USB, the Pi's GPIO UART (`/dev/serial0`) is 
> free for the GT-U7. No conflicts.

> **IMPORTANT:** Requires `enable_uart=1` and `dtoverlay=disable-bt` in 
> `/boot/firmware/config.txt` (same as GPIO-mode A7670E). Reboot after changes.

---

## Testing Plan

### `tests/test_gtu7.py` — Standalone GT-U7 test
- Open serial, read NMEA for 30s
- Print raw sentences
- Parse and display coordinates if fix obtained
- Verify checksum validation

### `tests/test_dual_gps.py` — Both modules together
- Initialize A7670E + GT-U7
- Run dual poll loop for 60s
- Report which module got the fix first
- Verify no serial port conflicts

---

## Risk / Considerations

| Risk | Mitigation |
|------|-----------|
| GPIO UART conflict (BT on Pi 3/4) | Require `dtoverlay=disable-bt` in config |
| GT-U7 not connected | `GTU7_ENABLED = False` in config, graceful fallback |
| Both modules slow indoors | Expected — GPS needs sky view, not a code issue |
| Serial port permissions | Run with `sudo` (same as current) |
| GT-U7 noisy NMEA stream | Checksum validation, ignore malformed sentences |

---

## Summary of All File Changes

| File | Action | What |
|------|--------|------|
| `main/gtu7.py` | **CREATE** | GT-U7 NMEA driver |
| `main/config.py` | MODIFY | Add GTU7_* settings |
| `main/panic.py` | MODIFY | Dual-poll GPS loop |
| `main/main.py` | MODIFY | Init GT-U7, pass to panic |
| `main/a7670e.py` | MODIFY | Add `poll_gnss_once()` method |
| `tests/test_gtu7.py` | **CREATE** | GT-U7 standalone test |
| `tests/test_dual_gps.py` | **CREATE** | Dual GPS integration test |

---

**Review this plan and let me know:**
1. Is the GT-U7 on GPIO UART (`/dev/serial0`) at 9600 baud? 
2. Any changes to the polling strategy?
3. Ready to implement?
