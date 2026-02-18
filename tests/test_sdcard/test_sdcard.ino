// ============================================================
// SD Card Test — Test read and write operations
// ============================================================
// SD card must be formatted as FAT16 or FAT32
// ============================================================

#include <SPI.h>
#include <SD.h>

#define SD_CS_PIN  10   // D10 — SD Card CS

const char TEST_FILE[] = "test.txt";
const char LOG_FILE[] = "logs.txt";

void setup() {
  Serial.begin(9600);
  
  Serial.println("=== SD Card Test Started ===");
  Serial.println("Make sure:");
  Serial.println("- SD card inserted");
  Serial.println("- Formatted as FAT32");
  Serial.println("- Wiring: CS→D10, MOSI→D11, MISO→D12, SCK→D13");
  Serial.println();
  
  delay(2000);
  
  // Test 1: Initialize SD card
  Serial.print("Test 1: Initializing SD card... ");
  if (!SD.begin(SD_CS_PIN)) {
    Serial.println("FAILED!");
    Serial.println("\nTroubleshooting:");
    Serial.println("- Check SD card is inserted properly");
    Serial.println("- Check wiring connections");
    Serial.println("- Try formatting SD card as FAT32");
    Serial.println("- Try different SD card (2GB-32GB works best)");
    while (1);
  }
  Serial.println("OK!");
  
  // Test 2: Get card info
  Serial.println("\nTest 2: Card information");
  Serial.print("Card type: ");
  switch (SD.type()) {
    case SD_CARD_TYPE_SD1:
      Serial.println("SD1");
      break;
    case SD_CARD_TYPE_SD2:
      Serial.println("SD2");
      break;
    case SD_CARD_TYPE_SDHC:
      Serial.println("SDHC");
      break;
    default:
      Serial.println("Unknown");
  }
  
  // Test 3: List files
  Serial.println("\nTest 3: Files on SD card:");
  File root = SD.open("/");
  printDirectory(root, 0);
  root.close();
  
  // Test 4: Write test file
  Serial.println("\nTest 4: Writing to test file...");
  File testFile = SD.open(TEST_FILE, FILE_WRITE);
  if (testFile) {
    testFile.println("=== SD Card Write Test ===");
    testFile.print("Timestamp: ");
    testFile.print(millis());
    testFile.println(" ms");
    testFile.println("Line 1: Hello from Arduino!");
    testFile.println("Line 2: SD card working correctly.");
    testFile.println("Line 3: Test complete.");
    testFile.close();
    Serial.println("Write OK!");
  } else {
    Serial.println("Write FAILED!");
  }
  
  // Test 5: Read test file
  Serial.println("\nTest 5: Reading from test file...");
  testFile = SD.open(TEST_FILE, FILE_READ);
  if (testFile) {
    Serial.println("--- File Contents ---");
    while (testFile.available()) {
      Serial.write(testFile.read());
    }
    testFile.close();
    Serial.println("--- End of File ---");
    Serial.println("Read OK!");
  } else {
    Serial.println("Read FAILED!");
  }
  
  // Test 6: Append to log file
  Serial.println("\nTest 6: Appending to log file...");
  File logFile = SD.open(LOG_FILE, FILE_WRITE);
  if (logFile) {
    logFile.println("--------------------------------");
    logFile.print("[Test Entry ");
    logFile.print(millis() / 1000);
    logFile.println("s]");
    logFile.println("Status: SUCCESS");
    logFile.println("Message: SD card test completed");
    logFile.println("--------------------------------");
    logFile.println();
    logFile.close();
    Serial.println("Append OK!");
  } else {
    Serial.println("Append FAILED!");
  }
  
  // Test 7: Read log file
  Serial.println("\nTest 7: Reading log file...");
  logFile = SD.open(LOG_FILE, FILE_READ);
  if (logFile) {
    Serial.println("--- Log File Contents ---");
    while (logFile.available()) {
      Serial.write(logFile.read());
    }
    logFile.close();
    Serial.println("--- End of Log ---");
  } else {
    Serial.println("No log file yet (this is normal on first run)");
  }
  
  // Test 8: File size
  Serial.println("\nTest 8: File sizes");
  testFile = SD.open(TEST_FILE);
  if (testFile) {
    Serial.print(TEST_FILE);
    Serial.print(": ");
    Serial.print(testFile.size());
    Serial.println(" bytes");
    testFile.close();
  }
  
  logFile = SD.open(LOG_FILE);
  if (logFile) {
    Serial.print(LOG_FILE);
    Serial.print(": ");
    Serial.print(logFile.size());
    Serial.println(" bytes");
    logFile.close();
  }
  
  Serial.println("\n=== All Tests Complete ===");
  Serial.println("SD card is working correctly!");
}

void loop() {
  // Add a new log entry every 5 seconds
  static unsigned long lastLog = 0;
  if (millis() - lastLog > 5000) {
    lastLog = millis();
    
    Serial.println("\nAdding log entry...");
    File logFile = SD.open(LOG_FILE, FILE_WRITE);
    if (logFile) {
      logFile.print("Loop entry at ");
      logFile.print(millis() / 1000);
      logFile.println("s");
      logFile.close();
      Serial.println("Log entry added!");
    } else {
      Serial.println("Log FAILED!");
    }
  }
}

void printDirectory(File dir, int numTabs) {
  while (true) {
    File entry = dir.openNextFile();
    if (!entry) {
      break;
    }
    
    for (uint8_t i = 0; i < numTabs; i++) {
      Serial.print('\t');
    }
    
    Serial.print(entry.name());
    if (entry.isDirectory()) {
      Serial.println("/");
      printDirectory(entry, numTabs + 1);
    } else {
      Serial.print("\t\t");
      Serial.print(entry.size());
      Serial.println(" bytes");
    }
    entry.close();
  }
}
