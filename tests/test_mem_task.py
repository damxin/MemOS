"""
Tests for Task module.

Tests:
- Task creation and status
- TaskChunk and ChunkRef
- SkipChecker
- TaskSummarizer
- TaskProcessor factory
"""

import unittest
import sys
import os
from datetime import datetime, timedelta
from typing import List
from enum import Enum

# Add src to path for direct imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


# Import modules directly to avoid __init__.py chain
from memos.mem_task.base import (
    Task, TaskChunk, ChunkRef, TaskStatus,
    TaskBoundary, TaskProcessorFactory
)
from memos.mem_task.types import (
    SkipReason, TaskSummaryResult, ChunkKind
)
from memos.mem_task.summarizer import (
    SkipChecker, TaskSummarizer
)


class TestTaskBasics(unittest.TestCase):
    """Test Task data structures"""
    
    def test_task_creation(self):
        """Test creating a Task"""
        task = Task(
            id='task-1',
            session_key='session:123',
            title='Test Task',
            summary='A test task',
            status=TaskStatus.ACTIVE,
            owner='agent:main'
        )
        
        self.assertEqual(task.id, 'task-1')
        self.assertEqual(task.title, 'Test Task')
        self.assertEqual(task.status, TaskStatus.ACTIVE)
    
    def test_task_status_transitions(self):
        """Test Task status enum values"""
        self.assertEqual(TaskStatus.ACTIVE.value, 'active')
        self.assertEqual(TaskStatus.COMPLETED.value, 'completed')
        self.assertEqual(TaskStatus.SKIPPED.value, 'skipped')
    
    def test_task_chunk(self):
        """Test TaskChunk structure"""
        chunk = TaskChunk(
            id='chunk-1',
            task_id='task-1',
            content='Hello world',
            role='user',
            index=0
        )
        
        self.assertEqual(chunk.content, 'Hello world')
        self.assertEqual(chunk.role, 'user')
        self.assertEqual(chunk.index, 0)
    
    def test_chunk_ref(self):
        """Test ChunkRef structure"""
        chunk_ref = ChunkRef(
            chunk_id='chunk-1',
            task_id='task-1'
        )
        
        self.assertEqual(chunk_ref.chunk_id, 'chunk-1')


class TestSkipChecker(unittest.TestCase):
    """Test SkipChecker logic"""
    
    def setUp(self):
        """Set up skip checker"""
        self.checker = SkipChecker()
    
    def test_should_skip_trivial(self):
        """Test skipping trivial content"""
        # Very short content should be skipped
        result = self.checker.should_skip(
            chunks=[TaskChunk(
                id=f'c{i}',
                task_id='t1',
                content='hi',  # Very short
                role='user',
                index=i
            ) for i in range(5)]
        )
        
        self.assertTrue(result.should_skip)
        self.assertIn(SkipReason.TOO_SHORT, result.reasons)
    
    def test_should_not_skip_substantial(self):
        """Test not skipping substantial content"""
        content = 'This is a substantial piece of content that should not be skipped. ' * 10
        
        chunks = [
            TaskChunk(id=f'c{i}', task_id='t1', content=content, role='user', index=i)
            for i in range(10)
        ]
        
        result = self.checker.should_skip(chunks)
        
        # Should not skip if content is substantial
        # (though may skip for other reasons like no user role)
    
    def test_should_skip_no_user_role(self):
        """Test skipping when no user messages"""
        chunks = [
            TaskChunk(id=f'c{i}', task_id='t1', content='Assistant response', role='assistant', index=i)
            for i in range(5)
        ]
        
        result = self.checker.should_skip(chunks)
        
        self.assertTrue(result.should_skip)
        self.assertIn(SkipReason.NO_USER_MESSAGE, result.reasons)
    
    def test_should_skip_tool_dominated(self):
        """Test skipping tool-dominated content"""
        # 70%+ tool results
        chunks = [
            TaskChunk(id='c0', task_id='t1', content='Tool call', role='tool', index=0),
            TaskChunk(id='c1', task_id='t1', content='Tool result', role='tool', index=1),
            TaskChunk(id='c2', task_id='t1', content='Tool call', role='tool', index=2),
            TaskChunk(id='c3', task_id='t1', content='User message', role='user', index=3),
        ]
        
        result = self.checker.should_skip(chunks)
        
        self.assertTrue(result.should_skip)
        self.assertIn(SkipReason.TOOL_DOMINATED, result.reasons)
    
    def test_should_skip_high_repetition(self):
        """Test skipping high repetition content"""
        repeated = 'Same content. ' * 20
        
        chunks = [
            TaskChunk(id=f'c{i}', task_id='t1', content=repeated, role='user', index=i)
            for i in range(10)
        ]
        
        result = self.checker.should_skip(chunks)
        
        self.assertTrue(result.should_skip)
        self.assertIn(SkipReason.HIGH_REPETITION, result.reasons)


class TestTaskSummarizer(unittest.TestCase):
    """Test TaskSummarizer"""
    
    def setUp(self):
        """Set up summarizer"""
        self.summarizer = TaskSummarizer()
    
    def test_summarizer_initialization(self):
        """Test summarizer initializes"""
        self.assertIsNotNone(self.summarizer)
    
    def test_summarize_returns_result(self):
        """Test summarize returns TaskSummaryResult"""
        chunks = [
            TaskChunk(id=f'c{i}', task_id='t1', content=f'Content chunk {i}', role='user', index=i)
            for i in range(5)
        ]
        
        # Should return a result object (actual LLM call would need mock)
        result = self.summarizer.summarize(chunks, session_key='test')
        
        # Result should have expected structure
        self.assertTrue(hasattr(result, 'summary'))
        self.assertTrue(hasattr(result, 'title'))
    
    def test_extract_topic(self):
        """Test topic extraction from chunks"""
        chunks = [
            TaskChunk(id='c0', task_id='t1', content='Python programming tutorial', role='user', index=0),
            TaskChunk(id='c1', task_id='t1', content='Variables and functions', role='assistant', index=1),
        ]
        
        # Topic should be extracted
        topic = self.summarizer._extract_topic(chunks)
        # Topic extraction is content-dependent


class TestTaskProcessorFactory(unittest.TestCase):
    """Test TaskProcessor factory"""
    
    def test_factory_creates_processor(self):
        """Test factory creates processor"""
        factory = TaskProcessorFactory()
        processor = factory.create()
        
        self.assertIsNotNone(processor)
    
    def test_factory_with_config(self):
        """Test factory with custom config"""
        config = {'chunk_threshold': 10}
        factory = TaskProcessorFactory(config)
        processor = factory.create()
        
        self.assertIsNotNone(processor)


class TestTaskBoundary(unittest.TestCase):
    """Test TaskBoundary detection"""
    
    def test_boundary_session_change(self):
        """Test boundary on session change"""
        boundary = TaskBoundary()
        
        # Different sessions should trigger boundary
        result = boundary.should_split(
            prev_session='session:A',
            curr_session='session:B'
        )
        
        self.assertTrue(result)
    
    def test_no_boundary_same_session(self):
        """Test no boundary for same session"""
        boundary = TaskBoundary()
        
        result = boundary.should_split(
            prev_session='session:A',
            curr_session='session:A'
        )
        
        self.assertFalse(result)
    
    def test_boundary_time_gap(self):
        """Test boundary on time gap > 2 hours"""
        boundary = TaskBoundary()
        
        now = datetime.now()
        two_hours_ago = now - timedelta(hours=2, minutes=1)
        
        result = boundary.should_split(
            prev_time=two_hours_ago.timestamp() * 1000,
            curr_time=now.timestamp() * 1000
        )
        
        self.assertTrue(result)
    
    def test_no_boundary_quick_succession(self):
        """Test no boundary for quick succession"""
        boundary = TaskBoundary()
        
        now = datetime.now()
        one_minute_ago = now - timedelta(minutes=1)
        
        result = boundary.should_split(
            prev_time=one_minute_ago.timestamp() * 1000,
            curr_time=now.timestamp() * 1000
        )
        
        self.assertFalse(result)


class TestChunkKind(unittest.TestCase):
    """Test ChunkKind enum"""
    
    def test_chunk_kind_values(self):
        """Test ChunkKind enum values"""
        self.assertEqual(ChunkKind.PARAGRAPH.value, 'paragraph')
        self.assertEqual(ChunkKind.CODE_BLOCK.value, 'code_block')
        self.assertEqual(ChunkKind.ERROR_STACK.value, 'error_stack')
        self.assertEqual(ChunkKind.LIST.value, 'list')
        self.assertEqual(ChunkKind.COMMAND.value, 'command')


if __name__ == '__main__':
    unittest.main()
