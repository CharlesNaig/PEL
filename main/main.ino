// ============================================================
// Panic Button Emergency Locator — Production Prototype
// ============================================================
// Based on: test_v1/test_v1.ino (button, buzzer, LED logic)
// Plan:     .github/prompts/plan-panicButtonEmergencyLocator.prompt.md
// ============================================================

#include <SoftwareSerial.h>
#include <TinyGPS++.h>
#include <SPI.h>
#include <SD.h>

// ============================================================
// USER CONFIGURATION — Change these before deployment
// ============================================================

// Name of the person carrying the device
const char OWNER_NAME[] = "Charles";

// Emergency contacts — names and numbers
const char* contactNames[] = {
  "Andrew Felipe",    // e.g. "Mama"
  "Naig",    // e.g. "Papa"
};
const char* emergencyNumbers[] = {
  "+639154693904",     // Contact 1 number
  "+639391445673",     // Contact 2 number
};
const int NUM_CONTACTS = 2;

// GPS settings
#define GPS_TIMEOUT        30000  // 30 seconds to acquire GPS fix
#define GPS_BAUD           9600   // GPS module baud rate

// GSM settings
#define GSM_BAUD           9600   // SIM800L baud rate
#define GSM_RETRY_COUNT    3      // Number of SMS send retries

// SD Card log file
const char LOG_FILE[] = "logs.txt";

// ============================================================
// PIN CONFIGURATION — Match your wiring
// ============================================================

// GPS Module (SoftwareSerial)
#define GPS_TX_PIN    2    // D2 — GPS TX → Arduino RX
#define GPS_RX_PIN    3    // D3 — GPS RX → Arduino TX

// Button
#define BTN_PIN       4    // D4 — Push button (INPUT_PULLUP)

// LED Indicators
#define GREEN_LED     5    // D5 — Green LED (success)
#define RED_LED       6    // D6 — Red LED (error/arming)

// Relay (Active LOW — controls active buzzer)
#define RELAY_PIN     7    // D7 — Relay IN

// SIM800L (SoftwareSerial)
#define GSM_TX_PIN    8    // D8 — SIM800L TXD → Arduino RX
#define GSM_RX_PIN    9    // D9 — SIM800L RXD → Arduino TX (via voltage divider)

// SD Card (SPI)
#define SD_CS_PIN     10   // D10 — SD Card CS

// ============================================================
// TIMING CONSTANTS
// ============================================================

#define ARM_HOLD_TIME      3000   // 3s hold to arm
#define CANCEL_WINDOW      3000   // 3s window to cancel
#define DEBOUNCE_DELAY     50     // 50ms debounce

// ============================================================
// GLOBAL OBJECTS
// ============================================================

SoftwareSerial gpsSerial(GPS_TX_PIN, GPS_RX_PIN);
SoftwareSerial gsmSerial(GSM_TX_PIN, GSM_RX_PIN);
TinyGPSPlus gps;

bool sdReady = false;

// ============================================================
// BUZZER HELPERS (Active LOW relay)
// ============================================================

void buzzerOn()  { digitalWrite(RELAY_PIN, LOW); }
void buzzerOff() { digitalWrite(RELAY_PIN, HIGH); }

void allOff() {
  buzzerOff();
  digitalWrite(GREEN_LED, LOW);
  digitalWrite(RED_LED, LOW);
}

void buzzerTick() {
  buzzerOn(); delay(50); buzzerOff();
}

void buzzerDoubleBeep() {
  buzzerOn(); delay(100); buzzerOff();
  delay(100);
  buzzerOn(); delay(100); buzzerOff();
}

void buzzerCancelSound() {
  buzzerOn(); delay(400); buzzerOff();
  delay(150);
  buzzerOn(); delay(400); buzzerOff();
}

void buzzerSuccessSound() {
  buzzerOn(); delay(200); buzzerOff();
  delay(100);
  buzzerOn(); delay(500); buzzerOff();
}

void buzzerFailSound() {
  buzzerOn(); delay(800); buzzerOff();
}

// ============================================================
// SETUP
// ============================================================

void setup() {
  // Pin modes
  pinMode(BTN_PIN, INPUT_PULLUP);
  pinMode(RELAY_PIN, OUTPUT);
  pinMode(GREEN_LED, OUTPUT);
  pinMode(RED_LED, OUTPUT);

  allOff();

  // Serial monitor
  Serial.begin(9600);
  Serial.println(F("================================="));
  Serial.println(F(" Panic Button Emergency Locator"));
  Serial.println(F("================================="));

  // Initialize SD card
  Serial.print(F("SD Card: "));
  if (SD.begin(SD_CS_PIN)) {
    sdReady = true;
    Serial.println(F("OK"));
  } else {
    sdReady = false;
    Serial.println(F("FAILED — logging disabled"));
  }

  // Initialize GPS
  gpsSerial.begin(GPS_BAUD);
  Serial.println(F("GPS: Initialized"));

  // Initialize GSM
  gsmSerial.begin(GSM_BAUD);
  delay(1000);
  Serial.print(F("GSM: "));
  if (initGSM()) {
    Serial.println(F("OK"));
  } else {
    Serial.println(F("WARNING — check SIM card"));
  }

  Serial.println(F("---------------------------------"));
  Serial.println(F("System Ready. Hold button 3s to arm."));
  Serial.println();
}

// ============================================================
// MAIN LOOP
// ============================================================

void loop() {
  if (digitalRead(BTN_PIN) == LOW) {
    delay(DEBOUNCE_DELAY);
    if (digitalRead(BTN_PIN) == LOW) {
      handlePanicSequence();
    }
  }
}

// ============================================================
// PANIC SEQUENCE — 4 Phases
// ============================================================

void handlePanicSequence() {
  Serial.println(F("Button held — arming..."));

  // -----------------------------------------------
  // PHASE 1: Hold to Arm (3 seconds)
  // Red LED blinks fast, buzzer ticks each second
  // -----------------------------------------------
  unsigned long holdStart = millis();
  int tickCount = 0;
  bool armed = false;

  while (digitalRead(BTN_PIN) == LOW) {
    unsigned long elapsed = millis() - holdStart;

    // Blink red LED rapidly (every 200ms)
    digitalWrite(RED_LED, (millis() / 200) % 2 ? HIGH : LOW);

    // Buzzer tick once per second
    if ((elapsed / 1000) > (unsigned long)tickCount && tickCount < 3) {
      tickCount++;
      buzzerTick();
      Serial.print(F("Arming... "));
      Serial.print(tickCount);
      Serial.println(F("/3"));
    }

    // Armed after 3 seconds
    if (elapsed >= ARM_HOLD_TIME) {
      armed = true;
      break;
    }

    delay(10);
  }

  allOff();

  if (!armed) {
    Serial.println(F("Cancelled — released too early."));
    return;
  }

  // -----------------------------------------------
  // PHASE 2: Armed Confirmation
  // Double beep + both LEDs flash
  // -----------------------------------------------
  Serial.println(F("ARMED! Press button within 3s to cancel."));

  digitalWrite(GREEN_LED, HIGH);
  digitalWrite(RED_LED, HIGH);
  buzzerDoubleBeep();
  delay(200);
  allOff();

  // Wait for button release
  while (digitalRead(BTN_PIN) == LOW) { delay(10); }
  delay(100);

  // -----------------------------------------------
  // PHASE 3: Cancellation Window (3 seconds)
  // Green LED blinks slowly, press button to cancel
  // -----------------------------------------------
  Serial.println(F("Cancel window open (3 seconds)..."));

  unsigned long cancelStart = millis();
  bool cancelled = false;

  while (millis() - cancelStart < CANCEL_WINDOW) {
    // Blink green LED slowly (every 500ms)
    digitalWrite(GREEN_LED, (millis() / 500) % 2 ? HIGH : LOW);

    // Check for cancel press
    if (digitalRead(BTN_PIN) == LOW) {
      delay(DEBOUNCE_DELAY);
      if (digitalRead(BTN_PIN) == LOW) {
        cancelled = true;
        while (digitalRead(BTN_PIN) == LOW) { delay(10); }
        break;
      }
    }

    delay(10);
  }

  allOff();

  if (cancelled) {
    Serial.println(F("CANCELLED by user."));
    digitalWrite(RED_LED, HIGH);
    buzzerCancelSound();
    delay(500);
    allOff();
    logToSD("CANCELLED", 0.0, 0.0);
    Serial.println(F("System Idle."));
    return;
  }

  // -----------------------------------------------
  // PHASE 4: Execute Panic Routine
  // -----------------------------------------------
  Serial.println();
  Serial.println(F("========================================="));
  Serial.println(F(">>> EXECUTING PANIC ROUTINE <<<"));
  Serial.println(F("========================================="));
  executePanic();
}

// ============================================================
// EXECUTE PANIC — GPS → SMS → SD Log → Feedback
// ============================================================

void executePanic() {
  // Indicate processing: green LED solid
  digitalWrite(GREEN_LED, HIGH);
  buzzerTick();

  // --- Step 1: Acquire GPS ---
  Serial.println();
  Serial.println(F("[STEP 1/4] GPS ACQUISITION"));
  Serial.println(F("-----------------------------------------"));
  Serial.println(F("Searching for GPS satellites..."));
  Serial.println(F("Timeout: 30 seconds"));
  Serial.println(F("Green LED blinks while searching..."));
  Serial.println();

  float lat = 0.0, lng = 0.0;
  bool gpsOk = acquireGPS(&lat, &lng);

  if (!gpsOk) {
    // GPS FAILED
    Serial.println();
    Serial.println(F("✗ GPS TIMEOUT — No satellites found"));
    Serial.println(F("  Possible causes:"));
    Serial.println(F("  - Testing indoors (GPS needs clear sky)"));
    Serial.println(F("  - GPS antenna not connected"));
    Serial.println(F("  - GPS module not powered"));
    Serial.println(F("-----------------------------------------"));
    allOff();
    digitalWrite(RED_LED, HIGH);
    buzzerFailSound();
    logToSD("FAILED — GPS Timeout", 0.0, 0.0);
    delay(500);
    allOff();
    Serial.println(F("System Idle."));
    Serial.println(F("=========================================\n"));
    return;
  }

  Serial.println();
  Serial.println(F("✓ GPS FIX ACQUIRED!"));
  Serial.print(F("  Latitude:  "));
  Serial.println(lat, 6);
  Serial.print(F("  Longitude: "));
  Serial.println(lng, 6);
  Serial.println(F("-----------------------------------------"));

  // --- Step 2: Send SMS to all contacts ---
  Serial.println();
  Serial.println(F("[STEP 2/4] SMS TRANSMISSION"));
  Serial.println(F("-----------------------------------------"));

  // Build Google Maps link
  char mapLink[60];
  buildMapLink(lat, lng, mapLink, sizeof(mapLink));
  
  Serial.print(F("Maps Link: "));
  Serial.println(mapLink);
  Serial.println();
  Serial.print(F("Sending to "));
  Serial.print(NUM_CONTACTS);
  Serial.println(F(" emergency contacts..."));

  bool smsOk = false;
  for (int i = 0; i < NUM_CONTACTS; i++) {
    Serial.println();
    Serial.print(F("  ["));
    Serial.print(i + 1);
    Serial.print(F("/"));
    Serial.print(NUM_CONTACTS);
    Serial.print(F("] "));
    Serial.print(contactNames[i]);
    Serial.print(F(" ("));
    Serial.print(emergencyNumbers[i]);
    Serial.println(F(")"));

    bool sent = sendSMS(emergencyNumbers[i], contactNames[i], mapLink);

    if (sent) {
      Serial.println(F("      ✓ SMS SENT"));
      smsOk = true;
    } else {
      Serial.println(F("      ✗ SMS FAILED"));
    }
  }
  
  Serial.println(F("-----------------------------------------"));

  // --- Step 3: Log to SD card ---
  Serial.println();
  Serial.println(F("[STEP 3/4] SD CARD LOGGING"));
  Serial.println(F("-----------------------------------------"));
  if (smsOk) {
    logToSD("SUCCESS", lat, lng);
  } else {
    logToSD("FAILED — SMS Send Error", lat, lng);
  }
  Serial.println(F("-----------------------------------------"));

  // --- Step 4: Feedback ---
  Serial.println();
  Serial.println(F("[STEP 4/4] FINAL STATUS"));
  Serial.println(F("-----------------------------------------"));
  
  allOff();

  if (smsOk) {
    Serial.println(F("✓ PANIC ALERT SENT SUCCESSFULLY"));
    Serial.println(F("  Emergency contacts have been notified"));
    Serial.println(F("  Location shared via SMS"));
    digitalWrite(GREEN_LED, HIGH);
    buzzerSuccessSound();
    delay(500);
  } else {
    Serial.println(F("✗ PANIC ALERT FAILED"));
    Serial.println(F("  Unable to send SMS to contacts"));
    Serial.println(F("  Check SIM card and network signal"));
    digitalWrite(RED_LED, HIGH);
    buzzerFailSound();
    delay(500);
  }

  allOff();
  Serial.println(F("-----------------------------------------"));
  Serial.println(F("System Idle."));
  Serial.println(F("=========================================\n"));
  delay(500);
}

// ============================================================
// GPS ACQUISITION WITH PROGRESS REPORTING
// ============================================================

bool acquireGPS(float* lat, float* lng) {
  gpsSerial.listen();
  unsigned long start = millis();
  unsigned long lastUpdate = 0;
  int lastSatellites = -1;

  while (millis() - start < GPS_TIMEOUT) {
    while (gpsSerial.available() > 0) {
      gps.encode(gpsSerial.read());

      if (gps.location.isUpdated() && gps.location.isValid()) {
        *lat = gps.location.lat();
        *lng = gps.location.lng();
        
        unsigned long elapsed = (millis() - start) / 1000;
        Serial.print(F("  Lock acquired in "));
        Serial.print(elapsed);
        Serial.println(F(" seconds"));
        
        return true;
      }
    }

    // Print progress every 5 seconds
    if (millis() - lastUpdate > 5000) {
      lastUpdate = millis();
      unsigned long elapsed = (millis() - start) / 1000;
      
      Serial.print(F("  Searching... "));
      Serial.print(elapsed);
      Serial.print(F("s / "));
      Serial.print(GPS_TIMEOUT / 1000);
      Serial.print(F("s — Satellites: "));
      
      if (gps.satellites.isValid()) {
        int sats = gps.satellites.value();
        Serial.print(sats);
        if (sats != lastSatellites) {
          if (sats > 0 && sats < 4) {
            Serial.print(F(" (need 4+ for fix)"));
          } else if (sats >= 4) {
            Serial.print(F(" (acquiring fix...)"));
          }
          lastSatellites = sats;
        }
      } else {
        Serial.print(F("0"));
      }
      Serial.println();
    }

    // Blink green LED while waiting
    digitalWrite(GREEN_LED, (millis() / 300) % 2 ? HIGH : LOW);
    delay(1);
  }

  return false;
}

void buildMapLink(float lat, float lng, char* buffer, int bufSize) {
  // Format: https://maps.google.com/?q=LAT,LNG
  dtostrf(lat, 1, 6, buffer);
  char lngStr[15];
  dtostrf(lng, 1, 6, lngStr);

  char temp[60];
  snprintf(temp, sizeof(temp), "https://maps.google.com/?q=%s,%s", buffer, lngStr);
  strncpy(buffer, temp, bufSize - 1);
  buffer[bufSize - 1] = '\0';
}

// ============================================================
// GSM / SMS FUNCTIONS
// ============================================================

bool initGSM() {
  gsmSerial.listen();
  delay(500);

  // Test AT command
  gsmSerial.println(F("AT"));
  delay(500);
  if (!waitForResponse("OK", 2000)) return false;

  // Set SMS text mode
  gsmSerial.println(F("AT+CMGF=1"));
  delay(500);
  if (!waitForResponse("OK", 2000)) return false;

  // Check network registration
  gsmSerial.println(F("AT+CREG?"));
  delay(500);
  // Accept either 0,1 (home) or 0,5 (roaming)
  waitForResponse("OK", 2000);

  return true;
}

bool sendSMS(const char* number, const char* contactName, const char* mapLink) {
  gsmSerial.listen();
  delay(100);

  for (int attempt = 0; attempt < GSM_RETRY_COUNT; attempt++) {
    // Set SMS text mode
    gsmSerial.println(F("AT+CMGF=1"));
    delay(300);
    waitForResponse("OK", 2000);

    // Set recipient
    gsmSerial.print(F("AT+CMGS=\""));
    gsmSerial.print(number);
    gsmSerial.println(F("\""));
    delay(500);

    // Wait for '>' prompt
    if (!waitForResponse(">", 3000)) {
      gsmSerial.write(0x1B);  // ESC to cancel
      delay(500);
      continue;
    }

    // Compose personalized message
    gsmSerial.print(F("EMERGENCY ALERT!\n\nHey "));
    gsmSerial.print(contactName);
    gsmSerial.print(F(", I'm letting you know that the emergency panic button has been pressed by "));
    gsmSerial.print(OWNER_NAME);
    gsmSerial.println(F("."));
    gsmSerial.println();
    gsmSerial.println(F("I've got her location from the GPS device. Here is the Google Maps link:"));
    gsmSerial.println();
    gsmSerial.println(mapLink);
    gsmSerial.println();
    gsmSerial.println(F("Please respond immediately and check on her safety."));

    // Send with Ctrl+Z
    gsmSerial.write(0x1A);
    delay(1000);

    if (waitForResponse("OK", 10000)) {
      return true;
    }

    Serial.print(F("    Retry "));
    Serial.print(attempt + 1);
    Serial.print(F("/"));
    Serial.println(GSM_RETRY_COUNT);
    delay(2000);
  }

  return false;
}

bool waitForResponse(const char* expected, unsigned long timeout) {
  unsigned long start = millis();
  String response = "";

  while (millis() - start < timeout) {
    while (gsmSerial.available()) {
      char c = gsmSerial.read();
      response += c;
    }
    if (response.indexOf(expected) >= 0) {
      return true;
    }
    delay(10);
  }

  return false;
}

// ============================================================
// SD CARD LOGGING
// ============================================================

void logToSD(const char* status, float lat, float lng) {
  if (!sdReady) {
    Serial.println(F("SD: Skipped — card not available"));
    return;
  }

  File logFile = SD.open(LOG_FILE, FILE_WRITE);
  if (!logFile) {
    Serial.println(F("SD: Write FAILED"));
    // Blink red LED 3 times to indicate SD error
    for (int i = 0; i < 3; i++) {
      digitalWrite(RED_LED, HIGH); delay(100);
      digitalWrite(RED_LED, LOW);  delay(100);
    }
    return;
  }

  // Write log entry
  logFile.println(F("--------------------------------"));

  // Timestamp from GPS if available, otherwise uptime
  if (gps.date.isValid() && gps.time.isValid()) {
    logFile.print(F("["));
    logFile.print(gps.date.year());
    logFile.print(F("-"));
    if (gps.date.month() < 10) logFile.print(F("0"));
    logFile.print(gps.date.month());
    logFile.print(F("-"));
    if (gps.date.day() < 10) logFile.print(F("0"));
    logFile.print(gps.date.day());
    logFile.print(F(" "));
    if (gps.time.hour() < 10) logFile.print(F("0"));
    logFile.print(gps.time.hour());
    logFile.print(F(":"));
    if (gps.time.minute() < 10) logFile.print(F("0"));
    logFile.print(gps.time.minute());
    logFile.print(F(":"));
    if (gps.time.second() < 10) logFile.print(F("0"));
    logFile.print(gps.time.second());
    logFile.println(F("]"));
  } else {
    logFile.print(F("[Uptime: "));
    logFile.print(millis() / 1000);
    logFile.println(F("s]"));
  }

  logFile.print(F("Latitude:  "));
  logFile.println(lat, 6);
  logFile.print(F("Longitude: "));
  logFile.println(lng, 6);
  logFile.print(F("Status:    "));
  logFile.println(status);
  logFile.println(F("--------------------------------"));
  logFile.println();

  logFile.close();
  Serial.println(F("SD: Logged OK"));
}
  