"""
Buzzer/Relay Control Helpers
=============================
Controls the active buzzer via relay module on GPIO (Active LOW by default).
Direct port of BUZZER HELPERS section in main.ino (lines 86-112).

All timing values match the Arduino original exactly.
"""

import RPi.GPIO as GPIO
import time
from config import PIN_RELAY, RELAY_ACTIVE_LOW


def setup():
    """
    Initialize relay pin as output, buzzer OFF.
    Maps to: pinMode(RELAY_PIN, OUTPUT); buzzerOff(); in main.ino setup()
    """
    # Set initial state immediately so the relay never glitches ON during boot.
    # Active-LOW relay: HIGH = off.  Active-HIGH relay: LOW = off.
    init_state = GPIO.HIGH if RELAY_ACTIVE_LOW else GPIO.LOW
    GPIO.setup(PIN_RELAY, GPIO.OUT, initial=init_state)
    buzzer_off()


def buzzer_on():
    """
    Activate buzzer (relay triggered).
    Port of: buzzerOn() in main.ino — digitalWrite(RELAY_PIN, LOW)
    """
    if RELAY_ACTIVE_LOW:
        GPIO.output(PIN_RELAY, GPIO.LOW)
    else:
        GPIO.output(PIN_RELAY, GPIO.HIGH)


def buzzer_off():
    """
    Deactivate buzzer (relay released).
    Port of: buzzerOff() in main.ino — digitalWrite(RELAY_PIN, HIGH)
    """
    if RELAY_ACTIVE_LOW:
        GPIO.output(PIN_RELAY, GPIO.HIGH)
    else:
        GPIO.output(PIN_RELAY, GPIO.LOW)


def tick():
    """
    Short 50ms beep.
    Port of: buzzerTick() in main.ino
    """
    buzzer_on()
    time.sleep(0.05)
    buzzer_off()


def double_beep():
    """
    Two 100ms beeps with 100ms gap.
    Port of: buzzerDoubleBeep() in main.ino
    """
    buzzer_on()
    time.sleep(0.1)
    buzzer_off()
    time.sleep(0.1)
    buzzer_on()
    time.sleep(0.1)
    buzzer_off()


def cancel_sound():
    """
    Two 400ms beeps with 150ms gap.
    Port of: buzzerCancelSound() in main.ino
    """
    buzzer_on()
    time.sleep(0.4)
    buzzer_off()
    time.sleep(0.15)
    buzzer_on()
    time.sleep(0.4)
    buzzer_off()


def success_sound():
    """
    200ms beep + 100ms pause + 500ms beep.
    Port of: buzzerSuccessSound() in main.ino
    """
    buzzer_on()
    time.sleep(0.2)
    buzzer_off()
    time.sleep(0.1)
    buzzer_on()
    time.sleep(0.5)
    buzzer_off()


def fail_sound():
    """
    Single 800ms buzz.
    Port of: buzzerFailSound() in main.ino
    """
    buzzer_on()
    time.sleep(0.8)
    buzzer_off()
