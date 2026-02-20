#!/usr/bin/env python3
"""
Test MQTT integration with TPT-RFID app
Simulates ESP32 sending RFID scan messages
"""

import paho.mqtt.client as mqtt
import json
import time
import sys

# MQTT Configuration
BROKER = "localhost"
PORT = 1883
TOPIC_RFID_SCAN = "rfid/scan"

# Test RFIDs (from seed data if available)
TEST_RFIDS = [
    {"rfid_uid": "1234567890", "reader_id": "esp32_01", "name": "Test Student 1"},
    {"rfid_uid": "0987654321", "reader_id": "esp32_01", "name": "Test Student 2"},
    {"rfid_uid": "UNKNOWN123", "reader_id": "esp32_01", "name": "Unknown Card"},
]


def on_connect(client, userdata, flags, rc):
    """Callback when connected to broker"""
    if rc == 0:
        print(f"✓ Connected to MQTT broker at {BROKER}:{PORT}")
    else:
        print(f"✗ Connection failed with code: {rc}")
        sys.exit(1)


def on_publish(client, userdata, mid):
    """Callback when message published"""
    print(f"  Message published (mid: {mid})")


def main():
    print("=" * 60)
    print("  TPT-RFID MQTT Integration Test")
    print("=" * 60)
    print("")

    # Create MQTT client
    client = mqtt.Client(client_id="esp32-test-simulator", protocol=mqtt.MQTTv311)
    client.on_connect = on_connect
    client.on_publish = on_publish

    # Connect to broker
    print(f"Connecting to broker at {BROKER}:{PORT}...")
    try:
        client.connect(BROKER, PORT, keepalive=60)
        client.loop_start()
        time.sleep(1)  # Wait for connection
    except Exception as e:
        print(f"✗ Failed to connect: {e}")
        sys.exit(1)

    print("")
    print("Simulating RFID scans...")
    print("-" * 60)

    # Simulate RFID scans
    for i, rfid_data in enumerate(TEST_RFIDS, 1):
        print(f"\n[Test {i}/{len(TEST_RFIDS)}] Scanning RFID: {rfid_data['rfid_uid']}")
        print(f"  Expected: {rfid_data['name']}")

        # Create payload
        payload = {
            "rfid_uid": rfid_data["rfid_uid"],
            "reader_id": rfid_data["reader_id"],
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

        # Publish message
        result = client.publish(TOPIC_RFID_SCAN, json.dumps(payload), qos=1)

        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            print(f"  ✓ Published to '{TOPIC_RFID_SCAN}'")
            print(f"    Payload: {json.dumps(payload)}")
        else:
            print(f"  ✗ Publish failed: {result.rc}")

        # Wait before next scan
        if i < len(TEST_RFIDS):
            print("  Waiting 2 seconds...")
            time.sleep(2)

    print("")
    print("-" * 60)
    print("All test scans completed!")
    print("")
    print("Check the Flask app logs to see if MQTT messages were received.")
    print("If MQTT_ENABLED=true, you should see:")
    print("  - 'MQTT RFID scan received: ...'")
    print("  - 'Student identified: ...' (for known RFIDs)")
    print("  - 'Unknown RFID scanned: ...' (for unknown RFIDs)")
    print("")

    # Cleanup
    client.loop_stop()
    client.disconnect()
    print("Disconnected from broker.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user.")
        sys.exit(0)
    except Exception as e:
        print(f"\n✗ Error: {e}")
        sys.exit(1)
