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
