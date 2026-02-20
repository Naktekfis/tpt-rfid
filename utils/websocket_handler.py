"""
WebSocket Handler for TPT-RFID System
Provides real-time updates to web clients via Flask-SocketIO
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class WebSocketHandlerMock:
    """
    Mock WebSocket handler for development without Socket.IO dependencies
    Logs all operations but doesn't actually emit events
    """

    def __init__(self, app=None):
        """Initialize mock WebSocket handler"""
        self.app = app
        self.rooms = set()
        logger.info("[MOCK] WebSocket handler initialized (mock mode)")

    def init_app(self, app):
        """Initialize with Flask app"""
        self.app = app
        logger.info("[MOCK] WebSocket handler attached to Flask app")

    def emit(
        self, event: str, data: Any, room: Optional[str] = None, namespace: str = "/"
    ):
        """
        Mock emit event to clients

        Args:
            event: Event name
            data: Data to send
            room: Optional room to send to (None = broadcast)
            namespace: Socket.IO namespace
        """
        room_str = f" to room '{room}'" if room else " (broadcast)"
        logger.info(f"[MOCK] WebSocket emit '{event}'{room_str}: {data}")

    def join_room(self, room: str, sid: Optional[str] = None):
        """Mock join room"""
        self.rooms.add(room)
        logger.info(f"[MOCK] Client joined room '{room}'")

    def leave_room(self, room: str, sid: Optional[str] = None):
        """Mock leave room"""
        if room in self.rooms:
            self.rooms.remove(room)
        logger.info(f"[MOCK] Client left room '{room}'")

    def on_connect(self, handler):
        """Mock register connect handler"""
        logger.info("[MOCK] Registered connect handler")
        return handler

    def on_disconnect(self, handler):
        """Mock register disconnect handler"""
        logger.info("[MOCK] Registered disconnect handler")
        return handler

    def on(self, event: str):
        """Mock decorator for event handlers"""

        def decorator(handler):
            logger.info(f"[MOCK] Registered handler for event '{event}'")
            return handler

        return decorator


class WebSocketHandlerReal:
    """
    Real WebSocket handler using Flask-SocketIO
    Requires flask-socketio to be installed
    """

    def __init__(self, app=None):
        """
        Initialize real WebSocket handler

        Args:
            app: Flask application instance
        """
        try:
            from flask_socketio import SocketIO, emit, join_room, leave_room

            self._SocketIO = SocketIO
            self._emit = emit
            self._join_room = join_room
            self._leave_room = leave_room
        except ImportError:
            raise ImportError(
                "flask-socketio is required for real WebSocket handler. "
                "Install with: pip install -r requirements-mqtt.txt"
            )

        self.socketio = None
        self.app = app

        if app is not None:
            self.init_app(app)

        logger.info("WebSocket handler initialized (real mode)")

    def init_app(self, app):
        """
        Initialize with Flask app

        Args:
            app: Flask application instance
        """
        self.app = app
        self.socketio = self._SocketIO(
            app,
            cors_allowed_origins="*",  # Adjust for production
            async_mode="threading",
            logger=False,
            engineio_logger=False,
        )

        # Register default handlers
        self._register_default_handlers()

        logger.info("WebSocket handler attached to Flask app with Socket.IO")

    def _register_default_handlers(self):
        """Register default Socket.IO event handlers"""

        @self.socketio.on("connect")
        def handle_connect():
            logger.info("Client connected to WebSocket")
            self.emit(
                "connection_established",
                {"status": "connected", "timestamp": datetime.utcnow().isoformat()},
            )

        @self.socketio.on("disconnect")
        def handle_disconnect():
            logger.info("Client disconnected from WebSocket")

        @self.socketio.on("join")
        def handle_join(data):
            """Allow clients to join specific rooms"""
            room = data.get("room")
            if room:
                self._join_room(room)
                logger.info(f"Client joined room: {room}")
                self.emit("joined_room", {"room": room}, room=room)

        @self.socketio.on("leave")
        def handle_leave(data):
            """Allow clients to leave rooms"""
            room = data.get("room")
            if room:
                self._leave_room(room)
                logger.info(f"Client left room: {room}")

    def emit(
        self, event: str, data: Any, room: Optional[str] = None, namespace: str = "/"
    ):
        """
        Emit event to clients

        Args:
            event: Event name
            data: Data to send (will be JSON-serialized)
            room: Optional room to send to (None = broadcast to all)
            namespace: Socket.IO namespace
        """
        try:
            if room:
                self.socketio.emit(event, data, room=room, namespace=namespace)
                logger.debug(f"Emitted '{event}' to room '{room}'")
            else:
                self.socketio.emit(event, data, namespace=namespace)
                logger.debug(f"Broadcast '{event}' to all clients")
        except Exception as e:
            logger.error(f"Error emitting event '{event}': {e}")

    def join_room(self, room: str, sid: Optional[str] = None):
        """
        Join a room

        Args:
            room: Room name
            sid: Optional session ID (uses current if None)
        """
        self._join_room(room, sid=sid)

    def leave_room(self, room: str, sid: Optional[str] = None):
        """
        Leave a room

        Args:
            room: Room name
            sid: Optional session ID (uses current if None)
        """
        self._leave_room(room, sid=sid)

    def on(self, event: str):
        """
        Decorator to register event handler

        Args:
            event: Event name to handle
        """
        return self.socketio.on(event)

    def on_connect(self, handler):
        """Register connect handler"""
        return self.socketio.on("connect")(handler)

    def on_disconnect(self, handler):
        """Register disconnect handler"""
        return self.socketio.on("disconnect")(handler)

    def run(self, app, **kwargs):
        """
        Run the Socket.IO server

        Args:
            app: Flask app
            **kwargs: Arguments passed to socketio.run()
        """
        return self.socketio.run(app, **kwargs)


def create_websocket_handler(enabled: bool = False, app=None):
    """
    Factory function to create WebSocket handler based on configuration

    Args:
        enabled: If True, create real handler; if False, create mock
        app: Flask application instance

    Returns:
        WebSocketHandlerMock or WebSocketHandlerReal instance
    """
    if enabled:
        logger.info("Creating REAL WebSocket handler")
        return WebSocketHandlerReal(app=app)
    else:
        logger.info("Creating MOCK WebSocket handler (WEBSOCKET_ENABLED=false)")
        return WebSocketHandlerMock(app=app)


# ==================== Helper Functions ====================


def broadcast_rfid_scan(ws_handler, rfid_data: Dict):
    """
    Broadcast RFID scan event to all connected clients

    Args:
        ws_handler: WebSocket handler instance
        rfid_data: RFID scan data (rfid_uid, student_name, etc.)
    """
    ws_handler.emit("rfid_scan", rfid_data)
    logger.info(f"Broadcast RFID scan: {rfid_data.get('rfid_uid')}")


def broadcast_transaction_update(ws_handler, transaction_data: Dict):
    """
    Broadcast transaction update to all connected clients

    Args:
        ws_handler: WebSocket handler instance
        transaction_data: Transaction data (id, status, student, tool, etc.)
    """
    ws_handler.emit("transaction_update", transaction_data)
    logger.info(f"Broadcast transaction update: {transaction_data.get('id')}")


def broadcast_tool_status(ws_handler, tool_data: Dict):
    """
    Broadcast tool status change to all connected clients

    Args:
        ws_handler: WebSocket handler instance
        tool_data: Tool data (id, name, status)
    """
    ws_handler.emit("tool_status", tool_data)
    logger.info(
        f"Broadcast tool status: {tool_data.get('name')} -> {tool_data.get('status')}"
    )


def broadcast_sensor_data(ws_handler, sensor_data: Dict):
    """
    Broadcast sensor data to all connected clients

    Args:
        ws_handler: WebSocket handler instance
        sensor_data: Sensor readings (type, value, unit, timestamp)
    """
    ws_handler.emit("sensor_data", sensor_data)
    logger.debug(f"Broadcast sensor data: {sensor_data.get('type')}")
