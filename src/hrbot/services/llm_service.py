from abc import ABC, abstractmethod
from typing import Dict, List, AsyncGenerator
from hrbot.utils.result import Result

class LLMService(ABC):
    @abstractmethod
    async def analyze_messages(self, messages: List[str]) -> Result[Dict]:
        """
        Analyze a batch of chat messages (or questions).
        Returns a Result containing the LLM's output or error.
        """
        pass

    @abstractmethod
    async def analyze_messages_streaming(self, messages: List[str]) -> AsyncGenerator[str, None]:
        """
        Analyze a batch of chat messages with streaming output.
        Yields chunks of the response as they are generated.
        """
        yield "Streaming not implemented"

    @abstractmethod
    async def test_connection(self) -> bool:
        pass 