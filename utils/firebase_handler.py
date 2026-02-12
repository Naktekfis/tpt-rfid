"""
Firebase Firestore and Storage handler for RFID Workshop Tool Monitoring System
Handles all database operations and file storage
"""
import os
import logging
from datetime import datetime
from typing import Dict, List, Optional

import firebase_admin
from firebase_admin import credentials, firestore, storage
from google.cloud.firestore_v1.base_query import FieldFilter
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)


class FirebaseHandler:
    """Handler for Firebase Firestore and Storage operations"""
    
    def __init__(self):
        """Initialize Firebase Admin SDK"""
        try:
            # Check if Firebase app is already initialized
            firebase_admin.get_app()
            logger.info("Firebase app already initialized")
        except ValueError:
            # Initialize Firebase
            cred_path = 'serviceAccountKey.json'
            if not os.path.exists(cred_path):
                raise FileNotFoundError(
                    f"Firebase credentials not found at {cred_path}. "
                    "Please download your service account key from Firebase Console."
                )
            
            cred = credentials.Certificate(cred_path)
            storage_bucket = os.getenv('FIREBASE_STORAGE_BUCKET')
            
            if not storage_bucket:
                raise ValueError(
                    "FIREBASE_STORAGE_BUCKET not found in environment. "
                    "Please set it in your .env file."
                )
            
            firebase_admin.initialize_app(cred, {
                'storageBucket': storage_bucket
            })
            logger.info("Firebase initialized successfully")
        
        self.db = firestore.client()
        
        # Get storage bucket
        storage_bucket = os.getenv('FIREBASE_STORAGE_BUCKET')
        if storage_bucket:
            self.bucket = storage.bucket(storage_bucket)
        else:
            self.bucket = storage.bucket()

    
    # ==================== Student Operations ====================
    
    def create_student(self, data: Dict) -> Dict:
        """
        Create a new student in Firestore
        
        Args:
            data (dict): Student data including name, nim, email, phone, rfid_uid, photo_url
            
        Returns:
            dict: Created student document with ID
        """
        try:
            # Add timestamps
            data['created_at'] = firestore.SERVER_TIMESTAMP
            data['updated_at'] = firestore.SERVER_TIMESTAMP
            
            # Create student document
            doc_ref = self.db.collection('students').document()
            doc_ref.set(data)
            
            # Get the created document
            student = doc_ref.get().to_dict()
            student['student_id'] = doc_ref.id
            
            logger.info(f"Created student: {student['name']} (NIM: {student['nim']})")
            return student
            
        except Exception as e:
            logger.error(f"Error creating student: {str(e)}")
            raise
    
    def get_student_by_uid(self, rfid_uid: str) -> Optional[Dict]:
        """
        Get student by RFID UID
        
        Args:
            rfid_uid (str): RFID card UID
            
        Returns:
            dict or None: Student data if found, None otherwise
        """
        try:
            students_ref = self.db.collection('students')
            query = students_ref.where(filter=FieldFilter('rfid_uid', '==', rfid_uid)).limit(1)
            docs = query.stream()
            
            for doc in docs:
                student = doc.to_dict()
                student['student_id'] = doc.id
                logger.info(f"Found student by UID {rfid_uid}: {student['name']}")
                return student
            
            logger.warning(f"No student found with UID: {rfid_uid}")
            return None
            
        except Exception as e:
            logger.error(f"Error getting student by UID: {str(e)}")
            raise
    
    def get_student_by_nim(self, nim: str) -> Optional[Dict]:
        """
        Get student by NIM (for validation during registration)
        
        Args:
            nim (str): Student NIM
            
        Returns:
            dict or None: Student data if found, None otherwise
        """
        try:
            students_ref = self.db.collection('students')
            query = students_ref.where(filter=FieldFilter('nim', '==', nim)).limit(1)
            docs = query.stream()
            
            for doc in docs:
                student = doc.to_dict()
                student['student_id'] = doc.id
                return student
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting student by NIM: {str(e)}")
            raise
    
    # ==================== Tool Operations ====================
    
    def create_tool(self, data: Dict) -> Dict:
        """
        Create a new tool in Firestore
        
        Args:
            data (dict): Tool data including name, rfid_uid, category
            
        Returns:
            dict: Created tool document with ID
        """
        try:
            # Set default status
            data['status'] = data.get('status', 'available')
            data['created_at'] = firestore.SERVER_TIMESTAMP
            
            # Create tool document
            doc_ref = self.db.collection('tools').document()
            doc_ref.set(data)
            
            # Get the created document
            tool = doc_ref.get().to_dict()
            tool['tool_id'] = doc_ref.id
            
            logger.info(f"Created tool: {tool['name']} (UID: {tool['rfid_uid']})")
            return tool
            
        except Exception as e:
            logger.error(f"Error creating tool: {str(e)}")
            raise
    
    def get_tool_by_uid(self, rfid_uid: str) -> Optional[Dict]:
        """
        Get tool by RFID UID
        
        Args:
            rfid_uid (str): RFID tag UID
            
        Returns:
            dict or None: Tool data if found, None otherwise
        """
        try:
            tools_ref = self.db.collection('tools')
            query = tools_ref.where(filter=FieldFilter('rfid_uid', '==', rfid_uid)).limit(1)
            docs = query.stream()
            
            for doc in docs:
                tool = doc.to_dict()
                tool['tool_id'] = doc.id
                logger.info(f"Found tool by UID {rfid_uid}: {tool['name']}")
                return tool
            
            logger.warning(f"No tool found with UID: {rfid_uid}")
            return None
            
        except Exception as e:
            logger.error(f"Error getting tool by UID: {str(e)}")
            raise
    
    def update_tool_status(self, tool_id: str, status: str):
        """
        Update tool status (available/borrowed)
        
        Args:
            tool_id (str): Tool document ID
            status (str): New status ('available' or 'borrowed')
        """
        try:
            tool_ref = self.db.collection('tools').document(tool_id)
            tool_ref.update({
                'status': status,
                'updated_at': firestore.SERVER_TIMESTAMP
            })
            logger.info(f"Updated tool {tool_id} status to: {status}")
            
        except Exception as e:
            logger.error(f"Error updating tool status: {str(e)}")
            raise
    
    # ==================== Transaction Operations ====================
    
    def create_transaction(self, data: Dict) -> Dict:
        """
        Create a transaction record (borrow or return)
        
        Args:
            data (dict): Transaction data
            
        Returns:
            dict: Created transaction document with ID
        """
        try:
            data['created_at'] = firestore.SERVER_TIMESTAMP
            
            # Create transaction document
            doc_ref = self.db.collection('transactions').document()
            doc_ref.set(data)
            
            # Get the created document
            transaction = doc_ref.get().to_dict()
            transaction['transaction_id'] = doc_ref.id
            
            logger.info(f"Created transaction: {transaction['status']} - "
                       f"Student: {transaction['student_name']}, Tool: {transaction['tool_name']}")
            return transaction
            
        except Exception as e:
            logger.error(f"Error creating transaction: {str(e)}")
            raise
    
    def get_recent_transactions(self, limit: int = 5) -> List[Dict]:
        """
        Get recent transactions ordered by creation time
        
        Args:
            limit (int): Maximum number of transactions to return
            
        Returns:
            list: List of recent transaction documents
        """
        try:
            transactions_ref = self.db.collection('transactions')
            query = transactions_ref.order_by('created_at', direction=firestore.Query.DESCENDING).limit(limit)
            docs = query.stream()
            
            transactions = []
            for doc in docs:
                transaction = doc.to_dict()
                transaction['transaction_id'] = doc.id
                transactions.append(transaction)
            
            logger.info(f"Retrieved {len(transactions)} recent transactions")
            return transactions
            
        except Exception as e:
            logger.error(f"Error getting recent transactions: {str(e)}")
            raise
    
    def get_active_borrow(self, student_id: str, tool_id: str) -> Optional[Dict]:
        """
        Check if there's an active borrow transaction for a student-tool pair
        
        Args:
            student_id (str): Student document ID
            tool_id (str): Tool document ID
            
        Returns:
            dict or None: Active borrow transaction if found, None otherwise
        """
        try:
            transactions_ref = self.db.collection('transactions')
            query = (transactions_ref
                    .where(filter=FieldFilter('student_id', '==', student_id))
                    .where(filter=FieldFilter('tool_id', '==', tool_id))
                    .where(filter=FieldFilter('status', '==', 'borrowed'))
                    .limit(1))
            docs = query.stream()
            
            for doc in docs:
                transaction = doc.to_dict()
                transaction['transaction_id'] = doc.id
                return transaction
            
            return None
            
        except Exception as e:
            logger.error(f"Error checking active borrow: {str(e)}")
            raise
    
    def update_transaction_return(self, transaction_id: str):
        """
        Update transaction to mark tool as returned
        
        Args:
            transaction_id (str): Transaction document ID
        """
        try:
            transaction_ref = self.db.collection('transactions').document(transaction_id)
            transaction_ref.update({
                'return_time': firestore.SERVER_TIMESTAMP,
                'status': 'returned'
            })
            logger.info(f"Updated transaction {transaction_id} to returned")
            
        except Exception as e:
            logger.error(f"Error updating transaction return: {str(e)}")
            raise
    
    # ==================== Storage Operations ====================
    
    def upload_photo(self, file_path: str, student_id: str) -> str:
        """
        Upload photo to Firebase Storage
        
        Args:
            file_path (str): Path to local file
            student_id (str): Student ID (used in storage path)
            
        Returns:
            str: Public URL of uploaded photo
        """
        try:
            # Generate storage path
            filename = os.path.basename(file_path)
            blob_path = f"student_photos/{student_id}/{filename}"
            
            # Upload file
            blob = self.bucket.blob(blob_path)
            blob.upload_from_filename(file_path)
            
            # Make public and get URL
            blob.make_public()
            public_url = blob.public_url
            
            logger.info(f"Uploaded photo for student {student_id}")
            return public_url
            
        except Exception as e:
            logger.error(f"Error uploading photo: {str(e)}")
            raise
