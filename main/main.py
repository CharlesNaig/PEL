#!/usr/bin/env python3
"""
Panic Button Emergency Locator — Main Entry Point
====================================================
Raspberry Pi + SIMCOM A7670E production firmware.

Port of: setup() + loop() in main.ino (lines 125-175)
Run with:  sudo python3 main.py
(sudo required for GPIO access on most Pi configurations)
"""

import time
import sys
import RPi.GPIO as GPIO

import config
from a7670e import A7670E
from gtu7 import GTU7
from gps_poller import GPSPoller
from logger import get_logger
import buzzer
import led
import panic

log = get_logger("PEL.main")


def setup():
    """
    Initialize all peripherals with warm-up component checks.
    Returns (modem, gtu7_module) tuple.
    Port of: setup() in main.ino (lines 125-170)
    """
    # ── GPIO global config ──────────────────────────────────────────────
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)

    # ── Button ──────────────────────────────────────────────────────────
    GPIO.setup(config.PIN_BUTTON, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    # ── Peripherals ─────────────────────────────────────────────────────
    buzzer.setup()
    led.setup()

    # ── Power-on confirmation beep ──────────────────────────────────────
    buzzer.tick()

    log.info("=================================")
    log.info(" Panic Button Emergency Locator")
    log.info(" Raspberry Pi + A7670E Edition")
    log.info("=================================")

    # ── Component warm-up checks ────────────────────────────────────────
    log.info("Warming up — checking components...")
    log.info("---------------------------------")
    all_ok = True

    # 1) Green LED
    led.green_on()
    time.sleep(0.3)
    led.green_off()
    log.info("  Green LED : OK")

    # 2) Red LED
    led.red_on()
    time.sleep(0.3)
    led.red_off()
    log.info("  Red LED   : OK")

    # 3) Buzzer (short tick)
    buzzer.tick()
    log.info("  Buzzer    : OK")

    # 4) Button GPIO (verify it's readable — HIGH when not pressed)
    try:
        btn_state = GPIO.input(config.PIN_BUTTON)
        if btn_state == GPIO.HIGH:
            log.info("  Button    : OK (idle)")
        else:
            log.warning("  Button    : OK (pressed — release it)")
    except Exception:
        log.error("  Button    : FAIL")
        all_ok = False

    # 5) A7670E modem
    log.info("  Modem     : detecting...")
    port = config.SERIAL_PORT
    modem = None
    modem_ok = False

    if config.SERIAL_MODE == "usb" and port == "auto":
        from a7670e import find_usb_at_port
        detected = find_usb_at_port()
        if detected:
            port = detected
        else:
            port = None
    elif port == "auto":
        port = "/dev/serial0"

    pwrkey = config.PIN_PWRKEY if config.SERIAL_MODE == "gpio" else None

    if port is not None:
        modem = A7670E(
            port=port,
            baud=config.SERIAL_BAUD,
            fallback_baud=config.SERIAL_FALLBACK_BAUD,
            timeout=config.SERIAL_TIMEOUT,
            pwrkey_pin=pwrkey,
        )

    if modem and modem.is_connected:
        if modem.init_module():
            log.info("  Modem     : OK")
            modem_ok = True
        else:
            log.warning("  Modem     : WARNING — check SIM / signal")
            modem_ok = True  # modem exists but SIM issue
    elif modem:
        log.error("  Modem     : FAIL — not responding")
        all_ok = False
    else:
        log.error("  Modem     : FAIL — not detected")
        all_ok = False

    # 6) GT-U7 backup GPS
    gtu7_module = None
    if config.GTU7_ENABLED:
        log.info("  GPS (GT-U7): detecting...")
        gtu7_module = GTU7(
            port=config.GTU7_PORT,
            baud=config.GTU7_BAUD,
            timeout=config.GTU7_TIMEOUT,
        )
        if gtu7_module.warmup_check(duration=2.0):
            log.info("  GPS (GT-U7): OK")
        else:
            log.error("  GPS (GT-U7): FAIL — not detected")
            gtu7_module.disable()
            gtu7_module = None
    else:
        log.warning("  GPS (GT-U7): disabled in config")

    # 7) Start background GPS poller (24/7 live tracking)
    gps_poller = None
    if config.GPS_BG_ENABLED and (modem or gtu7_module):
        gps_poller = GPSPoller(
            modem=modem,
            gtu7_module=gtu7_module,
            poll_interval=config.GPS_BG_POLL_INTERVAL,
        )
        gps_poller.start()
        log.info("  GPS Poller: LIVE (background)")
    else:
        log.warning("  GPS Poller: disabled")

    # Ensure buzzer is definitely off after warm-up
    buzzer.buzzer_off()

    # ── Status summary ──────────────────────────────────────────────────
    log.info("---------------------------------")
    log.info(f"Owner:    {config.OWNER_NAME}")
    log.info(f"Contacts: {len(config.CONTACTS)}")
    for c in config.CONTACTS:
        log.info(f"  • {c['name']} ({c['number']})")
    log.info(f"Log file: {config.LOG_FILE}")
    log.info("---------------------------------")

    if all_ok:
        log.info("All components OK — System Ready.")
        log.info("Hold button 3s to arm.")
        led.solid_green()
        buzzer.double_beep()
    elif modem_ok:
        log.warning("System Ready (modem has warnings).")
        log.info("Hold button 3s to arm.")
        led.solid_green()
        buzzer.double_beep()
    else:
        log.error("WARNING: Modem not available!")
        log.error("SMS/GPS will not work until modem is connected.")
        log.warning("System running in limited mode — hold button 3s to arm.")
        led.blink_red(interval=1.0)
        buzzer.fail_sound()
        buzzer.buzzer_off()   # guarantee buzzer is silent after fail tone
    return modem, gtu7_module, gps_poller


def loop(modem, gtu7_module=None, gps_poller=None):
    """
    Main polling loop. Checks for button press and triggers panic sequence.
    Sends periodic keepalive AT pings so the module never goes stale.
    Port of: loop() in main.ino (lines 172-178)
    """
    last_keepalive = time.time()

    while True:
        if GPIO.input(config.PIN_BUTTON) == GPIO.LOW:
            time.sleep(config.DEBOUNCE_DELAY)
            if GPIO.input(config.PIN_BUTTON) == GPIO.LOW:
                panic.handle_panic_sequence(modem, gtu7_module, gps_poller)
                # Re-establish idle state after sequence completes
                led.solid_green()
                last_keepalive = time.time()

        # Periodic keepalive — prevents the A7670E from becoming
        # unresponsive after long idle periods.
        if (modem and config.KEEPALIVE_INTERVAL > 0
                and (time.time() - last_keepalive) >= config.KEEPALIVE_INTERVAL):
            resp = modem.send_command("AT", timeout=2.0)
            if "OK" not in resp:
                log.warning("[KEEPALIVE] Module unresponsive — waking...")
                modem.wake(max_attempts=config.MODEM_WAKE_ATTEMPTS)
            last_keepalive = time.time()

        time.sleep(0.01)  # ~10ms loop rate, same as delay(10) in Arduino


def main():
    """Application entry point with clean shutdown."""
    modem = None
    gtu7_module = None
    gps_poller = None
    try:
        modem, gtu7_module, gps_poller = setup()
        loop(modem, gtu7_module, gps_poller)

    except KeyboardInterrupt:
        log.warning("Shutdown requested (Ctrl+C)")

    except Exception as e:
        log.critical(f"FATAL ERROR: {e}")
        import traceback
        traceback.print_exc()

    finally:
        log.info("Cleaning up...")
        if gps_poller:
            gps_poller.stop()
        led.all_off()
        buzzer.buzzer_off()
        if gtu7_module:
            gtu7_module.close()
        if modem:
            modem.disable_gnss()
            modem.close()
        GPIO.cleanup()
        log.info("Goodbye.")
        sys.exit(0)


if __name__ == "__main__":
    main()
