// ============================================================
// Buzzer Relay Test — Test Active LOW relay with buzzer
// ============================================================

#define RELAY_PIN  7   // D7 — Active LOW relay

void buzzerOn()  { digitalWrite(RELAY_PIN, LOW); }   // Active LOW
void buzzerOff() { digitalWrite(RELAY_PIN, HIGH); }

void setup() {
  pinMode(RELAY_PIN, OUTPUT);
  buzzerOff();  // Start with buzzer OFF
  
  Serial.begin(9600);
  Serial.println("=== Buzzer Relay Test Started ===");
  Serial.println("Active LOW relay on D7");
  delay(2000);
}

void loop() {
  // Test 1: Short beep
  Serial.println("Test 1: Short beep (200ms)");
  buzzerOn();
  delay(200);
  buzzerOff();
  delay(1000);
  
  // Test 2: Long beep
  Serial.println("Test 2: Long beep (800ms)");
  buzzerOn();
  delay(800);
  buzzerOff();
  delay(1000);
  
  // Test 3: Double beep
  Serial.println("Test 3: Double beep");
  buzzerOn();
  delay(100);
  buzzerOff();
  delay(100);
  buzzerOn();
  delay(100);
  buzzerOff();
  delay(1000);
  
  // Test 4: Short-Long pattern (success)
  Serial.println("Test 4: Short-Long pattern");
  buzzerOn();
  delay(200);
  buzzerOff();
  delay(100);
  buzzerOn();
  delay(500);
  buzzerOff();
  delay(1000);
  
  // Test 5: Three short ticks
  Serial.println("Test 5: Three ticks (1 per second)");
  for (int i = 0; i < 3; i++) {
    buzzerOn();
    delay(50);
    buzzerOff();
    Serial.print("  Tick ");
    Serial.println(i + 1);
    delay(950);
  }
  
  Serial.println("--- Test cycle complete ---\n");
  delay(3000);
}
