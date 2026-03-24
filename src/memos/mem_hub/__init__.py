"""
mem_hub - Hub-Client architecture for team memory sharing.

Provides:
- HubServer: Central server for memory sharing
- UserManager: User registration and authentication
- AuthHandler: Token-based authentication
- HubClient: Client SDK for connecting to Hub
"""

from .server import HubServer, HubConfig, ClientConnection, create_hub
from .user_manager import UserManager, HubUser
from .auth import AuthHandler, TokenManager, AuthToken
from .client import HubClient, HubClientConfig, LocalHubClient


__all__ = [
    # Server
    "HubServer",
    "HubConfig",
    "ClientConnection",
    "create_hub",
    # User
    "UserManager",
    "HubUser",
    # Auth
    "AuthHandler",
    "TokenManager",
    "AuthToken",
    # Client
    "HubClient",
    "HubClientConfig",
    "LocalHubClient",
]
