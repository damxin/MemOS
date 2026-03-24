"""
Task summarizer using LLM.
"""

import re
from typing import List, Optional, Callable, Dict, Any

from .base import TaskChunk, Task
from .types import TaskSummaryResult, TopicJudgmentResult, SkipReason


class TaskSummarizer:
    """
    Generates summaries for tasks using LLM.
    
    Supports:
    - Full task summarization
    - Title generation
    - Topic judgment (new topic vs same topic)
    - Skip detection
    """
    
    def __init__(
        self,
        llm_call_fn: Callable[[str], str],
        config: Optional[Dict[str, Any]] = None
    ):
        """
        Args:
            llm_call_fn: Function that takes a prompt and returns LLM response
            config: Configuration for summarization
        """
        self.llm_call = llm_call_fn
        self.config = config or {}
    
    async def summarize_task(self, conversation_text: str) -> str:
        """
        Generate a summary for a task conversation.
        
        Args:
            conversation_text: Combined text of all chunks in the task
        
        Returns:
            Summary text with title and body
        """
        prompt = self._build_summary_prompt(conversation_text)
        summary = await self._call_llm(prompt)
        return summary
    
    def summarize_task_sync(self, conversation_text: str) -> str:
        """Synchronous version of summarize_task"""
        prompt = self._build_summary_prompt(conversation_text)
        return self.llm_call(prompt)
    
    async def judge_new_topic(
        self,
        context_summary: str,
        new_message: str
    ) -> TopicJudgmentResult:
        """
        Judge whether a new user message represents a new topic.
        
        Args:
            context_summary: Summary of existing task context
            new_message: New user message to evaluate
        
        Returns:
            TopicJudgmentResult with is_new_topic flag
        """
        prompt = self._build_topic_judge_prompt(context_summary, new_message)
        response = await self._call_llm(prompt)
        return self._parse_topic_judge_response(response)
    
    def judge_new_topic_sync(
        self,
        context_summary: str,
        new_message: str
    ) -> TopicJudgmentResult:
        """Synchronous version of judge_new_topic"""
        prompt = self._build_topic_judge_prompt(context_summary, new_message)
        response = self.llm_call(prompt)
        return self._parse_topic_judge_response(response)
    
    async def generate_title(self, user_messages: List[str]) -> str:
        """
        Generate a title for a task based on user messages.
        
        Args:
            user_messages: List of user message contents
        
        Returns:
            Generated title
        """
        if not user_messages:
            return "Untitled Task"
        
        combined = "\n\n".join(user_messages[:3])
        prompt = self._build_title_prompt(combined)
        title = await self._call_llm(prompt)
        return title.strip() or "Untitled Task"
    
    def generate_title_sync(self, user_messages: List[str]) -> str:
        """Synchronous version of generate_title"""
        if not user_messages:
            return "Untitled Task"
        
        combined = "\n\n".join(user_messages[:3])
        prompt = self._build_title_prompt(combined)
        title = self.llm_call(prompt)
        return title.strip() or "Untitled Task"
    
    def _build_summary_prompt(self, conversation_text: str) -> str:
        """Build prompt for task summarization"""
        return f"""请为以下对话生成简洁的任务摘要。

要求：
1. 首先输出 📌 标题：<一句话概括任务主题>
2. 然后输出详细摘要，包括：
   - 用户的核心需求或问题
   - 助手的解决方案或回应
   - 关键的技术细节或结论

📌 标题：
"""
    
    def _build_topic_judge_prompt(
        self,
        context_summary: str,
        new_message: str
    ) -> str:
        """Build prompt for topic judgment"""
        return f"""判断新消息是否与之前的对话属于同一主题。

之前对话摘要：
{context_summary}

新用户消息：
{new_message}

请判断：新消息是否与之前的对话属于同一主题？

回答格式（仅回答数字）：
1 - 同一主题，继续当前任务
0 - 新主题，应该创建新任务
"""
    
    def _parse_topic_judge_response(self, response: str) -> TopicJudgmentResult:
        """Parse LLM response for topic judgment"""
        response = response.strip()
        
        # Look for explicit indicators
        if '0' in response and '1' not in response[:response.index('0')]:
            return TopicJudgmentResult(is_new_topic=True, confidence=1.0)
        elif response.startswith('1'):
            return TopicJudgmentResult(is_new_topic=False, confidence=1.0)
        
        # Try to extract number
        numbers = re.findall(r'\b([01])\b', response)
        if numbers:
            is_new = numbers[0] == '0'
            return TopicJudgmentResult(is_new_topic=is_new, confidence=0.8)
        
        # Default to same topic
        return TopicJudgmentResult(is_new_topic=None, confidence=0.5)
    
    def _build_title_prompt(self, user_messages: str) -> str:
        """Build prompt for title generation"""
        return f"""根据以下用户消息，生成一个简短的任务标题（不超过50字）：

{user_messages}

标题：
"""
    
    def _call_llm(self, prompt: str) -> str:
        """Call LLM - implementation depends on the LLM wrapper"""
        if hasattr(self.llm_call, '__call__'):
            result = self.llm_call(prompt)
            if hasattr(result, '__await__'):
                # It's a coroutine
                import asyncio
                return asyncio.get_event_loop().run_until_complete(result)
            return result
        return str(result)


class SkipChecker:
    """
    Checks if a task should be skipped from summarization.
    
    Based on various heuristics like content length,
    conversation turns, trivial patterns, etc.
    """
    
    TRIVIAL_PATTERNS = [
        re.compile(r"^(test|testing|hello|hi|hey|ok|okay|yes|no|yeah|nope|sure|thanks|thank you|thx|ping|pong|哈哈|好的|嗯|是的|不是|谢谢|你好|测试)\s*[.!?。！？]*$", re.IGNORECASE),
        re.compile(r"^(aaa+|bbb+|xxx+|zzz+|123+|asdf+|qwer+|haha+|lol+|hmm+)\s*$", re.IGNORECASE),
        re.compile(r"^[\s\p{P}\p{S}]*$", re.UNICODE),
    ]
    
    def __init__(
        self,
        min_chunks: int = 4,
        min_turns: int = 2,
        min_content_len: int = 200,
        min_content_len_cjk: int = 80,
        max_tool_ratio: float = 0.7,
        min_unique_ratio: float = 0.4
    ):
        self.min_chunks = min_chunks
        self.min_turns = min_turns
        self.min_content_len = min_content_len
        self.min_content_len_cjk = min_content_len_cjk
        self.max_tool_ratio = max_tool_ratio
        self.min_unique_ratio = min_unique_ratio
    
    def check(self, chunks: List[TaskChunk]) -> tuple[Optional[SkipReason], Optional[str]]:
        """
        Check if task should be skipped from summarization.
        
        Returns:
            Tuple of (SkipReason, human_readable_message) or (None, None)
        """
        # 1. Too few chunks
        if len(chunks) < self.min_chunks:
            return (
                SkipReason.TOO_FEW_CHUNKS,
                f"对话内容过少（{len(chunks)} 条消息），不足以生成有效摘要。至少需要 {self.min_chunks} 条消息。"
            )
        
        user_chunks = [c for c in chunks if c.role == 'user']
        assistant_chunks = [c for c in chunks if c.role == 'assistant']
        tool_chunks = [c for c in chunks if c.role == 'tool']
        
        # 2. Not enough conversation turns
        turns = min(len(user_chunks), len(assistant_chunks))
        if turns < self.min_turns:
            return (
                SkipReason.TOO_FEW_CONVERSATION_TURNS,
                f"对话轮次不足（{turns} 轮），需要至少 {self.min_turns} 轮完整的问答交互才能生成摘要。"
            )
        
        # 3. No user messages
        if len(user_chunks) == 0:
            return (
                SkipReason.NO_USER_MESSAGES,
                "该任务没有用户消息，仅包含系统或工具自动生成的内容。"
            )
        
        # 4. Content too short
        total_content_len = sum(len(c.content) for c in chunks)
        has_cjk = bool(re.search(r'[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]', 
                                  ' '.join(c.content for c in user_chunks[:1])))
        min_len = self.min_content_len_cjk if has_cjk else self.min_content_len
        
        if total_content_len < min_len:
            return (
                SkipReason.CONTENT_TOO_SHORT,
                f"对话内容过短（{total_content_len} 字），信息量不足以生成有意义的摘要。"
            )
        
        # 5. User content is trivial
        user_content = '\n'.join(c.content for c in user_chunks)
        if self._is_trivial_content(user_content):
            return (
                SkipReason.TRIVIAL_USER_CONTENT,
                "对话内容为简单问候或测试数据（如 hello、test、ok），无需生成摘要。"
            )
        
        # 6. Both user and assistant are trivial
        all_content = user_content + '\n' + '\n'.join(c.content for c in assistant_chunks)
        if self._is_trivial_content(all_content):
            return (
                SkipReason.TRIVIAL_CONVERSATION,
                "对话内容（用户和助手）均较为简单，无需生成摘要。"
            )
        
        # 7. Dominated by tool results
        if (len(tool_chunks) > 0 and 
            len(tool_chunks) >= len(chunks) * self.max_tool_ratio and 
            len(user_chunks) <= 1):
            return (
                SkipReason.DOMINATED_BY_TOOL_RESULTS,
                f"该任务主要由工具执行结果组成（{len(tool_chunks)}/{len(chunks)} 条），缺少足够的用户交互内容。"
            )
        
        # 8. High repetition
        if len(user_chunks) >= 3:
            unique_msgs = set(c.content.strip().lower() for c in user_chunks)
            unique_ratio = len(unique_msgs) / len(user_chunks)
            if unique_ratio < self.min_unique_ratio:
                return (
                    SkipReason.HIGH_CONTENT_REPETITION,
                    f"对话中存在大量重复内容（{len(unique_msgs)} 个唯一消息 / {len(user_chunks)} 个用户消息）。"
                )
        
        return None, None
    
    def _is_trivial_content(self, text: str) -> bool:
        """Check if content is trivial/test data"""
        lines = [l.strip().lower() for l in text.split('\n') if l.strip()]
        if not lines:
            return True
        
        trivial_count = 0
        for line in lines:
            if len(line) < 5:
                trivial_count += 1
                continue
            for pattern in self.TRIVIAL_PATTERNS:
                if pattern.match(line):
                    trivial_count += 1
                    break
        
        return trivial_count / len(lines) > 0.7 if lines else True


def build_conversation_text(chunks: List[TaskChunk]) -> str:
    """
    Build conversation text from chunks.
    
    Args:
        chunks: List of TaskChunks
    
    Returns:
        Formatted conversation text
    """
    lines = []
    for c in chunks:
        if c.role == 'user':
            label = 'User'
        elif c.role == 'assistant':
            label = 'Assistant'
        elif c.role == 'tool':
            label = 'Tool'
        else:
            label = c.role.capitalize()
        
        lines.append(f"[{label}]: {c.content}")
    
    return '\n\n'.join(lines)


def parse_title_from_summary(summary: str) -> tuple[str, str]:
    """
    Parse LLM-generated title from summary.
    
    Looks for patterns like:
    - 📌 Title\n<title>
    - 📌 标题\n<title>
    
    Args:
        summary: LLM-generated summary text
    
    Returns:
        Tuple of (title, body_without_title)
    """
    patterns = [
        r'📌\s*Title\s*\n(.+)',
        r'📌\s*标题\s*\n(.+)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, summary, re.IGNORECASE)
        if match:
            title = match.group(1).strip()
            body = re.sub(pattern, '', summary, flags=re.IGNORECASE).strip()
            return title, body
    
    return '', summary


def extract_title_fallback(chunks: List[TaskChunk]) -> str:
    """
    Extract title from chunks when LLM title generation fails.
    
    Uses the first meaningful user message as title.
    """
    for c in chunks:
        if c.role != 'user':
            continue
        content = c.content.strip()
        # Skip session startup messages
        if len(content) > 200:
            continue
        if re.match(r'session\.startup|Session Startup|/new|/reset', content, re.IGNORECASE):
            continue
        return content[:80]
    
    return "Untitled Task"
