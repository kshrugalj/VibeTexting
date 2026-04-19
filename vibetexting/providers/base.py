from abc import ABC, abstractmethod
from typing import List, Optional, Tuple, Dict

class BaseMessagingProvider(ABC):
    """
    The blueprint for all messaging platforms (iMessage, WhatsApp, etc.)
    Any new platform must implement these methods.
    """

    @abstractmethod
    def load_history(self, chat_filter: str, limit: Optional[int] = None, **kwargs) -> Tuple:
        """Loads message history from the platform."""
        pass

    @abstractmethod
    def send_message(self, recipient: str, text: str, **kwargs) -> bool:
        """Sends a message through the platform."""
        pass

    @abstractmethod
    def get_recent_chats(self, limit: int = 10) -> List[Dict]:
        """Lists recent active conversations."""
        pass

    @abstractmethod
    def search_memories(self, chat_id: any, query: str, limit: int = 5) -> str:
        """Searches past messages for context."""
        pass
