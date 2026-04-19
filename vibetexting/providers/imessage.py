from .base import BaseMessagingProvider
from ..database import load_recent_chat_history, list_recent_group_chats, search_relevant_history
from ..utils import send_imessage
from typing import List, Optional, Tuple, Dict

class IMessageProvider(BaseMessagingProvider):
    """
    macOS iMessage implementation using SQLite and AppleScript.
    """

    def load_history(self, chat_filter: str, limit: Optional[int] = None, **kwargs) -> Tuple:
        # We pass through to the existing logic in database.py
        # kwargs allows us to pass platform-specific stuff like pinned_chat_id
        return load_recent_chat_history(
            chat_filter, 
            limit, 
            auto_select=kwargs.get("auto_select", False), 
            chat_id=kwargs.get("chat_id")
        )

    def send_message(self, recipient: str, text: str, **kwargs) -> bool:
        # Uses AppleScript via utils.py
        return send_imessage(recipient, text, chat_id=kwargs.get("chat_id"))

    def get_recent_chats(self, limit: int = 10) -> List[Dict]:
        return list_recent_group_chats(limit)

    def search_memories(self, chat_id: any, query: str, limit: int = 5) -> str:
        return search_relevant_history(chat_id, query, limit)
