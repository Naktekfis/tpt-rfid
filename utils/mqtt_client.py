"""
MQTT Client for TPT-RFID System
Provides abstraction layer with mock mode support
"""

import logging
import json
from typing import Callable, Dict, Optional, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class MQTTClientMock:
    """
    Mock MQTT client for development without MQTT dependencies
    Logs all operations but doesn't actually connect to broker
    """

    def __init__(
        self,
        broker_host: str = "localhost",
        broker_port: int = 1883,
        client_id: str = "tpt-rfid-mock",
    ):
        """Initialize mock MQTT client"""
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.client_id = client_id
        self.connected = False
        self.subscriptions = {}
        logger.info(
            f"[MOCK] MQTT Client initialized: {client_id} @ {broker_host}:{broker_port}"
        )

    def connect(self) -> bool:
        """Mock connection to broker"""
        self.connected = True
        logger.info(
            f"[MOCK] Connected to MQTT broker at {self.broker_host}:{self.broker_port}"
        )
        return True

    def disconnect(self):
        """Mock disconnection from broker"""
        self.connected = False
        logger.info("[MOCK] Disconnected from MQTT broker")

    def publish(
        self, topic: str, payload: Any, qos: int = 0, retain: bool = False
    ) -> bool:
        """
        Mock publish message to topic

        Args:
            topic: MQTT topic
            payload: Message payload (will be JSON-encoded if dict)
            qos: Quality of Service (0, 1, or 2)
            retain: Retain message flag

        Returns:
            bool: Always True for mock
        """
        if isinstance(payload, dict):
            payload_str = json.dumps(payload)
        else:
            payload_str = str(payload)

        logger.info(
            f"[MOCK] Published to '{topic}' (QoS {qos}, retain={retain}): {payload_str}"
        )
        return True

    def subscribe(self, topic: str, callback: Callable, qos: int = 0):
        """
        Mock subscribe to topic

        Args:
            topic: MQTT topic (supports wildcards # and +)
            callback: Function to call when message received
            qos: Quality of Service
        """
        self.subscriptions[topic] = {"callback": callback, "qos": qos}
        logger.info(f"[MOCK] Subscribed to '{topic}' (QoS {qos})")

    def unsubscribe(self, topic: str):
        """Mock unsubscribe from topic"""
        if topic in self.subscriptions:
            del self.subscriptions[topic]
            logger.info(f"[MOCK] Unsubscribed from '{topic}'")

    def simulate_message(self, topic: str, payload: Dict):
        """
        Simulate receiving a message (for testing)

        Args:
            topic: Topic to simulate
            payload: Message payload
        """
        logger.info(f"[MOCK] Simulating message on '{topic}': {payload}")

        # Find matching subscriptions
        for sub_topic, sub_data in self.subscriptions.items():
            if self._topic_matches(sub_topic, topic):
                try:
                    sub_data["callback"](topic, payload)
                except Exception as e:
                    logger.error(f"[MOCK] Error in callback for '{topic}': {e}")

    def _topic_matches(self, subscription: str, topic: str) -> bool:
        """Check if topic matches subscription pattern"""
        # Simple implementation - could be enhanced
        if subscription == topic:
            return True
        if subscription == "#":
            return True
        if "+" in subscription or "#" in subscription:
            # Basic wildcard matching
            sub_parts = subscription.split("/")
            topic_parts = topic.split("/")

            if len(sub_parts) > len(topic_parts) and "#" not in subscription:
                return False

            for i, sub_part in enumerate(sub_parts):
                if sub_part == "#":
                    return True
                if i >= len(topic_parts):
                    return False
                if sub_part != "+" and sub_part != topic_parts[i]:
                    return False
            return True
        return False

    def is_connected(self) -> bool:
        """Check if connected"""
        return self.connected

    def loop_start(self):
        """Mock start network loop"""
        logger.info("[MOCK] Network loop started")

    def loop_stop(self):
        """Mock stop network loop"""
        logger.info("[MOCK] Network loop stopped")


class MQTTClientReal:
    """
    Real MQTT client using paho-mqtt library
    Requires paho-mqtt to be installed
    """

    def __init__(
        self,
        broker_host: str = "localhost",
        broker_port: int = 1883,
        client_id: str = "tpt-rfid",
        username: Optional[str] = None,
        password: Optional[str] = None,
    ):
        """
        Initialize real MQTT client

        Args:
            broker_host: MQTT broker hostname
            broker_port: MQTT broker port
            client_id: Client identifier
            username: Optional username for authentication
            password: Optional password for authentication
        """
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            raise ImportError(
                "paho-mqtt is required for real MQTT client. "
                "Install with: pip install -r requirements-mqtt.txt"
            )

        self.broker_host = broker_host
        self.broker_port = broker_port
        self.client_id = client_id
        self.subscriptions = {}

        # Create MQTT client
        self.client = mqtt.Client(client_id=client_id, protocol=mqtt.MQTTv311)

        # Set authentication if provided
        if username and password:
            self.client.username_pw_set(username, password)
            logger.info(f"MQTT authentication configured for user: {username}")

        # Set callbacks
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message

        logger.info(
            f"MQTT Client initialized: {client_id} @ {broker_host}:{broker_port}"
        )

    def connect(self) -> bool:
        """
        Connect to MQTT broker

        Returns:
            bool: True if connection successful
        """
        try:
            self.client.connect(self.broker_host, self.broker_port, keepalive=60)
            self.client.loop_start()
            logger.info(
                f"Connected to MQTT broker at {self.broker_host}:{self.broker_port}"
            )
            return True
        except Exception as e:
            logger.error(f"Failed to connect to MQTT broker: {e}")
            return False

    def disconnect(self):
        """Disconnect from MQTT broker"""
        self.client.loop_stop()
        self.client.disconnect()
        logger.info("Disconnected from MQTT broker")

    def publish(
        self, topic: str, payload: Any, qos: int = 0, retain: bool = False
    ) -> bool:
        """
        Publish message to topic

        Args:
            topic: MQTT topic
            payload: Message payload (will be JSON-encoded if dict)
            qos: Quality of Service (0, 1, or 2)
            retain: Retain message flag

        Returns:
            bool: True if publish successful
        """
        try:
            if isinstance(payload, dict):
                payload_str = json.dumps(payload)
            else:
                payload_str = str(payload)

            result = self.client.publish(topic, payload_str, qos=qos, retain=retain)

            if result.rc == 0:
                logger.info(f"Published to '{topic}' (QoS {qos}): {payload_str[:100]}")
                return True
            else:
                logger.error(f"Failed to publish to '{topic}': {result.rc}")
                return False
        except Exception as e:
            logger.error(f"Error publishing to '{topic}': {e}")
            return False

    def subscribe(self, topic: str, callback: Callable, qos: int = 0):
        """
        Subscribe to topic

        Args:
            topic: MQTT topic (supports wildcards # and +)
            callback: Function to call when message received (topic, payload)
            qos: Quality of Service
        """
        self.subscriptions[topic] = callback
        self.client.subscribe(topic, qos=qos)
        logger.info(f"Subscribed to '{topic}' (QoS {qos})")

    def unsubscribe(self, topic: str):
        """Unsubscribe from topic"""
        if topic in self.subscriptions:
            del self.subscriptions[topic]
        self.client.unsubscribe(topic)
        logger.info(f"Unsubscribed from '{topic}'")

    def is_connected(self) -> bool:
        """Check if connected to broker"""
        return self.client.is_connected()

    def loop_start(self):
        """Start network loop (called automatically in connect)"""
        self.client.loop_start()

    def loop_stop(self):
        """Stop network loop (called automatically in disconnect)"""
        self.client.loop_stop()

    # ==================== Callbacks ====================

    def _on_connect(self, client, userdata, flags, rc):
        """Callback when connected to broker"""
        if rc == 0:
            logger.info("MQTT connection established")
            # Re-subscribe to all topics
            for topic in self.subscriptions.keys():
                client.subscribe(topic)
                logger.info(f"Re-subscribed to '{topic}'")
        else:
            logger.error(f"MQTT connection failed with code: {rc}")

    def _on_disconnect(self, client, userdata, rc):
        """Callback when disconnected from broker"""
        if rc == 0:
            logger.info("MQTT disconnected cleanly")
        else:
            logger.warning(f"MQTT disconnected unexpectedly (code: {rc})")

    def _on_message(self, client, userdata, msg):
        """Callback when message received"""
        topic = msg.topic

        try:
            # Try to parse as JSON
            payload = json.loads(msg.payload.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            # Fallback to string
            payload = msg.payload.decode("utf-8", errors="ignore")

        logger.debug(f"Received message on '{topic}': {payload}")

        # Find matching subscription callbacks
        for sub_topic, callback in self.subscriptions.items():
            if self._topic_matches(sub_topic, topic):
                try:
                    callback(topic, payload)
                except Exception as e:
                    logger.error(f"Error in callback for '{topic}': {e}")

    def _topic_matches(self, subscription: str, topic: str) -> bool:
        """Check if topic matches subscription pattern"""
        if subscription == topic:
            return True
        if subscription == "#":
            return True

        sub_parts = subscription.split("/")
        topic_parts = topic.split("/")

        if len(sub_parts) > len(topic_parts):
            return False

        for i, sub_part in enumerate(sub_parts):
            if sub_part == "#":
                return True
            if i >= len(topic_parts):
                return False
            if sub_part != "+" and sub_part != topic_parts[i]:
                return False

        return len(sub_parts) == len(topic_parts)


def create_mqtt_client(
    enabled: bool = False, **kwargs
) -> MQTTClientMock | MQTTClientReal:
    """
    Factory function to create MQTT client based on configuration

    Args:
        enabled: If True, create real MQTT client; if False, create mock
        **kwargs: Arguments passed to client constructor

    Returns:
        MQTTClientMock or MQTTClientReal instance
    """
    if enabled:
        logger.info("Creating REAL MQTT client")
        return MQTTClientReal(**kwargs)
    else:
        logger.info("Creating MOCK MQTT client (MQTT_ENABLED=false)")
        # Mock client only accepts broker_host, broker_port, client_id
        mock_kwargs = {
            "broker_host": kwargs.get("broker_host", "localhost"),
            "broker_port": kwargs.get("broker_port", 1883),
            "client_id": kwargs.get("client_id", "tpt-rfid-mock"),
        }
        return MQTTClientMock(**mock_kwargs)
