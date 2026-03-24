"""
Dashboard API - REST API for MemOS Dashboard.

Provides CRUD operations for:
- Memories
- Tasks
- Skills
- Analytics
"""

from .memories import MemoriesAPI
from .tasks import TasksAPI
from .skills import SkillsAPI
from .analytics import AnalyticsAPI


__all__ = [
    "MemoriesAPI",
    "TasksAPI",
    "SkillsAPI",
    "AnalyticsAPI",
]
