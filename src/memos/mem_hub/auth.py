"""
Authentication handling for Hub.
"""

from typing import Dict, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib
import secrets

from .user_manager import UserManager, HubUser


@dataclass
class AuthToken:
    """An authentication token"""
    token: str
    user_id: str
    created_at: float
    expires_at: float
    scopes: list


class TokenManager:
    """
    Manages authentication tokens.
    """
    
    def __init__(self, token_ttl: int = 86400):  # 24 hours default
        self._tokens: Dict[str, AuthToken] = {}
        self._user_tokens: Dict[str, list] = {}  # user_id -> list of tokens
        self._token_ttl = token_ttl
    
    def create_token(
        self,
        user_id: str,
        scopes: Optional[list] = None
    ) -> AuthToken:
        """Create a new auth token for a user"""
        token = secrets.token_urlsafe(32)
        now = datetime.now().timestamp()
        
        auth_token = AuthToken(
            token=token,
            user_id=user_id,
            created_at=now,
            expires_at=now + self._token_ttl,
            scopes=scopes or ['read', 'write']
        )
        
        self._tokens[token] = auth_token
        
        if user_id not in self._user_tokens:
            self._user_tokens[user_id] = []
        self._user_tokens[user_id].append(token)
        
        return auth_token
    
    def verify_token(self, token: str) -> Optional[AuthToken]:
        """
        Verify a token.
        
        Returns token info if valid, None if invalid or expired.
        """
        auth_token = self._tokens.get(token)
        if not auth_token:
            return None
        
        now = datetime.now().timestamp()
        if auth_token.expires_at < now:
            # Token expired, clean up
            self._revoke_token(token)
            return None
        
        return auth_token
    
    def revoke_token(self, token: str) -> bool:
        """Revoke a specific token"""
        return self._revoke_token(token)
    
    def _revoke_token(self, token: str) -> bool:
        """Internal revoke"""
        auth_token = self._tokens.get(token)
        if not auth_token:
            return False
        
        del self._tokens[token]
        
        user_tokens = self._user_tokens.get(auth_token.user_id, [])
        if token in user_tokens:
            user_tokens.remove(token)
        
        return True
    
    def revoke_all_user_tokens(self, user_id: str) -> int:
        """Revoke all tokens for a user"""
        tokens = self._user_tokens.get(user_id, [])
        for token in tokens:
            if token in self._tokens:
                del self._tokens[token]
        
        count = len(tokens)
        self._user_tokens[user_id] = []
        
        return count
    
    def refresh_token(self, token: str) -> Optional[AuthToken]:
        """Refresh a token, creating a new one with same scopes"""
        auth_token = self.verify_token(token)
        if not auth_token:
            return None
        
        # Revoke old token
        self._revoke_token(token)
        
        # Create new token
        return self.create_token(auth_token.user_id, auth_token.scopes)
    
    def get_user_tokens(self, user_id: str) -> list:
        """Get all active tokens for a user"""
        now = datetime.now().timestamp()
        active = []
        
        for token in self._user_tokens.get(user_id, []):
            auth_token = self._tokens.get(token)
            if auth_token and auth_token.expires_at > now:
                active.append(token)
        
        return active


class AuthHandler:
    """
    Handles authentication for Hub requests.
    """
    
    def __init__(self, user_manager: UserManager):
        self.user_manager = user_manager
        self.token_manager = TokenManager()
    
    def login(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        """
        Login a user.
        
        Returns token info if successful.
        """
        user = self.user_manager.authenticate(username, password)
        if not user:
            return None
        
        token = self.token_manager.create_token(user.id)
        
        return {
            'token': token.token,
            'user_id': user.id,
            'username': user.username,
            'expires_at': token.expires_at,
            'scopes': token.scopes
        }
    
    def logout(self, token: str) -> bool:
        """Logout a user (revoke token)"""
        return self.token_manager.revoke_token(token)
    
    def verify(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Verify a token.
        
        Returns user info if valid.
        """
        auth_token = self.token_manager.verify_token(token)
        if not auth_token:
            return None
        
        user = self.user_manager.get_user(auth_token.user_id)
        if not user or not user.is_active:
            return None
        
        return {
            'user_id': user.id,
            'username': user.username,
            'scopes': auth_token.scopes,
            'expires_at': auth_token.expires_at
        }
    
    def register(
        self,
        username: str,
        email: str,
        password: str
    ) -> Optional[Dict[str, Any]]:
        """
        Register a new user.
        
        Returns user info if successful.
        """
        user = self.user_manager.create_user(username, email, password)
        if not user:
            return None
        
        # Auto-login after registration
        token = self.token_manager.create_token(user.id)
        
        return {
            'user_id': user.id,
            'username': user.username,
            'email': user.email,
            'token': token.token,
            'expires_at': token.expires_at
        }
    
    def change_password(
        self,
        token: str,
        old_password: str,
        new_password: str
    ) -> bool:
        """Change user password"""
        auth_token = self.token_manager.verify_token(token)
        if not auth_token:
            return False
        
        user = self.user_manager.authenticate(
            auth_token.user_id.split(':')[0] if ':' in auth_token.user_id else auth_token.user_id,
            old_password
        )
        if not user:
            return False
        
        # Get user by ID
        actual_user = self.user_manager.get_user(auth_token.user_id)
        if not actual_user:
            # Try to find by token user_id format
            for u in self.user_manager._users.values():
                if u.id == auth_token.user_id:
                    actual_user = u
                    break
        
        if not actual_user:
            return False
        
        return bool(self.user_manager.update_user(
            actual_user.id,
            {'password': new_password}
        ))
