// ============================================================
// LED Test — Test Green and Red LEDs
// ============================================================

#define GREEN_LED  5   // D5
#define RED_LED    6   // D6

void setup() {
  pinMode(GREEN_LED, OUTPUT);
  pinMode(RED_LED, OUTPUT);
  
  Serial.begin(9600);
  Serial.println("=== LED Test Started ===");
  Serial.println("Testing Green and Red LEDs...");
}

void loop() {
  // Test 1: Green LED ON
  Serial.println("Green LED ON");
  digitalWrite(GREEN_LED, HIGH);
  digitalWrite(RED_LED, LOW);
  delay(1000);
  
  // Test 2: Red LED ON
  Serial.println("Red LED ON");
  digitalWrite(GREEN_LED, LOW);
  digitalWrite(RED_LED, HIGH);
  delay(1000);
  
  // Test 3: Both ON
  Serial.println("Both LEDs ON");
  digitalWrite(GREEN_LED, HIGH);
  digitalWrite(RED_LED, HIGH);
  delay(1000);
  
  // Test 4: Both OFF
  Serial.println("Both LEDs OFF");
  digitalWrite(GREEN_LED, LOW);
  digitalWrite(RED_LED, LOW);
  delay(1000);
  
  // Test 5: Blink green rapidly
  Serial.println("Green LED blinking rapidly (5x)");
  for (int i = 0; i < 5; i++) {
    digitalWrite(GREEN_LED, HIGH);
    delay(100);
    digitalWrite(GREEN_LED, LOW);
    delay(100);
  }
  delay(500);
  
  // Test 6: Blink red slowly
  Serial.println("Red LED blinking slowly (3x)");
  for (int i = 0; i < 3; i++) {
    digitalWrite(RED_LED, HIGH);
    delay(500);
    digitalWrite(RED_LED, LOW);
    delay(500);
  }
  
  Serial.println("--- Test cycle complete ---\n");
  delay(2000);
}
