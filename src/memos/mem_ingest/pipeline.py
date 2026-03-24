"""
Ingest pipeline for processing messages into memories.
"""

from typing import List, Optional, Callable, Dict, Any, AsyncIterator
from dataclasses import dataclass
from datetime import datetime
import asyncio

from .chunker import TextChunker, ChunkKind
from .dedup import Deduplicator, cosine_similarity
from .llm_judge import LLMJudge, SimpleJudge
from .types import (
    IngestMessage,
    IngestChunk,
    IngestResult,
    IngestConfig,
    ProcessingStatus
)


class IngestPipeline:
    """
    Main ingest pipeline for processing messages into memories.
    
    Pipeline stages:
    1. Receive message
    2. Chunk text
    3. Generate embeddings
    4. Check deduplication
    5. LLM judgment (if needed)
    6. Store chunks
    
    Reference: Local Plugin src/ingest/worker.ts
    """
    
    def __init__(
        self,
        embedder: Callable[[str], List[float]],
        storage,
        config: Optional[IngestConfig] = None,
        llm_call_fn: Optional[Callable[[str], str]] = None
    ):
        """
        Args:
            embedder: Function to generate embeddings
            storage: Storage backend for chunks
            config: Pipeline configuration
            llm_call_fn: Optional LLM call for judgment
        """
        self.embedder = embedder
        self.storage = storage
        self.config = config or IngestConfig()
        
        self.chunker = TextChunker(
            max_chars=self.config.max_chunk_chars,
            min_chars=self.config.min_chunk_chars
        )
        self.deduplicator = Deduplicator(
            embedder=embedder,
            llm_call_fn=llm_call_fn,
            vector_threshold=self.config.dedup_threshold,
            top_n=self.config.dedup_top_n
        )
        self.llm_judge = LLMJudge(llm_call_fn) if llm_call_fn else None
        self.simple_judge = SimpleJudge()
    
    async def process(
        self,
        messages: List[IngestMessage]
    ) -> List[IngestResult]:
        """
        Process messages through the ingest pipeline.
        
        Args:
            messages: List of messages to process
        
        Returns:
            List of ingest results
        """
        results = []
        
        for message in messages:
            try:
                result = await self._process_message(message)
                results.append(result)
            except Exception as e:
                results.append(IngestResult(
                    status=ProcessingStatus.ERROR,
                    error=str(e),
                    chunks_created=0
                ))
        
        return results
    
    async def _process_message(
        self,
        message: IngestMessage
    ) -> IngestResult:
        """Process a single message"""
        chunks_created = 0
        
        # Stage 1: Chunk text
        raw_chunks = self.chunker.chunk(message.content)
        
        if not raw_chunks:
            return IngestResult(
                status=ProcessingStatus.SKIPPED,
                reason="No content to process",
                chunks_created=0
            )
        
        # Stage 2: Process each chunk
        for chunk_text in raw_chunks:
            # Check for trivial content
            if self.simple_judge.is_trivial_content(chunk_text):
                continue
            
            if self.simple_judge.is_too_short(chunk_text, self.config.min_chunk_chars):
                continue
            
            # Stage 3: Generate embedding
            try:
                embedding = self.embedder(chunk_text[:self.config.embedding_max_chars])
            except Exception as e:
                continue
            
            # Stage 4: Check deduplication
            existing_chunks = self.storage.get_all_chunks(
                owner=message.owner,
                limit=1000
            )
            
            dedup_result = self.deduplicator.check_duplicate(
                chunk_text,
                existing_chunks,
                use_llm=self.config.use_llm_judgment
            )
            
            if dedup_result.is_duplicate:
                # Update existing chunk
                if dedup_result.duplicate_id:
                    self.storage.update_chunk(
                        chunk_id=dedup_result.duplicate_id,
                        updates={
                            'content': chunk_text,
                            'embedding': embedding,
                            'updated_at': datetime.now().timestamp() * 1000
                        }
                    )
                continue
            
            # Stage 5: Create new chunk
            chunk = IngestChunk(
                id="",  # Will be assigned by storage
                owner=message.owner,
                session_key=message.session_key,
                role=message.role,
                content=chunk_text,
                embedding=embedding,
                kind=self._detect_chunk_kind(chunk_text),
                metadata=message.metadata
            )
            
            chunk_id = self.storage.insert_chunk(chunk)
            chunks_created += 1
        
        return IngestResult(
            status=ProcessingStatus.COMPLETED,
            chunks_created=chunks_created
        )
    
    def _detect_chunk_kind(self, text: str) -> str:
        """Detect the kind of chunk"""
        # Check for code blocks
        if '```' in text or text.startswith('    '):
            return 'code_block'
        
        # Check for error stacks
        if any(err in text for err in ['Error:', 'Exception:', 'Traceback']):
            return 'error_stack'
        
        # Check for command lines
        if text.startswith('$') or text.startswith('>'):
            return 'command'
        
        # Check for lists
        lines = text.split('\n')
        if any(line.strip().startswith(('-', '*', '•')) for line in lines):
            return 'list'
        
        return 'paragraph'


class IngestWorker:
    """
    Background worker for processing ingest tasks.
    
    Handles:
    - Message queuing
    - Batch processing
    - Error handling
    - Retry logic
    """
    
    def __init__(
        self,
        pipeline: IngestPipeline,
        batch_size: int = 10,
        max_retries: int = 3
    ):
        """
        Args:
            pipeline: IngestPipeline to use
            batch_size: Number of messages to process in a batch
            max_retries: Maximum number of retries for failed messages
        """
        self.pipeline = pipeline
        self.batch_size = batch_size
        self.max_retries = max_retries
        self.queue: List[IngestMessage] = []
        self.processing = False
    
    async def add_message(self, message: IngestMessage) -> None:
        """Add a message to the processing queue"""
        self.queue.append(message)
        
        if len(self.queue) >= self.batch_size:
            await self.process_batch()
    
    async def process_batch(self) -> List[IngestResult]:
        """Process all queued messages"""
        if not self.queue:
            return []
        
        self.processing = True
        messages = self.queue[:self.batch_size]
        self.queue = self.queue[self.batch_size:]
        
        try:
            results = await self.pipeline.process(messages)
            return results
        finally:
            self.processing = False
    
    async def process_all(self) -> List[IngestResult]:
        """Process all remaining messages"""
        results = []
        
        while self.queue:
            batch_results = await self.process_batch()
            results.extend(batch_results)
        
        return results


@dataclass
class IngestStats:
    """Statistics for ingest operations"""
    total_processed: int = 0
    total_chunks_created: int = 0
    duplicates_skipped: int = 0
    errors: int = 0
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    
    @property
    def duration_ms(self) -> float:
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time) * 1000
        return 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'total_processed': self.total_processed,
            'total_chunks_created': self.total_chunks_created,
            'duplicates_skipped': self.duplicates_skipped,
            'errors': self.errors,
            'duration_ms': self.duration_ms
        }
