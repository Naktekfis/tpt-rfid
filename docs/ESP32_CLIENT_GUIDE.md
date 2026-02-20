# ESP32 Client Guide - TPT-RFID System

Panduan lengkap programming ESP32 sebagai RFID reader client untuk TPT-RFID system.

---

## Daftar Isi

1. [Overview](#overview)
2. [Hardware Requirements](#hardware-requirements)
3. [Software Setup](#software-setup)
4. [Wiring Diagram](#wiring-diagram)
5. [Arduino Code](#arduino-code)
6. [Configuration](#configuration)
7. [Testing](#testing)
8. [Troubleshooting](#troubleshooting)
9. [Advanced Features](#advanced-features)

---

## Overview

ESP32 bertugas membaca RFID cards/tags dan mengirim data ke server Flask via MQTT. System mendukung multiple ESP32 untuk scalability.

### Architecture

```
┌──────────────┐
│ RFID Card/Tag│
└──────┬───────┘
       │ (13.56MHz)
       ▼
┌──────────────┐     WiFi      ┌────────────────┐
│ MFRC522      │◄──────────────┤    ESP32       │
│ RFID Reader  │                │  Dev Board     │
└──────────────┘                └────────┬───────┘
                                         │ MQTT
                                         │ (WiFi)
                                         ▼
                                  ┌──────────────┐
                                  │  Mosquitto   │
                                  │    Broker    │
                                  │ (Raspberry   │
                                  │      Pi)     │
                                  └──────┬───────┘
                                         │
                                         ▼
                                  ┌──────────────┐
                                  │  Flask App   │
                                  │  (Server)    │
                                  └──────────────┘
```

### Payload Format

ESP32 publish JSON ke topic `rfid/scan`:

```json
{
  "rfid_uid": "04A1B2C3D4E5F6",
  "reader_id": "esp32_01",
  "timestamp": "2024-01-15T10:30:45Z"
}
```

---

## Hardware Requirements

### ESP32 Board

**Recommended:**
- ESP32 DevKit V1 (30 pins)
- ESP32-WROOM-32

**Specifications:**
- WiFi: 802.11 b/g/n
- Voltage: 3.3V (tolerates 5V on VIN)
- GPIO pins: 30+
- Built-in WiFi and Bluetooth

### RFID Reader Module

**Model:** MFRC522

**Specifications:**
- Frequency: 13.56MHz
- Interface: SPI
- Voltage: 3.3V
- Read distance: ~3-5cm
- Supported cards: MIFARE Classic 1K, 4K

### RFID Cards/Tags

**Types:**
- ISO14443A cards (credit card size)
- Key fobs
- Stickers

---

## Software Setup

### Step 1: Install Arduino IDE

**Download:** https://www.arduino.cc/en/software

**Supported OS:**
- Windows 10/11
- macOS 10.14+
- Linux (Ubuntu, Debian, etc.)

### Step 2: Install ESP32 Board Support

1. Open Arduino IDE
2. Go to **File → Preferences**
3. Add board manager URL:
   ```
   https://dl.espressif.com/dl/package_esp32_index.json
   ```
4. Go to **Tools → Board → Boards Manager**
5. Search "esp32"
6. Install "esp32 by Espressif Systems" (latest version)

### Step 3: Install Required Libraries

Go to **Sketch → Include Library → Manage Libraries** dan install:

| Library | Version | Deskripsi |
|---------|---------|-----------|
| **PubSubClient** | 2.8+ | MQTT client |
| **MFRC522** | 1.4.10+ | RFID reader driver |
| **ArduinoJson** | 6.21+ | JSON encoding/decoding |

**Quick install via Library Manager:**
1. Search "PubSubClient" → Install
2. Search "MFRC522" → Install
3. Search "ArduinoJson" → Install

### Step 4: Select Board

1. Connect ESP32 via USB
2. **Tools → Board → ESP32 Arduino → ESP32 Dev Module**
3. **Tools → Port → COM3** (Windows) atau **/dev/ttyUSB0** (Linux)
4. **Tools → Upload Speed → 115200**

---

## Wiring Diagram

### MFRC522 to ESP32 Connection

| MFRC522 Pin | ESP32 Pin | Description |
|-------------|-----------|-------------|
| **SDA (SS)** | GPIO 21 | Chip Select |
| **SCK** | GPIO 18 | SPI Clock |
| **MOSI** | GPIO 23 | Master Out Slave In |
| **MISO** | GPIO 19 | Master In Slave Out |
| **IRQ** | Not connected | Interrupt (optional) |
| **GND** | GND | Ground |
| **RST** | GPIO 22 | Reset |
| **3.3V** | 3.3V | Power |

### Visual Diagram

```
ESP32 DevKit V1                MFRC522
┌─────────────┐                ┌──────────┐
│   GPIO 21   │───────────────▶│   SDA    │
│   GPIO 18   │───────────────▶│   SCK    │
│   GPIO 23   │───────────────▶│   MOSI   │
│   GPIO 19   │◀───────────────│   MISO   │
│   GPIO 22   │───────────────▶│   RST    │
│     3.3V    │───────────────▶│   3.3V   │
│     GND     │───────────────▶│   GND    │
└─────────────┘                └──────────┘
```

### Important Notes

⚠️ **DO NOT connect MFRC522 to 5V!** Module is 3.3V only.  
⚠️ **Use short wires** (<20cm) untuk SPI communication yang stable.  
⚠️ **Check connections twice** sebelum power on.

---

## Arduino Code

### Complete Code - RFID MQTT Client

```cpp
/*
 * TPT-RFID ESP32 Client
 * RFID Reader dengan MQTT Integration
 * 
 * Hardware:
 * - ESP32 DevKit V1
 * - MFRC522 RFID Reader
 * 
 * Libraries Required:
 * - PubSubClient (MQTT)
 * - MFRC522 (RFID)
 * - ArduinoJson
 */

#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <SPI.h>
#include <MFRC522.h>

// ==================== CONFIGURATION ====================

// WiFi credentials
const char* WIFI_SSID = "Your_WiFi_SSID";
const char* WIFI_PASSWORD = "Your_WiFi_Password";

// MQTT Configuration
const char* MQTT_SERVER = "192.168.1.100";  // IP Raspberry Pi
const int MQTT_PORT = 1883;
const char* MQTT_CLIENT_ID = "esp32_01";    // Unique ID per ESP32
const char* MQTT_USERNAME = "";             // Leave empty if no auth
const char* MQTT_PASSWORD = "";             // Leave empty if no auth

// MQTT Topics
const char* TOPIC_RFID_SCAN = "rfid/scan";
const char* TOPIC_HEARTBEAT = "sensor/heartbeat";

// RFID Configuration
#define RST_PIN     22    // Reset pin
#define SS_PIN      21    // SDA/SS pin

// LED indicator (built-in)
#define LED_PIN     2     // Built-in LED on most ESP32 boards

// Timing
#define SCAN_DEBOUNCE_MS 2000    // Minimum time between scans
#define MQTT_RECONNECT_MS 5000   // MQTT reconnect interval
#define HEARTBEAT_INTERVAL 60000 // Heartbeat every 60 seconds

// ==================== GLOBAL OBJECTS ====================

MFRC522 rfid(SS_PIN, RST_PIN);
WiFiClient espClient;
PubSubClient mqttClient(espClient);

unsigned long lastScanTime = 0;
unsigned long lastHeartbeat = 0;

// ==================== SETUP ====================

void setup() {
  Serial.begin(115200);
  delay(1000);
  
  Serial.println("\n\n=================================");
  Serial.println("TPT-RFID ESP32 Client");
  Serial.println("=================================\n");
  
  // Initialize LED
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);
  
  // Initialize SPI bus
  SPI.begin();
  
  // Initialize MFRC522
  rfid.PCD_Init();
  delay(100);
  
  // Show RFID reader details
  Serial.println("RFID Reader initialized:");
  rfid.PCD_DumpVersionToSerial();
  Serial.println();
  
  // Connect to WiFi
  connectWiFi();
  
  // Setup MQTT
  mqttClient.setServer(MQTT_SERVER, MQTT_PORT);
  mqttClient.setCallback(mqttCallback);
  
  Serial.println("Setup complete!\n");
}

// ==================== MAIN LOOP ====================

void loop() {
  // Maintain WiFi connection
  if (WiFi.status() != WL_CONNECTED) {
    connectWiFi();
  }
  
  // Maintain MQTT connection
  if (!mqttClient.connected()) {
    reconnectMQTT();
  }
  mqttClient.loop();
  
  // Send heartbeat
  sendHeartbeat();
  
  // Check for RFID card
  checkRFID();
  
  delay(50);  // Small delay to prevent watchdog reset
}

// ==================== WIFI ====================

void connectWiFi() {
  Serial.print("Connecting to WiFi: ");
  Serial.println(WIFI_SSID);
  
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 20) {
    delay(500);
    Serial.print(".");
    attempts++;
  }
  
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n✓ WiFi connected!");
    Serial.print("IP Address: ");
    Serial.println(WiFi.localIP());
    Serial.print("Signal Strength: ");
    Serial.print(WiFi.RSSI());
    Serial.println(" dBm\n");
    
    // Blink LED 3 times untuk indikasi WiFi connected
    blinkLED(3, 200);
  } else {
    Serial.println("\n✗ WiFi connection failed!");
    Serial.println("Restarting in 10 seconds...\n");
    delay(10000);
    ESP.restart();
  }
}

// ==================== MQTT ====================

void reconnectMQTT() {
  static unsigned long lastAttempt = 0;
  
  if (millis() - lastAttempt < MQTT_RECONNECT_MS) {
    return;  // Don't retry too frequently
  }
  
  lastAttempt = millis();
  
  Serial.print("Connecting to MQTT broker: ");
  Serial.println(MQTT_SERVER);
  
  bool connected;
  if (strlen(MQTT_USERNAME) > 0) {
    // Connect with authentication
    connected = mqttClient.connect(MQTT_CLIENT_ID, MQTT_USERNAME, MQTT_PASSWORD);
  } else {
    // Connect without authentication
    connected = mqttClient.connect(MQTT_CLIENT_ID);
  }
  
  if (connected) {
    Serial.println("✓ MQTT connected!");
    Serial.print("Client ID: ");
    Serial.println(MQTT_CLIENT_ID);
    Serial.println();
    
    // Blink LED 2 times untuk indikasi MQTT connected
    blinkLED(2, 200);
    
    // Subscribe to topics if needed (for future features)
    // mqttClient.subscribe("command/rfid");
  } else {
    Serial.print("✗ MQTT connection failed! State: ");
    Serial.println(mqttClient.state());
    Serial.println();
  }
}

void mqttCallback(char* topic, byte* payload, unsigned int length) {
  // Handle incoming MQTT messages (for future features)
  Serial.print("Message arrived [");
  Serial.print(topic);
  Serial.print("]: ");
  
  for (int i = 0; i < length; i++) {
    Serial.print((char)payload[i]);
  }
  Serial.println();
}

// ==================== RFID ====================

void checkRFID() {
  // Check if new card present
  if (!rfid.PICC_IsNewCardPresent()) {
    return;
  }
  
  // Check if card UID can be read
  if (!rfid.PICC_ReadCardSerial()) {
    return;
  }
  
  // Debounce check
  unsigned long now = millis();
  if (now - lastScanTime < SCAN_DEBOUNCE_MS) {
    rfid.PICC_HaltA();
    rfid.PCD_StopCrypto1();
    return;
  }
  
  lastScanTime = now;
  
  // Read UID
  String uid = "";
  for (byte i = 0; i < rfid.uid.size; i++) {
    uid += String(rfid.uid.uidByte[i] < 0x10 ? "0" : "");
    uid += String(rfid.uid.uidByte[i], HEX);
  }
  uid.toUpperCase();
  
  // Log to serial
  Serial.println("─────────────────────────────");
  Serial.print("✓ RFID Card Detected!\n");
  Serial.print("  UID: ");
  Serial.println(uid);
  Serial.print("  Type: ");
  
  MFRC522::PICC_Type piccType = rfid.PICC_GetType(rfid.uid.sak);
  Serial.println(rfid.PICC_GetTypeName(piccType));
  
  // LED on untuk indikasi scan
  digitalWrite(LED_PIN, HIGH);
  
  // Publish to MQTT
  publishRFIDScan(uid);
  
  // Halt PICC
  rfid.PICC_HaltA();
  rfid.PCD_StopCrypto1();
  
  // LED off
  delay(200);
  digitalWrite(LED_PIN, LOW);
  
  Serial.println("─────────────────────────────\n");
}

void publishRFIDScan(String uid) {
  if (!mqttClient.connected()) {
    Serial.println("✗ Cannot publish - MQTT not connected");
    return;
  }
  
  // Create JSON payload
  StaticJsonDocument<256> doc;
  doc["rfid_uid"] = uid;
  doc["reader_id"] = MQTT_CLIENT_ID;
  doc["timestamp"] = getISO8601Timestamp();
  doc["rssi"] = WiFi.RSSI();
  
  // Serialize to string
  char payload[256];
  serializeJson(doc, payload);
  
  // Publish dengan QoS 1 (at least once delivery)
  bool success = mqttClient.publish(TOPIC_RFID_SCAN, payload, false);
  
  if (success) {
    Serial.print("✓ Published to MQTT: ");
    Serial.println(payload);
  } else {
    Serial.println("✗ Publish failed!");
  }
}

// ==================== HEARTBEAT ====================

void sendHeartbeat() {
  unsigned long now = millis();
  
  if (now - lastHeartbeat < HEARTBEAT_INTERVAL) {
    return;
  }
  
  lastHeartbeat = now;
  
  if (!mqttClient.connected()) {
    return;
  }
  
  // Create JSON payload
  StaticJsonDocument<256> doc;
  doc["client_id"] = MQTT_CLIENT_ID;
  doc["uptime"] = millis() / 1000;  // seconds
  doc["rssi"] = WiFi.RSSI();
  doc["free_heap"] = ESP.getFreeHeap();
  doc["timestamp"] = getISO8601Timestamp();
  
  char payload[256];
  serializeJson(doc, payload);
  
  mqttClient.publish(TOPIC_HEARTBEAT, payload, false);
  
  Serial.print("♥ Heartbeat sent (Uptime: ");
  Serial.print(millis() / 1000);
  Serial.println(" seconds)");
}

// ==================== UTILITIES ====================

void blinkLED(int times, int delayMs) {
  for (int i = 0; i < times; i++) {
    digitalWrite(LED_PIN, HIGH);
    delay(delayMs);
    digitalWrite(LED_PIN, LOW);
    delay(delayMs);
  }
}

String getISO8601Timestamp() {
  // Simple timestamp (millis since boot)
  // For accurate timestamp, use NTP client
  unsigned long seconds = millis() / 1000;
  unsigned long minutes = seconds / 60;
  unsigned long hours = minutes / 60;
  
  char timestamp[32];
  snprintf(timestamp, sizeof(timestamp), "T+%02lu:%02lu:%02lu", 
           hours, minutes % 60, seconds % 60);
  
  return String(timestamp);
}
```

### Code Explanation

**Key Functions:**

1. **setup()** - Initialize hardware, WiFi, MQTT
2. **loop()** - Main loop: maintain connections, check RFID
3. **connectWiFi()** - Connect to WiFi network
4. **reconnectMQTT()** - Reconnect to MQTT broker with retry logic
5. **checkRFID()** - Poll RFID reader for new cards
6. **publishRFIDScan()** - Publish RFID scan to MQTT
7. **sendHeartbeat()** - Periodic heartbeat untuk monitoring

**Features:**

- ✓ Auto-reconnect WiFi dan MQTT
- ✓ Scan debouncing (prevent duplicate scans)
- ✓ LED indicators (WiFi connected, MQTT connected, scan detected)
- ✓ Heartbeat messages untuk monitoring
- ✓ JSON payload dengan metadata (timestamp, RSSI)
- ✓ Serial debug output

---

## Configuration

### WiFi Settings

```cpp
const char* WIFI_SSID = "Lab_Fabrikasi_WiFi";
const char* WIFI_PASSWORD = "password_here";
```

### MQTT Broker

**Development (localhost):**
```cpp
const char* MQTT_SERVER = "192.168.1.100";  // Laptop IP
```

**Production (Raspberry Pi):**
```cpp
const char* MQTT_SERVER = "192.168.1.50";   // Raspberry Pi IP
```

**Dengan Authentication:**
```cpp
const char* MQTT_USERNAME = "tpt-rfid";
const char* MQTT_PASSWORD = "secure_password";
```

### Multiple ESP32

Untuk multiple ESP32, ubah Client ID:

```cpp
// ESP32 #1 (Main RFID reader)
const char* MQTT_CLIENT_ID = "esp32_rfid_01";

// ESP32 #2 (Secondary reader atau sensor station)
const char* MQTT_CLIENT_ID = "esp32_rfid_02";

// ESP32 #3 (Sensor station)
const char* MQTT_CLIENT_ID = "esp32_sensor_01";
```

---

## Testing

### Step 1: Upload Code

1. Copy complete code ke Arduino IDE
2. Update WiFi credentials dan MQTT server IP
3. **Sketch → Upload**
4. Wait for "Done uploading"

### Step 2: Monitor Serial Output

1. **Tools → Serial Monitor**
2. Set baud rate: **115200**

**Expected output:**
```
=================================
TPT-RFID ESP32 Client
=================================

RFID Reader initialized:
Firmware Version: 0x92

Connecting to WiFi: Lab_Fabrikasi_WiFi
........
✓ WiFi connected!
IP Address: 192.168.1.105
Signal Strength: -45 dBm

Connecting to MQTT broker: 192.168.1.100
✓ MQTT connected!
Client ID: esp32_01

Setup complete!

♥ Heartbeat sent (Uptime: 5 seconds)
```

### Step 3: Test RFID Scan

Tap RFID card pada reader. Serial monitor akan menampilkan:

```
─────────────────────────────
✓ RFID Card Detected!
  UID: 04A1B2C3D4E5F6
  Type: MIFARE 1KB
✓ Published to MQTT: {"rfid_uid":"04A1B2C3D4E5F6","reader_id":"esp32_01",...}
─────────────────────────────
```

### Step 4: Verify on Server

Di server Flask, check logs:

```bash
tail -f /var/log/tpt-rfid.log

# Should show:
MQTT RFID scan received: 04A1B2C3D4E5F6 from esp32_01
Student identified: Ahmad Fauzi (NIM: 1234567890)
```

### Step 5: Subscribe to MQTT (Optional)

Di laptop/Raspberry Pi:

```bash
mosquitto_sub -h localhost -t 'rfid/scan' -v

# Output saat ESP32 scan:
rfid/scan {"rfid_uid":"04A1B2C3D4E5F6","reader_id":"esp32_01",...}
```

---

## Troubleshooting

### WiFi Cannot Connect

**Symptoms:**
```
Connecting to WiFi: ...............
✗ WiFi connection failed!
```

**Solutions:**
1. Check SSID dan password benar
2. Check WiFi range (RSSI harus > -70 dBm)
3. Use 2.4GHz WiFi (ESP32 tidak support 5GHz)
4. Restart router
5. Try different WiFi channel

### MQTT Connection Failed

**State codes:**
- `-4` : Connection timeout
- `-3` : Connection lost
- `-2` : Connect failed
- `-1` : Disconnected
- `0` : Connected
- `1` : Bad protocol
- `2` : Client ID rejected
- `3` : Server unavailable
- `4` : Bad credentials
- `5` : Not authorized

**Solutions:**
```cpp
// State -4 (timeout):
// - Check MQTT_SERVER IP correct
// - Ping Raspberry Pi: ping 192.168.1.100

// State 4 (bad credentials):
// - Check MQTT_USERNAME and MQTT_PASSWORD
// - Or set to "" if no auth

// State 5 (not authorized):
// - Check Mosquitto config: allow_anonymous true
```

### RFID Reader Not Working

**Symptoms:**
- No card detected
- "Firmware Version: 0x00"

**Solutions:**
1. Check wiring (especially SDA and SCK)
2. Check 3.3V power (NOT 5V!)
3. Use short wires (<20cm)
4. Try different RFID card
5. Check SPI pins:
   ```cpp
   rfid.PCD_DumpVersionToSerial();
   // Should show: Firmware Version: 0x91 or 0x92
   ```

### Duplicate Scans

**Symptoms:**
Same card scanned multiple times in 1 second

**Solutions:**
Increase debounce time:
```cpp
#define SCAN_DEBOUNCE_MS 3000  // 3 seconds instead of 2
```

### ESP32 Resets Randomly

**Symptoms:**
```
rst:0x8 (TG1WDT_SYS_RESET),boot:0x13 (SPI_FAST_FLASH_BOOT)
```

**Solutions:**
1. Power supply issue - use good quality USB cable
2. Add delay in loop:
   ```cpp
   void loop() {
     // ... your code ...
     delay(50);  // Prevent watchdog reset
   }
   ```
3. Use external 5V power supply (not USB)

---

## Advanced Features

### Feature 1: NTP Time Sync (Accurate Timestamps)

Add NTP client untuk accurate timestamps:

```cpp
#include <time.h>

const char* NTP_SERVER = "pool.ntp.org";
const long GMT_OFFSET_SEC = 25200;  // GMT+7 (WIB)
const int DAYLIGHT_OFFSET_SEC = 0;

void setup() {
  // ... existing setup code ...
  
  // Configure NTP
  configTime(GMT_OFFSET_SEC, DAYLIGHT_OFFSET_SEC, NTP_SERVER);
  Serial.println("Waiting for NTP time sync...");
  
  struct tm timeinfo;
  if (getLocalTime(&timeinfo)) {
    Serial.println("✓ Time synchronized!");
    Serial.println(&timeinfo, "%A, %B %d %Y %H:%M:%S");
  }
}

String getISO8601Timestamp() {
  struct tm timeinfo;
  if (!getLocalTime(&timeinfo)) {
    return "T+Unknown";
  }
  
  char timestamp[32];
  strftime(timestamp, sizeof(timestamp), "%Y-%m-%dT%H:%M:%S", &timeinfo);
  return String(timestamp) + "Z";
}
```

### Feature 2: Deep Sleep Mode (Battery Powered)

Untuk battery-powered deployment:

```cpp
#define SLEEP_DURATION_SECONDS 60

void enterDeepSleep() {
  Serial.println("Entering deep sleep for " + String(SLEEP_DURATION_SECONDS) + " seconds...");
  
  // Disconnect MQTT
  mqttClient.disconnect();
  
  // Disconnect WiFi
  WiFi.disconnect(true);
  WiFi.mode(WIFI_OFF);
  
  // Configure wakeup
  esp_sleep_enable_timer_wakeup(SLEEP_DURATION_SECONDS * 1000000ULL);
  
  // Enter deep sleep
  esp_deep_sleep_start();
}

// Call this when idle for X minutes
```

### Feature 3: OTA Updates (Over-The-Air)

Update firmware via WiFi:

```cpp
#include <ArduinoOTA.h>

void setup() {
  // ... existing setup ...
  
  // Configure OTA
  ArduinoOTA.setHostname(MQTT_CLIENT_ID);
  ArduinoOTA.setPassword("admin");  // Set OTA password
  
  ArduinoOTA.onStart([]() {
    Serial.println("OTA Update Starting...");
  });
  
  ArduinoOTA.onEnd([]() {
    Serial.println("\nOTA Update Complete!");
  });
  
  ArduinoOTA.onProgress([](unsigned int progress, unsigned int total) {
    Serial.printf("Progress: %u%%\r", (progress / (total / 100)));
  });
  
  ArduinoOTA.begin();
  Serial.println("OTA Ready!");
}

void loop() {
  ArduinoOTA.handle();  // Handle OTA updates
  // ... rest of loop ...
}
```

Update via Arduino IDE:
1. **Tools → Port → Network Port → esp32_01**
2. **Sketch → Upload**

---

## Best Practices

1. **Use unique Client IDs** - Setiap ESP32 harus punya ID berbeda
2. **Handle reconnections** - WiFi dan MQTT bisa disconnect kapan saja
3. **Add debouncing** - Prevent duplicate RFID scans
4. **Monitor uptime** - Send heartbeat untuk health monitoring
5. **Use QoS 1 for critical data** - RFID scans harus reliable
6. **Log everything** - Serial output untuk debugging
7. **Power supply quality** - Use good USB cable atau external PSU
8. **Short wires** - SPI communication butuh short wires
9. **Test range** - RFID reader range varies, test di lokasi actual
10. **Firmware updates** - Keep ESP32 core dan libraries updated

---

## Next Steps

- [MQTT Setup Guide](MQTT_SETUP.md) - Setup Mosquitto broker
- [Deployment Guide](DEPLOYMENT.md) - Deploy ke production
- [Troubleshooting](TROUBLESHOOTING.md) - Common issues

---

**Hardware Suppliers:**

- **Tokopedia:** Search "ESP32 DevKit" + "MFRC522"
- **Shopee:** Search "ESP32" + "RFID RC522"
- **AliExpress:** Search "ESP32-WROOM-32" + "MFRC522 RFID"

**Estimated delivery:**
- Local (Tokopedia/Shopee): 2-5 hari
- AliExpress: 2-4 minggu
