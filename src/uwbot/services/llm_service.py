from abc import ABC, abstractmethod
from typing import Dict, List
from uwbot.utils.result import Result

class LLMService(ABC):
    @abstractmethod
    async def analyze_messages(self, messages: List[str]) -> Result[Dict]:
        """
        Analyze a batch of chat messages (or questions).
        Returns a Result containing the LLM's output or error.
        """
        pass

    @abstractmethod
    async def test_connection(self) -> bool:
        pass 