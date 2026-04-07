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
import re
from urllib import error, request
from typing import Optional

# Configuration
OLLAMA_API_URL = "http://localhost:11434/api/generate"
APPLE_EPOCH = None
DEFAULT_CONFIG_PATH = os.path.expanduser("~/.vibetexting.json")
DEFAULT_INTENT_MODE = "uncertain"
INTENT_MODES = {"always", "uncertain", "suggest"}


def get_chat_db_path() -> str:
    return os.path.expanduser("~/Library/Messages/chat.db")


def load_user_config() -> dict:
    config_candidates = [
        os.path.join(os.getcwd(), ".vibetexting.json"),
        DEFAULT_CONFIG_PATH,
    ]

    for config_path in config_candidates:
        if not os.path.exists(config_path):
            continue
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
            if isinstance(config, dict):
                config["__path__"] = config_path
                return config
        except Exception:
            continue

    return {}


def save_user_config(config: dict, config_path: str = DEFAULT_CONFIG_PATH) -> str:
    serializable_config = {
        key: value
        for key, value in config.items()
        if key != "__path__" and value is not None
    }
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(serializable_config, f, indent=2)
        f.write("\n")
    return config_path


def prompt_setup_config() -> dict:
    print("\n--- VibeText Setup ---")
    print("This will save your default user profile for future runs. Press Enter to keep a value blank.")

    name = input("Your name [optional]: ").strip()
    vibe = input("Vibe profile path [default: my_vibe_profile.txt]: ").strip() or "my_vibe_profile.txt"
    model = input("Ollama model [default: llama3]: ").strip() or "llama3"
    intent_mode = input("Intent mode [uncertain/suggest/always, default: uncertain]: ").strip().lower() or DEFAULT_INTENT_MODE
    if intent_mode not in INTENT_MODES:
        print(f"Invalid intent mode. Using default: {DEFAULT_INTENT_MODE}")
        intent_mode = DEFAULT_INTENT_MODE
    default_recipient = input("Default recipient key [optional, e.g. mom]: ").strip()

    recipients = {}
    if default_recipient:
        chat = input(f"Chat lookup for '{default_recipient}' [default: {default_recipient}]: ").strip() or default_recipient
        history_limit_raw = input("History limit for this recipient [blank = full conversation]: ").strip()
        recipient_config = {"chat": chat}
        if history_limit_raw:
            try:
                recipient_config["history_limit"] = int(history_limit_raw)
            except ValueError:
                print("Invalid number provided. Using full conversation for this recipient.")
        recipients[default_recipient] = recipient_config

    config = {
        "name": name or None,
        "model": model,
        "intent_mode": intent_mode,
        "vibe": vibe,
        "default_recipient": default_recipient or None,
        "recipients": recipients or None,
    }
    return {key: value for key, value in config.items() if value is not None}


def merge_runtime_settings(args: argparse.Namespace, config: dict) -> argparse.Namespace:
    recipient_key = args.chat or config.get("default_recipient")
    recipient_config = {}

    recipients = config.get("recipients")
    if isinstance(recipients, dict) and recipient_key:
        recipient_config = recipients.get(recipient_key, {})
        if not recipient_config:
            normalized_recipient_key = normalize_chat_key(recipient_key)
            for key, value in recipients.items():
                if normalize_chat_key(key) == normalized_recipient_key:
                    recipient_config = value if isinstance(value, dict) else {}
                    recipient_key = key
                    break

    if not args.name and config.get("name"):
        args.name = config.get("name")
    if args.model == "llama3" and config.get("model"):
        args.model = config.get("model")
    if not args.vibe and config.get("vibe"):
        args.vibe = config.get("vibe")

    if not args.chat:
        config_chat = recipient_config.get("chat") if isinstance(recipient_config, dict) else None
        if config_chat:
            args.chat = config_chat
        elif isinstance(recipient_key, str) and recipient_key:
            args.chat = recipient_key

    if args.history_limit is None:
        recipient_history_limit = None
        if isinstance(recipient_config, dict):
            recipient_history_limit = recipient_config.get("history_limit")
        if recipient_history_limit is None and config.get("history_limit") is not None:
            recipient_history_limit = config.get("history_limit")
        if recipient_history_limit is not None:
            try:
                args.history_limit = int(recipient_history_limit)
            except Exception:
                pass

    if not getattr(args, "intent_mode", None) and config.get("intent_mode"):
        args.intent_mode = config.get("intent_mode")
    if not getattr(args, "intent_mode", None):
        args.intent_mode = DEFAULT_INTENT_MODE

    if isinstance(recipient_config, dict) and recipient_config.get("intent_mode"):
        args.intent_mode = recipient_config.get("intent_mode")

    return args


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


MANUAL_RESPONSE_PATTERNS = [
    r"\bdo you want to\b",
    r"\bwanna\b",
    r"\bwant to hang out\b",
    r"\bhang out\b",
    r"\bget together\b",
    r"\bmeet up\b",
    r"\bare you free\b",
    r"\bwhat do you want to do\b",
    r"\bshould we\b",
    r"\bwhat time works\b",
    r"\bavailable\b",
    r"\bcan you\b",
    r"\bwould you like to\b",
    r"\bopinion\b",
    r"\bdecision\b",
]


def classify_response_type(message: str) -> str:
    lowered_message = (message or "").lower()
    if any(phrase in lowered_message for phrase in ["hang out", "get together", "meet up", "do you want to", "wanna", "are you free", "should we", "what time works"]):
        return "plan"
    if any(phrase in lowered_message for phrase in ["can you", "could you", "would you", "please", "help me"]):
        return "request"
    if any(word in lowered_message for word in ["yes or no", "either", "which one", "choose", "decision"]):
        return "choice"
    return "general"


def build_intent_suggestions(original: str) -> list[str]:
    response_type = classify_response_type(original)

    if response_type == "plan":
        return [
            "Yes, that sounds good.",
            "I can’t tonight.",
            "Maybe another time.",
            "Let me check and get back to you.",
        ]
    if response_type == "request":
        return [
            "Sure, I can do that.",
            "I might be able to, but I need a minute.",
            "I can’t right now.",
            "Can you give me a little more info?",
        ]
    if response_type == "choice":
        return [
            "Pick the first one.",
            "Pick the second one.",
            "I’m not sure yet.",
            "Whichever is easiest.",
        ]

    return [
        "Yep.",
        "Nope.",
        "Maybe.",
        "I’ll think about it.",
    ]


def needs_manual_response(message: str) -> bool:
    lowered_message = (message or "").lower()
    if not lowered_message:
        return False

    for pattern in MANUAL_RESPONSE_PATTERNS:
        if re.search(pattern, lowered_message):
            return True

    return False


def prompt_for_intent(original: str) -> str:
    print("\nThis message looks like it needs your real intent before a reply is drafted.")
    print(f"Message: {original}")
    intent = input("What do you want to say? ").strip()
    return intent


def prompt_for_intent_choice(original: str) -> str:
    suggestions = build_intent_suggestions(original)
    print("\nThis message looks like it needs your intent. Choose the closest response type:")
    print(f"Message: {original}")
    for index, suggestion in enumerate(suggestions, start=1):
        print(f"  {index}. {suggestion}")
    print(f"  {len(suggestions) + 1}. Write my own")

    while True:
        choice = input(f"Select (1-{len(suggestions) + 1}): ").strip()
        if not choice:
            continue
        try:
            selected_index = int(choice)
        except ValueError:
            continue

        if 1 <= selected_index <= len(suggestions):
            return suggestions[selected_index - 1]
        if selected_index == len(suggestions) + 1:
            return prompt_for_intent(original)


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


def load_recent_chat_history(chat_filter: str, limit: Optional[int] = None) -> tuple[str, int, Optional[str]]:
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

        selected_chats = matching_chats
        chat_ids = []
        seen_chat_ids = set()
        for _, chat_id, _ in selected_chats:
            if chat_id in seen_chat_ids:
                continue
            seen_chat_ids.add(chat_id)
            chat_ids.append(chat_id)

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
              AND m.text NOT LIKE '%http%'
              AND m.text NOT LIKE '%www.%'
              AND m.associated_message_guid IS NULL
              AND c.ROWID IN ({placeholders})
            ORDER BY m.date DESC
            {'' if limit is None else 'LIMIT ?'}
        """
        query_params = [*chat_ids]
        if limit is not None:
            query_params.append(limit)
        cursor.execute(query, query_params)
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
    user_name: Optional[str] = None,
    user_intent: Optional[str] = None,
) -> str:
    """Constructs a reply prompt using the user's style and relevant chat history."""
    system_setup = "You are an AI assistant helping someone respond to a text message."
    if vibe_profile:
        system_setup = (
            "You are an AI assistant that mimics my exact texting style.\n\n"
            f"Here are examples of messages I have sent:\n{vibe_profile}\n\n"
            "Use the EXACT same vocabulary, capitalization style, phrasing, and punctuation habits as the examples above."
        )

    identity_block = ""
    if user_name:
        identity_block = (
            f"\n\nThe user's name is {user_name}."
            f" If someone asks for your name or who you are, answer with '{user_name}'."
        )

    history_block = ""
    if chat_history:
        label = f" for {chat_label}" if chat_label else ""
        history_block = f"\n\nHere is the conversation history{label}:\n{chat_history}"

    intent_block = ""
    if user_intent:
        intent_block = f"\n\nThe user wants to say this in response: {user_intent}"

    return f"""{system_setup}{identity_block}{history_block}{intent_block}

Incoming message: "{original}"

Generate a natural, human-like text response that matches my style and the conversation context.
If there is no exact example in the vibe profile, improvise a plausible answer that still sounds like the same person.
If the message is a direct question, answer the actual question first and clearly.
Answer the message the way a real person would in normal conversation, whether it is a question, statement, joke, or follow-up.
Do not respond with dismissive filler like "idk", "lol", or vague deflections unless that is clearly the style in the examples.
If no name is configured, do not invent one or refer to yourself as an assistant; just answer naturally in the same voice.
If the user provided an intent sentence, treat that as the meaning to preserve and rewrite it in the user's texting style.
Keep it concise and appropriate for a text message.
Response:"""

def main():
    parser = argparse.ArgumentParser(description="VibeText CLI - 100% Local AI Text Responder")
    parser.add_argument("--local", action="store_true", help="Compatibility flag for local mode (no-op)")
    parser.add_argument("--setup", action="store_true", help="Run interactive setup to create your default config")
    parser.add_argument("--model", default="llama3", help="Ollama model to use (default: llama3)")
    parser.add_argument("--name", help="Optional name to use for direct identity questions")
    parser.add_argument("--intent-mode", choices=sorted(INTENT_MODES), help="How to handle messages that need your real intent")
    parser.add_argument("--vibe", help="Path to your vibe profile (default: my_vibe_profile.txt if it exists)")
    parser.add_argument("--chat", help="Contact name, phone number, or email to load recent chat history")
    parser.add_argument("--history-limit", type=int, default=None, help="Max messages to include from that chat (default: full conversation)")
    args = parser.parse_args()

    if args.setup:
        config = prompt_setup_config()
        config_path = save_user_config(config)
        print(f"\n✅ Saved configuration to {config_path}")
        return 0

    config = load_user_config()
    args = merge_runtime_settings(args, config)

    print("\n--- VibeText CLI (Local Mode) ---")
    if config.get("__path__"):
        print(f"✅ Loaded user defaults from {config['__path__']}")
    
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
            if args.history_limit is None:
                print(f"✅ Loaded the full conversation with '{label}' ({message_count} messages)")
            else:
                print(f"✅ Loaded {message_count} messages from '{label}'")
        else:
            print("No matching chat history found. Continuing without chat context.")

    user_intent = None
    if args.intent_mode == "always":
        user_intent = prompt_for_intent_choice(original)
        if not user_intent:
            print("No intent entered. Continuing with an automatic suggestion instead.")
    elif args.intent_mode == "suggest":
        if needs_manual_response(original):
            user_intent = prompt_for_intent_choice(original)
            if not user_intent:
                print("No intent entered. Continuing with an automatic suggestion instead.")
    else:
        if needs_manual_response(original):
            user_intent = prompt_for_intent(original)
            if not user_intent:
                print("No intent entered. Continuing with an automatic suggestion instead.")

    # 3. Generate
    print(f"\nGenerating a reply using your sent-message style with local Ollama ({args.model})...")

    prompt = build_prompt(original, vibe_content, chat_history, resolved_chat_label or chat_filter, args.name, user_intent)
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
