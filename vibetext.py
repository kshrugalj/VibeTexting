#!/usr/bin/env python3
"""
VibeText CLI - 100% Local AI-powered text response generator.
Uses Ollama to ensure your messages never leave your computer.
"""

import os
import sys
import json
import sqlite3
import argparse
import subprocess
from urllib import error, request
from typing import Optional

# Configuration
OLLAMA_API_URL = "http://localhost:11434/api/generate"
APPLE_EPOCH = None


def get_chat_db_path() -> str:
    return os.path.expanduser("~/Library/Messages/chat.db")


def normalize_chat_key(value: Optional[str]) -> str:
    if not value:
        return ""
    return "".join(character.lower() for character in value if character.isalnum())


def escape_applescript_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def fuzzy_name_match(normalized_filter: str, normalized_fields: list[str]) -> bool:
    if not normalized_filter:
        return False

    for field in normalized_fields:
        if not field:
            continue
        if normalized_filter == field or normalized_filter in field:
            return True
        # Also support token-prefix matching for short inputs like "alex" -> "alexander".
        if field.startswith(normalized_filter) and len(normalized_filter) >= 2:
            return True
    return False


def resolve_contacts_aliases(chat_filter: str) -> list[str]:
    if not chat_filter:
        return []

    script = f'''
    set searchText to "{escape_applescript_string(chat_filter)}"
    tell application "Contacts"
        set matchingPeople to people
        set outputLines to {{}}
        set oldTids to AppleScript's text item delimiters
        repeat with personRef in matchingPeople
            set personName to ""
            set firstName to ""
            set lastName to ""
            set nickNameValue to ""
            set aliasValues to {{}}
            try
                set personName to name of personRef
            end try
            try
                set firstName to first name of personRef
            end try
            try
                set lastName to last name of personRef
            end try
            try
                set nickNameValue to nickname of personRef
            end try
            set isMatch to false
            ignoring case
                if personName contains searchText then set isMatch to true
                if firstName contains searchText then set isMatch to true
                if lastName contains searchText then set isMatch to true
                if nickNameValue contains searchText then set isMatch to true
            end ignoring
            if not isMatch then
                -- Skip this contact unless name fields matched first/last/full/nickname
                set end of outputLines to ""
            else
                if personName is not "" then set end of aliasValues to personName
                if firstName is not "" then set end of aliasValues to firstName
                if lastName is not "" then set end of aliasValues to lastName
                if nickNameValue is not "" then set end of aliasValues to nickNameValue
                try
                    repeat with phoneRef in phones of personRef
                        set end of aliasValues to value of phoneRef
                    end repeat
                end try
                try
                    repeat with emailRef in emails of personRef
                        set end of aliasValues to value of emailRef
                    end repeat
                end try
                if (count of aliasValues) > 0 then
                    set AppleScript's text item delimiters to tab
                    set aliasBlob to aliasValues as text
                    set AppleScript's text item delimiters to oldTids
                    set end of outputLines to personName & "|" & firstName & "|" & lastName & "|" & nickNameValue & "|" & aliasBlob
                end if
            end if
        end repeat
        set AppleScript's text item delimiters to oldTids
        return outputLines as text
    end tell
    '''

    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception:
        return []

    if result.returncode != 0:
        return []

    aliases = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("|", 4)
        if len(parts) != 5:
            continue
        person_name, first_name, last_name, nickname, raw_aliases = parts
        # AppleScript joins alias entries with tabs (set above), which avoids comma parsing issues.
        for alias in raw_aliases.split("\t"):
            cleaned = alias.strip()
            if cleaned:
                aliases.append(cleaned)

    # Keep order, remove duplicates.
    unique_aliases = []
    seen = set()
    for alias in aliases:
        key = normalize_chat_key(alias)
        if not key or key in seen:
            continue
        seen.add(key)
        unique_aliases.append(alias)
    return unique_aliases


def resolve_chat_matches(chat_filter: str):
    db_path = get_chat_db_path()
    if not os.path.exists(db_path):
        return []

    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT DISTINCT
                c.ROWID,
                c.display_name,
                h.id
            FROM message m
            LEFT JOIN handle h ON h.ROWID = m.handle_id
            LEFT JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
            LEFT JOIN chat c ON c.ROWID = cmj.chat_id
            WHERE m.text IS NOT NULL
              AND m.text != ''
            """
        )
        rows = cursor.fetchall()
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        return []
    finally:
        if conn is not None:
            conn.close()

    candidate_terms = [chat_filter, *resolve_contacts_aliases(chat_filter)]
    normalized_terms = {normalize_chat_key(term) for term in candidate_terms if term}
    matches = []

    for chat_id, display_name, handle_id in rows:
        label = display_name or handle_id or f"Chat {chat_id}"
        normalized_label = normalize_chat_key(label)
        normalized_display_name = normalize_chat_key(display_name)
        normalized_handle_id = normalize_chat_key(handle_id)

        if not normalized_terms:
            continue

        best_score = None
        for normalized_filter in normalized_terms:
            if not normalized_filter:
                continue
            if (
                normalized_filter in normalized_label
                or normalized_filter in normalized_display_name
                or normalized_filter in normalized_handle_id
            ):
                score = 0
                if normalized_filter == normalized_label:
                    score += 100
                if normalized_filter == normalized_display_name:
                    score += 90
                if normalized_filter == normalized_handle_id:
                    score += 80
                if normalized_filter in normalized_label:
                    score += 50
                if best_score is None or score > best_score:
                    best_score = score

        if best_score is not None:
            matches.append((best_score, chat_id, label))

    matches.sort(key=lambda item: (item[0], item[2]), reverse=True)
    return matches


def apple_timestamp_to_iso(raw_date):
    if raw_date is None:
        return "unknown-time"

    try:
        from datetime import datetime, timedelta

        apple_epoch = datetime(2001, 1, 1)
        val = int(raw_date)
        seconds = val / 1_000_000_000 if abs(val) > 10_000_000_000 else val
        return (apple_epoch + timedelta(seconds=seconds)).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return "unknown-time"


def load_recent_chat_history(chat_filter: str, limit: int = 20) -> tuple[str, int, Optional[str]]:
    db_path = get_chat_db_path()
    if not os.path.exists(db_path):
        return "", 0, None

    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        matching_chats = resolve_chat_matches(chat_filter)
        if not matching_chats:
            return "", 0, None

        selected_chats = matching_chats[:5]
        chat_ids = [chat_id for _, chat_id, _ in selected_chats]
        resolved_label = selected_chats[0][2]
        placeholders = ",".join("?" for _ in chat_ids)

        query = f"""
            SELECT
                m.date,
                m.is_from_me,
                m.text,
                h.id,
                c.display_name
            FROM message m
            LEFT JOIN handle h ON h.ROWID = m.handle_id
            LEFT JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
            LEFT JOIN chat c ON c.ROWID = cmj.chat_id
            WHERE m.text IS NOT NULL
              AND m.text != ''
              AND c.ROWID IN ({placeholders})
            ORDER BY m.date DESC
            LIMIT ?
        """
        cursor.execute(query, [*chat_ids, limit])
        rows = cursor.fetchall()

        if not rows:
            return "", 0, resolved_label

        lines = []
        for dt_raw, is_from_me, text, handle_id, display_name in reversed(rows):
            speaker = "Me" if is_from_me == 1 else (display_name or handle_id or "Them")
            dt_txt = apple_timestamp_to_iso(dt_raw)
            cleaned = (text or "").replace("\ufffc", "").replace("\n", " ").strip()
            if cleaned:
                lines.append(f"[{dt_txt}] {speaker}: {cleaned}")

        return "\n".join(lines), len(lines), resolved_label
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        return "", 0, None
    finally:
        if conn is not None:
            conn.close()

def get_clipboard_text() -> str:
    """Gets text from the system clipboard (macOS)."""
    try:
        return subprocess.check_output(['pbpaste'], encoding='utf-8').strip()
    except Exception:
        return ""

def call_ollama(prompt: str, model: str = "llama3") -> str:
    """Calls a local Ollama instance for truly local generation."""
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False
    }

    try:
        data = json.dumps(payload).encode("utf-8")
        req = request.Request(
            OLLAMA_API_URL,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(req, timeout=60.0) as response:
            if response.status == 200:
                body = json.loads(response.read().decode("utf-8"))
                return body["response"].strip()
            return (
                f"Error: Ollama returned {response.status}. "
                f"Make sure model '{model}' is installed (run 'ollama pull {model}')."
            )
    except error.HTTPError as e:
        return (
            f"Error: Ollama returned {e.code}. "
            f"Make sure model '{model}' is installed (run 'ollama pull {model}')."
        )
    except Exception as e:
        return f"Error connecting to Ollama: {str(e)}\nEnsure Ollama is running (https://ollama.com)."

def build_prompt(
    original: str,
    vibe_profile: Optional[str] = None,
    chat_history: Optional[str] = None,
    chat_label: Optional[str] = None,
) -> str:
    """Constructs a reply prompt using the user's style and relevant chat history."""
    system_setup = "You are an AI assistant helping someone respond to a text message."
    if vibe_profile:
        system_setup = (
            "You are an AI assistant that mimics my exact texting style.\n\n"
            f"Here are examples of messages I have sent:\n{vibe_profile}\n\n"
            "Use the EXACT same vocabulary, capitalization style, phrasing, and punctuation habits as the examples above."
        )

    history_block = ""
    if chat_history:
        label = f" for {chat_label}" if chat_label else ""
        history_block = f"\n\nHere is recent chat history{label}:\n{chat_history}"

    return f"""{system_setup}{history_block}

Incoming message: "{original}"

Generate a natural, human-like text response that matches my style and the conversation context.
Keep it concise and appropriate for a text message.
Response:"""

def main():
    parser = argparse.ArgumentParser(description="VibeText CLI - 100% Local AI Text Responder")
    parser.add_argument("--local", action="store_true", help="Compatibility flag for local mode (no-op)")
    parser.add_argument("--model", default="llama3", help="Ollama model to use (default: llama3)")
    parser.add_argument("--vibe", help="Path to your vibe profile (default: my_vibe_profile.txt if it exists)")
    parser.add_argument("--chat", help="Contact name, phone number, or email to load recent chat history")
    parser.add_argument("--history-limit", type=int, default=20, help="Max messages to include from that chat")
    args = parser.parse_args()

    print("\n--- VibeText CLI (Local Mode) ---")
    
    vibe_path = args.vibe or "my_vibe_profile.txt"
    vibe_content = None
    if os.path.exists(vibe_path):
        try:
            with open(vibe_path, "r", encoding="utf-8") as f:
                vibe_content = f.read().strip()
            print(f"✅ Loaded personal vibe profile from {vibe_path}")
        except Exception:
            pass
            
    # 1. Get Original Message
    clipboard = get_clipboard_text()
    if clipboard:
        print(f"Detected in clipboard: \"{clipboard[:50]}{'...' if len(clipboard)>50 else ''}\"")
        use_clip = input("Use clipboard text? (Y/n): ").lower() != 'n'
        original = clipboard if use_clip else input("Enter message: ")
    else:
        original = input("Enter message: ")

    if not original:
        return

    # 2. Find the relevant chat history, if available.
    chat_filter = args.chat
    if not chat_filter:
        chat_filter = input("\nWho are you texting? (name, number, or Enter to skip history): ").strip() or None

    chat_history = None
    resolved_chat_label = None
    if chat_filter:
        print(f"Searching recent chat history for '{chat_filter}'...")
        chat_history, message_count, resolved_chat_label = load_recent_chat_history(chat_filter, args.history_limit)
        if chat_history:
            label = resolved_chat_label or chat_filter
            print(f"✅ Loaded {message_count} recent messages from '{label}'")
        else:
            print("No matching chat history found. Continuing without chat context.")

    # 3. Generate
    print(f"\nGenerating a reply using your sent-message style with local Ollama ({args.model})...")

    prompt = build_prompt(original, vibe_content, chat_history, resolved_chat_label or chat_filter)
    reply = call_ollama(prompt, args.model)

    # 4. Output
    print("\n" + "="*40)
    print(f"SUGGESTED REPLY:")
    print("-" * 40)
    print(reply)
    print("="*40)
    
    if "Error" not in reply:
        try:
            subprocess.run(['pbcopy'], input=reply, encoding='utf-8')
            print("\n(Copied to clipboard! 📋)")
        except Exception:
            pass
    print()

if __name__ == "__main__":
    main()
