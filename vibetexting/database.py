import os
import sqlite3
from datetime import datetime, timedelta
from typing import Optional, List, Tuple
from .utils import fuzzy_name_match, normalize_chat_key
from .contacts import resolve_contacts_aliases

def get_chat_db_path() -> str:
    return os.path.expanduser("~/Library/Messages/chat.db")

def apple_timestamp_to_iso(raw_date):
    if raw_date is None:
        return "unknown-time"
    try:
        apple_epoch = datetime(2001, 1, 1)
        val = int(raw_date)
        seconds = val / 1_000_000_000 if abs(val) > 10_000_000_000 else val
        return (apple_epoch + timedelta(seconds=seconds)).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return "unknown-time"

def resolve_chat_matches(chat_filter: str) -> List[Tuple[float, int, str]]:
    db_path = get_chat_db_path()
    if not os.path.exists(db_path):
        return []

    print(f"📊 Searching iMessage database...")
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        # Join with message table to get the last message date for recency scoring
        cursor.execute(
            """
            SELECT DISTINCT
                c.ROWID,
                c.display_name,
                c.chat_identifier,
                h.id as handle_id,
                h.uncanonicalized_id,
                (SELECT MAX(date) FROM message m 
                 JOIN chat_message_join cmj ON m.ROWID = cmj.message_id 
                 WHERE cmj.chat_id = c.ROWID) as last_msg_date
            FROM chat c
            LEFT JOIN chat_handle_join chj ON chj.chat_id = c.ROWID
            LEFT JOIN handle h ON h.ROWID = chj.handle_id
            """
        )
        rows = cursor.fetchall()
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        return []
    finally:
        if conn is not None:
            conn.close()

    # Also scan messages for any display names that might match Omi directly
    # Some people put a name in a group chat or individual chat but it's not in Contacts.app
    candidate_terms = [chat_filter]
    aliases = resolve_contacts_aliases(chat_filter)
    if aliases:
        candidate_terms.extend(aliases)
    
    # print(f"DEBUG: Searching for terms: {candidate_terms[:5]}...")
    
    matches = []
    
    chat_data = {}
    for chat_id, display_name, chat_identifier, handle_id, uncanonicalized_id, last_msg_date in rows:
        if chat_id is None:
            continue
        if chat_id not in chat_data:
            chat_data[chat_id] = {
                "display_name": display_name,
                "chat_identifier": chat_identifier,
                "handles": set(),
                "last_msg_date": last_msg_date or 0
            }
        if handle_id:
            chat_data[chat_id]["handles"].add(handle_id)
        if uncanonicalized_id:
            chat_data[chat_id]["handles"].add(uncanonicalized_id)

    for chat_id, data in chat_data.items():
        display_name = data["display_name"]
        chat_identifier = data["chat_identifier"]
        handles = data["handles"]
        last_msg_date = data["last_msg_date"]
        
        # Build a descriptive label
        label = display_name
        if not label:
            if chat_identifier and not chat_identifier.startswith("chat") and not chat_identifier.startswith("SMS") and not chat_identifier.startswith("iMessage"):
                label = chat_identifier
            elif handles:
                # Prefer phone number as label
                label = next((h for h in handles if "@" not in h), next(iter(handles)))
            else:
                label = f"Chat {chat_id}"

        best_score = 0.0
        for term in candidate_terms:
            normalized_term = normalize_chat_key(term)
            
            # 1. Check display name
            if display_name:
                best_score = max(best_score, fuzzy_name_match(term, display_name))
            
            # 2. Check chat identifier
            if chat_identifier:
                best_score = max(best_score, fuzzy_name_match(term, chat_identifier))
                if normalized_term and normalized_term in normalize_chat_key(chat_identifier):
                    best_score = max(best_score, 90.0)
                
            # 3. Check handles (phone/email)
            for h in handles:
                best_score = max(best_score, fuzzy_name_match(term, h))
                if normalize_chat_key(h) == normalized_term:
                    best_score = 100.0
                elif normalized_term and normalized_term in normalize_chat_key(h):
                    best_score = max(best_score, 90.0)
            
            # 4. Check the label
            best_score = max(best_score, fuzzy_name_match(term, label))

        if best_score > 35:
            # if best_score > 80:
            #     print(f"DEBUG: Match chat {chat_id} ({label}) score {best_score}")
            matches.append((best_score, chat_id, label, last_msg_date))

    if not matches:
        print("❌ No matching chats found in iMessage database.")
        return []

    # Sort primarily by fuzzy score, secondarily by recency
    matches.sort(key=lambda item: (item[0], item[3]), reverse=True)
    
    print(f"✅ Found {len(matches)} potential chat matches.")
    # Return matches in original format (score, id, label)
    return [(m[0], m[1], m[2]) for m in matches]

def prompt_for_chat_suggestion(matches: list) -> Optional[tuple]:
    print("\nI couldn't find an exact match. Did you mean one of these?")
    suggestions = matches[:5]
    for i, (_, _, label) in enumerate(suggestions, 1):
        print(f"  {i}. {label}")
    print(f"  {len(suggestions) + 1}. None of these")

    while True:
        choice = input(f"Select (1-{len(suggestions) + 1}): ").strip()
        if not choice:
            continue
        try:
            idx = int(choice)
            if 1 <= idx <= len(suggestions):
                return suggestions[idx - 1]
            if idx == len(suggestions) + 1:
                return None
        except ValueError:
            continue

def load_recent_chat_history(chat_filter: str, limit: Optional[int] = None) -> tuple[str, int, Optional[str]]:
    db_path = get_chat_db_path()
    if not os.path.exists(db_path):
        return "", 0, None

    matching_chats = resolve_chat_matches(chat_filter)
    if not matching_chats:
        return "", 0, None

    # If the top match is very strong (>= 95) and the second is significantly lower, use it directly.
    # Otherwise, if there are multiple strong options, ask the user.
    selected_chat = None
    if matching_chats[0][0] >= 95:
        if len(matching_chats) > 1 and matching_chats[1][0] >= 90:
            # Two very close matches, ask for clarification
            selected_chat = prompt_for_chat_suggestion(matching_chats)
        else:
            selected_chat = matching_chats[0]
    else:
        # No perfect match, ask user
        selected_chat = prompt_for_chat_suggestion(matching_chats)

    if not selected_chat:
        return "", 0, None

    best_score, chat_id, resolved_label = selected_chat
    print(f"✅ Matched with '{resolved_label}'")

    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
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
              AND c.ROWID = ?
            ORDER BY m.date DESC
            {'' if limit is None else 'LIMIT ?'}
        """
        query_params = [chat_id]
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
        return "", 0, resolved_label
    finally:
        if conn is not None:
            conn.close()
