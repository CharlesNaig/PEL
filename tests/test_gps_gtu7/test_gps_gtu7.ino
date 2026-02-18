// ============================================================
// GTU-7 GPS Test — Test GPS module and location acquisition
// ============================================================
// Install library: TinyGPS++ (Sketch → Include Library → Manage Libraries)
// ============================================================

#include <SoftwareSerial.h>
#include <TinyGPS++.h>

#define GPS_TX_PIN  2   // D2 — GPS TX → Arduino RX
#define GPS_RX_PIN  3   // D3 — GPS RX → Arduino TX

SoftwareSerial gpsSerial(GPS_TX_PIN, GPS_RX_PIN);
TinyGPSPlus gps;

void setup() {
  Serial.begin(9600);
  gpsSerial.begin(9600);
  
  Serial.println("=== GTU-7 GPS Test Started ===");
  Serial.println("Waiting for GPS data...");
  Serial.println("Go outside with clear sky view for best results.");
  Serial.println("First fix can take 30-60 seconds.\n");
}

void loop() {
  // Read GPS data
  while (gpsSerial.available() > 0) {
    char c = gpsSerial.read();
    gps.encode(c);
    
    // Optionally print raw NMEA data (comment out if too much)
    // Serial.write(c);
  }
  
  // Every 2 seconds, display GPS info
  static unsigned long lastPrint = 0;
  if (millis() - lastPrint > 2000) {
    lastPrint = millis();
    
    Serial.println("=================================");
    
    // Satellites
    Serial.print("Satellites: ");
    if (gps.satellites.isValid()) {
      Serial.println(gps.satellites.value());
    } else {
      Serial.println("0 (searching...)");
    }
    
    // Location
    Serial.print("Location: ");
    if (gps.location.isValid()) {
      Serial.print("VALID — Lat: ");
      Serial.print(gps.location.lat(), 6);
      Serial.print(", Lng: ");
      Serial.println(gps.location.lng(), 6);
      
      // Build Google Maps link
      Serial.print("Maps Link: https://maps.google.com/?q=");
      Serial.print(gps.location.lat(), 6);
      Serial.print(",");
      Serial.println(gps.location.lng(), 6);
    } else {
      Serial.println("NO FIX (waiting for satellites...)");
    }
    
    // Date & Time
    Serial.print("Date/Time: ");
    if (gps.date.isValid() && gps.time.isValid()) {
      Serial.print(gps.date.year());
      Serial.print("-");
      if (gps.date.month() < 10) Serial.print("0");
      Serial.print(gps.date.month());
      Serial.print("-");
      if (gps.date.day() < 10) Serial.print("0");
      Serial.print(gps.date.day());
      Serial.print(" ");
      if (gps.time.hour() < 10) Serial.print("0");
      Serial.print(gps.time.hour());
      Serial.print(":");
      if (gps.time.minute() < 10) Serial.print("0");
      Serial.print(gps.time.minute());
      Serial.print(":");
      if (gps.time.second() < 10) Serial.print("0");
      Serial.println(gps.time.second());
    } else {
      Serial.println("N/A");
    }
    
    // Altitude
    Serial.print("Altitude: ");
    if (gps.altitude.isValid()) {
      Serial.print(gps.altitude.meters());
      Serial.println(" m");
    } else {
      Serial.println("N/A");
    }
    
    // Speed
    Serial.print("Speed: ");
    if (gps.speed.isValid()) {
      Serial.print(gps.speed.kmph());
      Serial.println(" km/h");
    } else {
      Serial.println("N/A");
    }
    
    Serial.println();
  }
  
  // Check if no data received for 5 seconds
  if (millis() > 5000 && gps.charsProcessed() < 10) {
    Serial.println("WARNING: No GPS data received.");
    Serial.println("Check wiring: GPS TX → D2, GPS RX → D3");
    Serial.println("Check power: GPS VCC → 5V, GND → GND");
    delay(5000);
  }
}
