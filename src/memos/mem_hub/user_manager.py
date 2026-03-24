"""
User management for Hub.
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
import hashlib


@dataclass
class HubUser:
    """A user in the Hub system"""
    id: str
    username: str
    email: str
    password_hash: str
    created_at: float
    last_login: Optional[float] = None
    is_active: bool = True
    is_admin: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


class UserManager:
    """
    Manages users in the Hub system.
    
    Provides:
    - User registration
    - User authentication
    - User profile management
    """
    
    def __init__(self):
        self._users: Dict[str, HubUser] = {}
        self._username_index: Dict[str, str] = {}  # username -> user_id
        self._email_index: Dict[str, str] = {}  # email -> user_id
    
    def create_user(
        self,
        username: str,
        email: str,
        password: str,
        is_admin: bool = False,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[HubUser]:
        """
        Create a new user.
        
        Returns None if username or email already exists.
        """
        # Check for duplicates
        if username in self._username_index:
            return None
        if email in self._email_index:
            return None
        
        import uuid
        
        user_id = str(uuid.uuid4())
        password_hash = self._hash_password(password)
        
        user = HubUser(
            id=user_id,
            username=username,
            email=email,
            password_hash=password_hash,
            created_at=datetime.now().timestamp(),
            is_admin=is_admin,
            metadata=metadata or {}
        )
        
        self._users[user_id] = user
        self._username_index[username] = user_id
        self._email_index[email] = user_id
        
        return user
    
    def get_user(self, user_id: str) -> Optional[HubUser]:
        """Get user by ID"""
        return self._users.get(user_id)
    
    def get_user_by_username(self, username: str) -> Optional[HubUser]:
        """Get user by username"""
        user_id = self._username_index.get(username)
        if user_id:
            return self._users.get(user_id)
        return None
    
    def get_user_by_email(self, email: str) -> Optional[HubUser]:
        """Get user by email"""
        user_id = self._email_index.get(email)
        if user_id:
            return self._users.get(user_id)
        return None
    
    def authenticate(self, username: str, password: str) -> Optional[HubUser]:
        """
        Authenticate a user.
        
        Returns user if credentials are valid, None otherwise.
        """
        user = self.get_user_by_username(username)
        if not user:
            return None
        
        if not user.is_active:
            return None
        
        password_hash = self._hash_password(password)
        if user.password_hash != password_hash:
            return None
        
        # Update last login
        user.last_login = datetime.now().timestamp()
        
        return user
    
    def update_user(
        self,
        user_id: str,
        updates: Dict[str, Any]
    ) -> Optional[HubUser]:
        """
        Update user profile.
        
        Allowed updates: email, password, metadata, is_active
        """
        user = self._users.get(user_id)
        if not user:
            return None
        
        # Update allowed fields
        if 'email' in updates:
            new_email = updates['email']
            if new_email != user.email:
                # Check for duplicate
                if new_email in self._email_index:
                    return None
                del self._email_index[user.email]
                user.email = new_email
                self._email_index[new_email] = user_id
        
        if 'password' in updates:
            user.password_hash = self._hash_password(updates['password'])
        
        if 'metadata' in updates:
            user.metadata.update(updates['metadata'])
        
        if 'is_active' in updates:
            user.is_active = updates['is_active']
        
        if 'is_admin' in updates:
            user.is_admin = updates['is_admin']
        
        return user
    
    def delete_user(self, user_id: str) -> bool:
        """Delete a user"""
        user = self._users.get(user_id)
        if not user:
            return False
        
        del self._username_index[user.username]
        del self._email_index[user.email]
        del self._users[user_id]
        
        return True
    
    def list_users(
        self,
        is_active: Optional[bool] = None,
        is_admin: Optional[bool] = None
    ) -> List[HubUser]:
        """List users with optional filters"""
        results = list(self._users.values())
        
        if is_active is not None:
            results = [u for u in results if u.is_active == is_active]
        
        if is_admin is not None:
            results = [u for u in results if u.is_admin == is_admin]
        
        return results
    
    def get_stats(self) -> Dict[str, Any]:
        """Get user statistics"""
        active = sum(1 for u in self._users.values() if u.is_active)
        admins = sum(1 for u in self._users.values() if u.is_admin)
        
        return {
            'total_users': len(self._users),
            'active_users': active,
            'admin_users': admins
        }
    
    @staticmethod
    def _hash_password(password: str) -> str:
        """Hash a password"""
        return hashlib.sha256(password.encode()).hexdigest()[:32]
