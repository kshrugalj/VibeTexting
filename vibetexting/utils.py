import os
import re
import subprocess
from typing import Optional

def get_clipboard_text() -> str:
    """Gets text from the system clipboard (macOS)."""
    try:
        return subprocess.check_output(['pbpaste'], encoding='utf-8').strip()
    except Exception:
        return ""

def normalize_chat_key(value: Optional[str]) -> str:
    if not value:
        return ""
    # Strip non-alphanumeric characters and lowercase
    cleaned = "".join(character.lower() for character in value if character.isalnum())
    # If it's a phone number with a leading '1' (US), strip it for better matching
    if cleaned.isdigit() and len(cleaned) == 11 and cleaned.startswith('1'):
        return cleaned[1:]
    return cleaned

def levenshtein_distance(s1: str, s2: str) -> int:
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]

def fuzzy_name_match(search_term: str, field_value: str) -> float:
    """Returns a score between 0 and 100, where 100 is a perfect match."""
    if not search_term or not field_value:
        return 0.0
    s1 = normalize_chat_key(search_term)
    s2 = normalize_chat_key(field_value)
    if not s1 or not s2:
        return 0.0
    if s1 == s2:
        return 100.0
    if s1 in s2 or s2 in s1:
        return 85.0
    distance = levenshtein_distance(s1, s2)
    max_len = max(len(s1), len(s2))
    score = (1 - distance / max_len) * 100
    return score

def escape_applescript_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')

def send_imessage(recipient_identifier: str, message_text: str, chat_id: Optional[str] = None) -> bool:
    """Sends an iMessage using AppleScript (macOS only).
    
    Args:
        recipient_identifier: Phone number, email, or display name
        message_text: The message to send
        chat_id: Optional iMessage chat_identifier (GUID) for targeting existing chats
    """
    escaped_msg = escape_applescript_string(message_text)
    
    # If we have a chat_identifier (GUID), try to target the specific existing chat
    # This prevents creating duplicate chats for group conversations
    if chat_id is not None:
        # Try targeting by chat_identifier (GUID) which is the actual iMessage ID
        script = f'''
        tell application "Messages"
            try
                set targetChat to (1st chat whose id is "{chat_id}")
                send "{escaped_msg}" to targetChat
                return "success"
            on error
                try
                    set targetChat to (1st chat whose id contains "{chat_id}")
                    send "{escaped_msg}" to targetChat
                    return "success"
                on error
                    return "failed"
                end try
            end try
        end tell
        '''
        try:
            result = subprocess.run(['osascript', '-e', script], check=True, capture_output=True, text=True)
            if result.stdout.strip() == "success":
                return True
        except subprocess.CalledProcessError:
            pass  # Fall through to buddy-based sending if chat targeting fails
    
    # This AppleScript attempts to find a buddy by identifier (email/phone)
    # It's more robust than relying on a window being open.
    script = f'''
    tell application "Messages"
        set targetService to 1st service whose service type is iMessage
        set targetBuddy to buddy "{recipient_identifier}" of targetService
        send "{escaped_msg}" to targetBuddy
    end tell
    '''
    try:
        subprocess.run(['osascript', '-e', script], check=True, capture_output=True)
        return True
    except subprocess.CalledProcessError:
        # Fallback: simpler script that targets the 'active' chat or a generic buddy string
        # Useful if the buddy lookup above fails for complex identifiers
        fallback_script = f'''
        tell application "Messages"
            set targetBuddy to (participant 1 of (1st chat whose id contains "{recipient_identifier}"))
            send "{escaped_msg}" to targetBuddy
        end tell
        '''
        try:
            subprocess.run(['osascript', '-e', fallback_script], check=True, capture_output=True)
            return True
        except Exception:
            return False
