// ============================================================
// SIM800L Test — Test GSM module and SMS sending
// ============================================================
// WIRING (match labels on your SIM800L module):
//   SIM800L TXD pin → Arduino D8 (Arduino receives from SIM800L)
//   SIM800L RXD pin → Arduino D9 via voltage divider (Arduino sends to SIM800L)
//   SIM800L GND → Arduino GND (common ground)
//   SIM800L VCC → Separate 5V power supply (NOT from Arduino!)
//   Add 1000µF capacitor across SIM800L VCC and GND
//
// OPTIONAL PINS (usually NOT needed):
//   RST - Leave disconnected (module auto-resets on power-up)
//         Only connect to Arduino pin if you need software reset
//   VDD/VCCIO - Usually internal, leave disconnected
// 
// VOLTAGE DIVIDER for Arduino D9 → SIM800L RXD:
//   Arduino D9 → 1kΩ resistor → SIM800L RXD
//   SIM800L RXD → 2kΩ resistor → GND
//   (This converts 5V from Arduino to 3.3V for SIM800L)
// ============================================================

#include <SoftwareSerial.h>

// Pin definitions - match the physical connections above
#define GSM_RX_PIN  8   // Arduino D8 ← SIM800L TXD pin
#define GSM_TX_PIN  9   // Arduino D9 → SIM800L RXD pin (via divider)

SoftwareSerial gsmSerial(GSM_RX_PIN, GSM_TX_PIN);

// === CONFIGURATION ===
const char TEST_NUMBER[] = "+639391445673";  // Change to your test number
const char TEST_MESSAGE[] = "Hello from SIM800L! Test OK.";

void setup() {
  Serial.begin(9600);
  gsmSerial.begin(9600);
  
  Serial.println(F("=== SIM800L Test Started ==="));
  Serial.println(F("Make sure:"));
  Serial.println(F("- SIM card inserted (no PIN lock)"));
  Serial.println(F("- SIM has load"));
  Serial.println(F("- Separate 5V power for SIM800L"));
  Serial.println(F("- 1000uF capacitor on VCC/GND"));
  Serial.println();
  
  delay(3000);
  
  // Test 1: Check communication
  Serial.println(F("======================================"));
  Serial.println(F("Test 1: Module Communication (AT)"));
  Serial.println(F("======================================"));
  gsmSerial.println(F("AT"));
  delay(1000);
  if (checkResponse()) {
    Serial.println(F("OK - Module responding"));
  } else {
    Serial.println(F("ERROR: No response"));
    Serial.println(F("- SIM800L not powered"));
    Serial.println(F("- Wrong TX/RX wiring"));
  }
  
  // Test 2: Module info
  Serial.println(F("\n======================================"));
  Serial.println(F("Test 2: Module Information"));
  Serial.println(F("======================================"));
  gsmSerial.println(F("ATI"));
  delay(1000);
  printResponse();
  
  // Test 3: Check SIM card
  Serial.println(F("\n======================================"));
  Serial.println(F("Test 3: SIM Card Status"));
  Serial.println(F("======================================"));
  gsmSerial.println(F("AT+CPIN?"));
  delay(1000);
  checkSIMStatus();
  
  // Test 4: Get phone number
  Serial.println(F("\n======================================"));
  Serial.println(F("Test 4: Phone Number (AT+CNUM)"));
  Serial.println(F("======================================"));
  gsmSerial.println(F("AT+CNUM"));
  delay(1500);
  printResponse();
  
  // Test 5: Signal strength
  Serial.println(F("\n======================================"));
  Serial.println(F("Test 5: Signal Strength"));
  Serial.println(F("======================================"));
  gsmSerial.println(F("AT+CSQ"));
  delay(1000);
  checkSignal();
  
  // Test 6: Network registration
  Serial.println(F("\n======================================"));
  Serial.println(F("Test 6: Network Registration"));
  Serial.println(F("======================================"));
  gsmSerial.println(F("AT+CREG?"));
  delay(1000);
  checkRegistration();
  
  // Test 7: Get operator
  Serial.println(F("\n======================================"));
  Serial.println(F("Test 7: Network Operator"));
  Serial.println(F("======================================"));
  gsmSerial.println(F("AT+COPS?"));
  delay(2000);
  printResponse();
  
  // Test 8: SMS mode
  Serial.println(F("\n======================================"));
  Serial.println(F("Test 8: SMS Mode (AT+CMGF=1)"));
  Serial.println(F("======================================"));
  gsmSerial.println(F("AT+CMGF=1"));
  delay(1000);
  if (checkResponse()) {
    Serial.println(F("OK - SMS text mode set"));
  }
  
  Serial.println(F("\n======================================"));
  Serial.println(F("=== DIAGNOSTIC COMPLETE ==="));
  Serial.println(F("======================================"));
  Serial.println(F("\nCommands:"));
  Serial.println(F("'send' - Send test SMS"));
  Serial.println(F("'signal' - Check signal"));
  Serial.println(F("'status' - Network status"));
  Serial.println(F("======================================\n"));
}

void loop() {
  // Forward from Arduino Serial to GSM
  if (Serial.available()) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    
    if (cmd.equalsIgnoreCase("send")) {
      sendTestSMS();
    } else if (cmd.equalsIgnoreCase("signal")) {
      Serial.println(F("\n=== Signal Check ==="));
      gsmSerial.println(F("AT+CSQ"));
      delay(1000);
      checkSignal();
    } else if (cmd.equalsIgnoreCase("status")) {
      Serial.println(F("\n=== Network Status ==="));
      gsmSerial.println(F("AT+CREG?"));
      delay(1000);
      printResponse();
    } else if (cmd.length() > 0) {
      Serial.print(F("Sending: "));
      Serial.println(cmd);
      gsmSerial.println(cmd);
      delay(1000);
      printResponse();
    }
  }
  
  // Forward from GSM to Arduino Serial
  if (gsmSerial.available()) {
    Serial.write(gsmSerial.read());
  }
}

// Check if there's a response
bool checkResponse() {
  unsigned long start = millis();
  while (millis() - start < 500) {
    if (gsmSerial.available()) {
      while (gsmSerial.available()) Serial.write(gsmSerial.read());
      return true;
    }
  }
  return false;
}

// Print response from module
void printResponse() {
  unsigned long start = millis();
  while (millis() - start < 500) {
    while (gsmSerial.available()) {
      Serial.write(gsmSerial.read());
    }
  }
  Serial.println();
}

// Check SIM status
void checkSIMStatus() {
  char buf[50];
  int idx = 0;
  unsigned long start = millis();
  
  while (millis() - start < 500 && idx < 49) {
    if (gsmSerial.available()) {
      buf[idx++] = gsmSerial.read();
    }
  }
  buf[idx] = '\0';
  
  Serial.println(buf);
  if (strstr(buf, "READY")) {
    Serial.println(F("OK - SIM ready"));
  } else if (strstr(buf, "PIN")) {
    Serial.println(F("ERROR: SIM locked with PIN"));
  } else if (strstr(buf, "NOT")) {
    Serial.println(F("ERROR: SIM not inserted"));
  }
}

// Check signal strength
void checkSignal() {
  char buf[50];
  int idx = 0;
  unsigned long start = millis();
  
  while (millis() - start < 500 && idx < 49) {
    if (gsmSerial.available()) {
      buf[idx++] = gsmSerial.read();
    }
  }
  buf[idx] = '\0';
  
  Serial.println(buf);
  
  // Parse signal
  char* csq = strstr(buf, "+CSQ: ");
  if (csq) {
    int rssi = atoi(csq + 6);
    Serial.print(F("Signal: "));
    if (rssi == 99) {
      Serial.println(F("NO SIGNAL"));
    } else if (rssi >= 15) {
      Serial.print(F("GOOD ("));
      Serial.print(rssi);
      Serial.println(F("/31)"));
    } else if (rssi >= 10) {
      Serial.print(F("FAIR ("));
      Serial.print(rssi);
      Serial.println(F("/31)"));
    } else {
      Serial.print(F("WEAK ("));
      Serial.print(rssi);
      Serial.println(F("/31)"));
    }
  }
}

// Check network registration
void checkRegistration() {
  char buf[50];
  int idx = 0;
  unsigned long start = millis();
  
  while (millis() - start < 500 && idx < 49) {
    if (gsmSerial.available()) {
      buf[idx++] = gsmSerial.read();
    }
  }
  buf[idx] = '\0';
  
  Serial.println(buf);
  if (strstr(buf, ",1")) {
    Serial.println(F("OK - Registered (home)"));
  } else if (strstr(buf, ",5")) {
    Serial.println(F("OK - Registered (roaming)"));
  } else if (strstr(buf, ",2")) {
    Serial.println(F("Searching..."));
  } else {
    Serial.println(F("Not registered"));
  }
}

void sendTestSMS() {
  Serial.println(F("\n=== SENDING TEST SMS ==="));
  
  // Set SMS text mode
  Serial.println(F("Setting SMS mode..."));
  gsmSerial.println(F("AT+CMGF=1"));
  delay(500);
  if (!checkResponse()) {
    Serial.println(F("ERROR: Cannot set SMS mode"));
    return;
  }
  Serial.println(F("OK"));
  
  // Set recipient
  Serial.print(F("Sending to: "));
  Serial.println(TEST_NUMBER);
  gsmSerial.print(F("AT+CMGS=\""));
  gsmSerial.print(TEST_NUMBER);
  gsmSerial.println(F("\""));
  delay(1000);
  
  // Wait for '>' prompt
  Serial.println(F("Waiting for prompt..."));
  if (!waitForPrompt()) {
    Serial.println(F("ERROR: No prompt"));
    Serial.println(F("- No credit on SIM"));
    Serial.println(F("- Not registered"));
    gsmSerial.write(0x1B);  // ESC
    delay(500);
    return;
  }
  
  Serial.println(F("Sending message..."));
  gsmSerial.println(TEST_MESSAGE);
  delay(100);
  
  // Send Ctrl+Z
  gsmSerial.write(0x1A);
  Serial.println(F("Waiting for confirmation..."));
  
  // Wait for response
  unsigned long start = millis();
  bool gotCMGS = false;
  bool gotOK = false;
  
  while (millis() - start < 15000) {
    if (gsmSerial.available()) {
      char c = gsmSerial.read();
      Serial.write(c);
      if (c == 'G') gotCMGS = true;  // Simple check for +CMGS
      if (c == 'K' && gotCMGS) gotOK = true;  // OK after CMGS
    }
    if (gotOK) break;
    delay(10);
  }
  
  Serial.println();
  if (gotOK) {
    Serial.println(F("=== SMS SENT OK ==="));
  } else {
    Serial.println(F("=== SEND FAILED ==="));
    Serial.println(F("Check if SMS received anyway"));
  }
  Serial.println();
}

bool waitForPrompt() {
  unsigned long start = millis();
  
  while (millis() - start < 5000) {
    if (gsmSerial.available()) {
      char c = gsmSerial.read();
      Serial.write(c);
      if (c == '>') return true;
      if (c == 'E') return false;  // ERROR
    }
    delay(10);
  }
  return false;
}
