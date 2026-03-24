"""
Task factory for creating TaskProcessor instances.
"""

from typing import Optional, Callable, Dict, Any

from .base import Task, TaskChunk
from .types import TaskProcessorConfig
from .storage import BaseTaskStorage, InMemoryTaskStorage, create_task_storage
from .summarizer import TaskSummarizer, SkipChecker


class TaskProcessor:
    """
    Asynchronous task-level processor.
    
    Detects task boundaries and generates summaries when tasks complete.
    
    Reference: Local Plugin src/ingest/task-processor.ts
    """
    
    TRIVIAL_PATTERNS = [
        # Simple greetings/tests in multiple languages
        r"^(test|testing|hello|hi|hey|ok|okay|yes|no|yeah|nope|sure|thanks|thank you|thx|ping|pong|哈哈|好的|嗯|是的|不是|谢谢|你好|测试)\s*[.!?。！？]*$",
        # Repeated characters
        r"^(aaa+|bbb+|xxx+|zzz+|123+|asdf+|qwer+|haha+|lol+|hmm+)\s*$",
        # Only punctuation/symbols
        r"^[\s\p{P}\p{S}]*$",
    ]
    
    SKIP_REASONS = {
        "noChunks": "该任务没有对话内容，已自动跳过。",
    }
    
    def __init__(
        self,
        storage: BaseTaskStorage,
        llm_call_fn: Callable[[str], str],
        config: Optional[TaskProcessorConfig] = None,
        on_task_completed: Optional[Callable[[Task], None]] = None
    ):
        """
        Args:
            storage: Task storage backend
            llm_call_fn: LLM call function for summarization
            config: Processor configuration
            on_task_completed: Callback when task is completed
        """
        self.storage = storage
        self.config = config or TaskProcessorConfig()
        self.summarizer = TaskSummarizer(llm_call_fn)
        self.skip_checker = SkipChecker(
            min_chunks=self.config.min_chunks_for_summary,
            min_turns=self.config.min_conversation_turns,
            min_content_len=self.config.min_content_length,
            min_content_len_cjk=self.config.min_content_length_cjk,
            max_tool_ratio=self.config.max_tool_ratio,
            min_unique_ratio=self.config.min_unique_ratio
        )
        self.on_task_completed = on_task_completed
        self.processing = False
    
    async def on_chunks_ingested(
        self,
        session_key: str,
        latest_timestamp: float,
        owner: Optional[str] = None
    ) -> None:
        """
        Called after new chunks are ingested.
        
        Determines if a new task boundary was crossed and handles transition.
        """
        owner = owner or "agent:main"
        await self._detect_and_process(session_key, latest_timestamp, owner)
    
    async def _detect_and_process(
        self,
        session_key: str,
        latest_timestamp: float,
        owner: str
    ) -> None:
        """Detect task boundaries and process"""
        # Finalize any active tasks from different sessions
        active_tasks = self.storage.get_active_tasks(owner)
        for task in active_tasks:
            if task.session_key != session_key:
                await self._finalize_task(task)
        
        # Get or create active task for this session
        active_task = self.storage.get_active_task(session_key, owner)
        
        if not active_task:
            active_task = self._create_new_task(session_key, latest_timestamp, owner)
        
        await self._process_chunks_incrementally(active_task, session_key, latest_timestamp, owner)
    
    async def _process_chunks_incrementally(
        self,
        active_task: Task,
        session_key: str,
        latest_timestamp: float,
        owner: str
    ) -> None:
        """Process unassigned chunks one user-turn at a time"""
        unassigned = self.storage.get_unassigned_chunks(session_key)
        if not unassigned:
            return
        
        task_chunks = self.storage.get_chunks_by_task(active_task.id)
        
        # Time gap check
        if task_chunks:
            last_task_ts = max(c.created_at for c in task_chunks)
            first_unassigned_ts = min(c.created_at for c in unassigned)
            gap = first_unassigned_ts - last_task_ts
            
            if gap > self.config.task_idle_timeout_ms:
                await self._finalize_task(active_task)
                new_task = self._create_new_task(session_key, latest_timestamp, owner)
                return await self._process_chunks_incrementally(
                    new_task, session_key, latest_timestamp, owner
                )
        
        turns = self._group_into_turns(unassigned)
        if not turns:
            self._assign_chunks_to_task(unassigned, active_task.id)
            return
        
        current_task = active_task
        current_task_chunks = list(task_chunks)
        
        for turn in turns:
            user_chunk = next((c for c in turn if c.role == 'user'), None)
            
            if not user_chunk:
                self._assign_chunks_to_task(turn, current_task.id)
                current_task_chunks.extend(turn)
                continue
            
            # Time gap check per turn
            if current_task_chunks:
                last_ts = max(c.created_at for c in current_task_chunks)
                if user_chunk.created_at - last_ts > self.config.task_idle_timeout_ms:
                    await self._finalize_task(current_task)
                    current_task = self._create_new_task(session_key, user_chunk.created_at, owner)
                    current_task_chunks = []
            
            # Need at least 1 user turn before LLM judgment
            existing_user_count = sum(1 for c in current_task_chunks if c.role == 'user')
            if existing_user_count < 1:
                self._assign_chunks_to_task(turn, current_task.id)
                current_task_chunks.extend(turn)
                continue
            
            # LLM topic judgment
            context = self._build_context_summary(current_task_chunks)
            new_msg = user_chunk.content[:500]
            
            result = self.summarizer.judge_new_topic_sync(context, new_msg)
            
            if result.is_same_topic:
                self._assign_chunks_to_task(turn, current_task.id)
                current_task_chunks.extend(turn)
            else:
                await self._finalize_task(current_task)
                current_task = self._create_new_task(session_key, user_chunk.created_at, owner)
                current_task_chunks = []
                self._assign_chunks_to_task(turn, current_task.id)
                current_task_chunks.extend(turn)
        
        # Mark task as still active
        self.storage.update_task(current_task.id, {'ended_at': None})
    
    def _group_into_turns(self, chunks: list) -> list:
        """Group chunks into user turns"""
        turns = []
        current = []
        
        for c in chunks:
            if c.role == 'user' and current:
                turns.append(current)
                current = []
            current.append(c)
        
        if current:
            turns.append(current)
        
        return turns
    
    def _build_context_summary(self, chunks: list) -> str:
        """Build context from existing task chunks"""
        conversational = [c for c in chunks if c.role in ('user', 'assistant')]
        if not conversational:
            return ""
        
        def format_chunk(c):
            label = 'User' if c.role == 'user' else 'Assistant'
            max_len = 500 if c.role == 'user' else 200
            text = c.summary or c.content[:max_len]
            return f"[{label}]: {text}"
        
        if len(conversational) <= 10:
            return '\n'.join(format_chunk(c) for c in conversational)
        
        opening = [format_chunk(c) for c in conversational[:6]]
        recent = [format_chunk(c) for c in conversational[-4:]]
        
        return '\n'.join([
            "--- Task opening ---",
            *opening,
            "--- Recent exchanges ---",
            *recent
        ])
    
    def _create_new_task(
        self,
        session_key: str,
        timestamp: float,
        owner: str = "agent:main"
    ) -> Task:
        """Create a new task"""
        task = Task(
            id=str(uuid.uuid4()),
            session_key=session_key,
            title="",
            summary="",
            status="active",
            owner=owner,
            started_at=timestamp,
            updated_at=timestamp
        )
        return self.storage.create_task(task)
    
    def _assign_chunks_to_task(self, chunks: list, task_id: str) -> None:
        """Assign chunks to a task"""
        for chunk in chunks:
            self.storage.set_chunk_task_id(chunk.id, task_id)
    
    async def _finalize_task(self, task: Task) -> None:
        """Finalize a task by generating summary"""
        chunks = self.storage.get_chunks_by_task(task.id)
        
        if not chunks:
            self.storage.update_task(task.id, {
                'title': 'Untitled Task',
                'summary': self.SKIP_REASONS['noChunks'],
                'status': 'skipped'
            })
            return
        
        # Check if should skip
        skip_reason, skip_message = self.skip_checker.check(chunks)
        
        if skip_reason:
            title = self._generate_title_fallback(chunks)
            self.storage.update_task(task.id, {
                'title': title,
                'summary': skip_message,
                'status': 'skipped',
                'ended_at': datetime.now().timestamp() * 1000
            })
            return
        
        # Build conversation text
        conversation_text = self._build_conversation_text(chunks)
        
        # Generate summary
        try:
            summary = self.summarizer.summarize_task_sync(conversation_text)
            title, body = self._parse_title_from_summary(summary)
        except Exception:
            body = self._fallback_summary(chunks)
            title = self._generate_title_fallback(chunks)
        
        if not title:
            title = self._generate_title_fallback(chunks)
        
        self.storage.update_task(task.id, {
            'title': title,
            'summary': body,
            'status': 'completed',
            'ended_at': datetime.now().timestamp() * 1000
        })
        
        # Call completion callback
        if self.on_task_completed:
            updated_task = self.storage.get_task(task.id)
            if updated_task:
                self.on_task_completed(updated_task)
    
    def _build_conversation_text(self, chunks: list) -> str:
        """Build conversation text from chunks"""
        lines = []
        for c in chunks:
            label = c.role.capitalize() if c.role else 'Unknown'
            if c.role == 'user':
                label = 'User'
            elif c.role == 'assistant':
                label = 'Assistant'
            elif c.role == 'tool':
                label = 'Tool'
            lines.append(f"[{label}]: {c.content}")
        return '\n\n'.join(lines)
    
    def _parse_title_from_summary(self, summary: str) -> tuple:
        """Parse title from LLM summary"""
        import re
        patterns = [
            r'📌\s*Title\s*\n(.+)',
            r'📌\s*标题\s*\n(.+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, summary, re.IGNORECASE | re.MULTILINE)
            if match:
                title = match.group(1).strip()
                body = re.sub(pattern, '', summary, flags=re.IGNORECASE | re.MULTILINE).strip()
                return title, body
        
        return '', summary
    
    def _generate_title_fallback(self, chunks: list) -> str:
        """Generate title from chunks as fallback"""
        for c in chunks:
            if c.role != 'user':
                continue
            content = c.content.strip()
            if len(content) > 200:
                continue
            import re
            if re.match(r'session\.startup|Session Startup|/new|/reset', content, re.IGNORECASE):
                continue
            return content[:80]
        return "Untitled Task"
    
    def _fallback_summary(self, chunks: list) -> str:
        """Generate fallback summary"""
        title = self._generate_title_fallback(chunks)
        summaries = [c.summary for c in chunks if c.summary]
        
        lines = [
            "🎯 Goal",
            title,
            "",
            "📋 Key Steps",
            *[f"- {s}" for s in summaries[:20]]
        ]
        return '\n'.join(lines)


from datetime import datetime
import uuid
