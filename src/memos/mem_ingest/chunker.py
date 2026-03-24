"""
Semantic text chunking.
"""

import re
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass
from enum import Enum


class ChunkKind(Enum):
    """Type of chunk"""
    PARAGRAPH = "paragraph"
    CODE_BLOCK = "code_block"
    ERROR_STACK = "error_stack"
    LIST = "list"
    COMMAND = "command"


@dataclass
class RawChunk:
    """A raw chunk before processing"""
    content: str
    kind: ChunkKind


# Constants
MAX_CHUNK_CHARS = 3000
MIN_CHUNK_CHARS = 40
IDEAL_CHUNK_CHARS = 1500

# Patterns
FENCED_CODE_RE = re.compile(r'^(`{3,})[^\n]*\n[\s\S]*?^\1\s*$', re.MULTILINE)

FUNC_OPEN_RE = re.compile(
    r'^[ \t]*(?:(?:export\s+)?(?:async\s+)?(?:function|class|const\s+\w+\s*=\s*(?:\([^)]*\)|[^=])*=>)'
    r'|(?:def |class )|(?:func |fn |pub\s+fn )|(?:public |private |protected |static )+.*\{)\s*$'
)

BLOCK_CLOSE_RE = re.compile(r'^[ \t]*[}\]]\s*;?\s*$')

ERROR_STACK_RE = re.compile(
    r'(?:(?:Error|Exception|Traceback)[^\n]*\n(?:\s+at\s+[^\n]+\n?|.*File "[^\n]+\n?|.*line \d+[^\n]*\n?){2,})',
    re.MULTILINE
)

LIST_BLOCK_RE = re.compile(r'(?:^[\s]*[-*•]\s+.+\n?){3,}', re.MULTILINE)

COMMAND_LINE_RE = re.compile(r'^(?:\$|>|#)\s+.+$', re.MULTILINE)


class TextChunker:
    """
    Semantic-aware text chunking.
    
    Chunks text by:
    1. Extracting fenced code blocks as whole units
    2. Detecting unfenced code regions (functions/classes)
    3. Extracting error stacks, list blocks, command lines
    4. Splitting prose at paragraph boundaries
    5. Merging short adjacent chunks
    6. Splitting oversized chunks
    
    Reference: Local Plugin src/ingest/chunker.ts
    """
    
    def __init__(
        self,
        max_chars: int = MAX_CHUNK_CHARS,
        min_chars: int = MIN_CHUNK_CHARS,
        ideal_chars: int = IDEAL_CHUNK_CHARS
    ):
        self.max_chars = max_chars
        self.min_chars = min_chars
        self.ideal_chars = ideal_chars
    
    def chunk(self, text: str) -> List[str]:
        """
        Chunk text into pieces.
        
        Args:
            text: Input text
        
        Returns:
            List of text chunks
        """
        if not text or not text.strip():
            return []
        
        raw_chunks = self._semantic_chunk(text)
        merged = self._merge_small_chunks(raw_chunks)
        final = self._split_oversized(merged)
        
        if not final:
            return [text.strip()]
        
        return final
    
    def _semantic_chunk(self, text: str) -> List[RawChunk]:
        """Extract semantic chunks from text"""
        remaining = text
        slots: List[Tuple[str, str, ChunkKind]] = []
        counter = 0
        
        def ph(content: str, kind: ChunkKind = ChunkKind.PARAGRAPH) -> str:
            nonlocal counter
            tag = f"\x00SLOT_{counter}\x00"
            slots.append((tag, content.strip(), kind))
            counter += 1
            return tag
        
        # Extract fenced code blocks
        remaining = FENCED_CODE_RE.sub(
            lambda m: ph(m.group(), ChunkKind.CODE_BLOCK),
            remaining
        )
        
        # Extract brace blocks (functions/classes)
        remaining = self._extract_brace_blocks(remaining, ph)
        
        # Extract structural patterns
        remaining = ERROR_STACK_RE.sub(
            lambda m: ph(m.group(), ChunkKind.ERROR_STACK),
            remaining
        )
        remaining = LIST_BLOCK_RE.sub(
            lambda m: ph(m.group(), ChunkKind.LIST),
            remaining
        )
        remaining = COMMAND_LINE_RE.sub(
            lambda m: ph(m.group(), ChunkKind.COMMAND),
            remaining
        )
        
        # Split at paragraph boundaries
        raw: List[RawChunk] = []
        sections = re.split(r'\n{2,}', remaining)
        
        for sec in sections:
            trimmed = sec.strip()
            if not trimmed:
                continue
            
            if '\x00SLOT_' in trimmed:
                parts = re.split(r'(\x00SLOT_\d+\x00)', trimmed)
                for part in parts:
                    slot = next((s for s in slots if s[0] == part), None)
                    if slot:
                        raw.append(RawChunk(content=slot[1], kind=slot[2]))
                    elif part.strip() and len(part.strip()) >= self.min_chars:
                        raw.append(RawChunk(content=part.strip(), kind=ChunkKind.PARAGRAPH))
            elif len(trimmed) >= self.min_chars:
                raw.append(RawChunk(content=trimmed, kind=ChunkKind.PARAGRAPH))
        
        # Add any orphaned slots
        for tag, content, kind in slots:
            if not any(c.content == content for c in raw):
                raw.append(RawChunk(content=content, kind=kind))
        
        return raw
    
    def _extract_brace_blocks(
        self,
        text: str,
        ph: callable
    ) -> str:
        """Extract function/class bodies using brace matching"""
        lines = text.split('\n')
        result: List[str] = []
        block_lines: List[str] = []
        depth = 0
        in_block = False
        
        for i, line in enumerate(lines):
            # Skip slots
            if '\x00SLOT_' in line:
                if in_block:
                    block_lines.append(line)
                else:
                    result.append(line)
                continue
            
            if not in_block and FUNC_OPEN_RE.match(line):
                in_block = True
                block_lines = [line]
                depth = self._count_braces(line)
                if depth <= 0:
                    depth = 1
                continue
            
            if in_block:
                block_lines.append(line)
                depth += self._count_braces(line)
                
                if depth <= 0 or (BLOCK_CLOSE_RE.match(line) and depth <= 0):
                    block = '\n'.join(block_lines)
                    if len(block.strip()) >= self.min_chars:
                        result.append(ph(block, ChunkKind.CODE_BLOCK))
                    else:
                        result.append(block)
                    in_block = False
                    block_lines = []
                    depth = 0
            else:
                result.append(line)
        
        # Handle remaining block
        if block_lines:
            block = '\n'.join(block_lines)
            if len(block.strip()) >= self.min_chars:
                result.append(ph(block, ChunkKind.CODE_BLOCK))
            else:
                result.append(block)
        
        return '\n'.join(result)
    
    def _count_braces(self, line: str) -> int:
        """Count braces in line"""
        d = 0
        for ch in line:
            if ch in '{(':
                d += 1
            elif ch in '})':
                d -= 1
        return d
    
    def _merge_small_chunks(self, chunks: List[RawChunk]) -> List[RawChunk]:
        """Merge small adjacent chunks"""
        if len(chunks) <= 1:
            return chunks
        
        merged: List[RawChunk] = []
        buf: Optional[RawChunk] = None
        
        for c in chunks:
            if buf is None:
                buf = RawChunk(content=c.content, kind=c.kind)
                continue
            
            # Check if both chunks are small
            both_small = (
                len(buf.content) < self.ideal_chars and
                len(c.content) < self.ideal_chars
            )
            
            merged_len = len(buf.content) + len(c.content) + 2
            
            if both_small and merged_len <= self.max_chars:
                buf.content = buf.content + '\n\n' + c.content
            else:
                merged.append(buf)
                buf = RawChunk(content=c.content, kind=c.kind)
        
        if buf:
            merged.append(buf)
        
        return merged
    
    def _split_oversized(self, chunks: List[RawChunk]) -> List[str]:
        """Split oversized chunks at sentence boundaries"""
        result: List[str] = []
        
        for c in chunks:
            if len(c.content) <= self.max_chars:
                result.append(c.content)
            else:
                result.extend(self._split_chunk_at_sentence_boundary(c.content))
        
        return result
    
    def _split_chunk_at_sentence_boundary(self, text: str) -> List[str]:
        """Split text at sentence boundaries"""
        # Match sentences
        sentences = re.findall(
            r'[^.!?。！？\n]+(?:[.!?。！？]+|\n{2,})',
            text
        )
        
        if not sentences:
            sentences = [text]
        
        chunks: List[str] = []
        buf = ""
        
        for s in sentences:
            if len(buf) + len(s) > self.max_chars and buf:
                chunks.append(buf.strip())
                buf = ""
            buf += s
        
        if buf.strip() and len(buf.strip()) >= self.min_chars:
            chunks.append(buf.strip())
        
        return chunks


def chunk_by_characters(
    text: str,
    chunk_size: int = 1000,
    overlap: int = 100
) -> List[str]:
    """
    Simple character-based chunking with overlap.
    
    Args:
        text: Input text
        chunk_size: Size of each chunk
        overlap: Overlap between chunks
    
    Returns:
        List of text chunks
    """
    if len(text) <= chunk_size:
        return [text]
    
    chunks = []
    start = 0
    
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        chunks.append(chunk)
        start = end - overlap
    
    return chunks


def chunk_by_paragraphs(text: str) -> List[str]:
    """
    Split text by paragraph boundaries.
    
    Args:
        text: Input text
    
    Returns:
        List of paragraphs
    """
    paragraphs = re.split(r'\n{2,}', text)
    return [p.strip() for p in paragraphs if p.strip()]
