"""
Mock RFID Reader for development without hardware
In production, this will be replaced with actual serial communication to ESP32
"""
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class RFIDMock:
    """
    Mock RFID reader for development and testing
    Simulates RFID card/tag scanning behavior
    """
    
    def __init__(self):
        """Initialize the mock RFID reader"""
        self.current_uid = None
        self.last_scan_time = None
        self.scan_duration = 3  # How long a scan stays "active" (seconds)
        logger.info("RFID Mock initialized")
    
    def simulate_scan(self, uid):
        """
        Simulate an RFID card/tag scan
        
        Args:
            uid (str): The UID to simulate (e.g., "ABCD1234")
        """
        self.current_uid = uid
        self.last_scan_time = datetime.now()
        logger.info(f"RFID Mock: Simulated scan of UID: {uid}")
    
    def get_current_uid(self):
        """
        Get the currently scanned UID
        Returns None if no card is present or scan has expired
        
        Returns:
            str or None: The current UID if available, None otherwise
        """
        if not self.current_uid or not self.last_scan_time:
            return None
        
        # Check if scan has expired
        elapsed = (datetime.now() - self.last_scan_time).total_seconds()
        if elapsed > self.scan_duration:
            logger.debug(f"RFID Mock: Scan expired for UID: {self.current_uid}")
            self.current_uid = None
            self.last_scan_time = None
            return None
        
        return self.current_uid
    
    def clear(self):
        """Clear the current UID (simulate card removal)"""
        if self.current_uid:
            logger.info(f"RFID Mock: Cleared UID: {self.current_uid}")
        self.current_uid = None
        self.last_scan_time = None
    
    def is_card_present(self):
        """
        Check if a card is currently present
        
        Returns:
            bool: True if card is present, False otherwise
        """
        return self.get_current_uid() is not None


# Global RFID mock instance
rfid_reader = RFIDMock()


# Production Implementation Reference
# ====================================
# When deploying to Raspberry Pi with actual ESP32 hardware,
# replace this mock with serial communication:
#
# import serial
#
# class RFIDReader:
#     def __init__(self, port='/dev/ttyUSB0', baudrate=115200):
#         self.serial = serial.Serial(port, baudrate, timeout=1)
#         self.current_uid = None
#     
#     def read_uid(self):
#         """Read UID from ESP32 via serial"""
#         if self.serial.in_waiting > 0:
#             data = self.serial.readline().decode('utf-8').strip()
#             if data.startswith('UID:'):
#                 self.current_uid = data.split(':')[1]
#                 return self.current_uid
#         return None
#     
#     def get_current_uid(self):
#         """Poll for current UID"""
#         return self.read_uid()
#     
#     def clear(self):
#         """Clear current UID"""
#         self.current_uid = None
#         # Send clear command to ESP32 if needed
#         self.serial.write(b'CLEAR\n')
