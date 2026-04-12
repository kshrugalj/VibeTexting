import os
import sqlite3
from datetime import datetime, timedelta
from typing import Optional, List, Tuple, Dict
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

def resolve_chat_matches(chat_filter: str, auto_select: bool = False) -> List[Tuple[float, int, str]]:
    db_path = get_chat_db_path()
    if not os.path.exists(db_path):
        return []

    if not auto_select:
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
        
        # Debug: Log total chats found
        if not auto_select:
            print(f"[DEBUG] Total chats in database: {len(rows)}")
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        return []
    finally:
        if conn is not None:
            conn.close()

    # Also scan messages for any display names that might match Omi directly
    candidate_terms = [chat_filter]
    aliases = resolve_contacts_aliases(chat_filter)
    if aliases:
        candidate_terms.extend(aliases)
    
    if not auto_select:
        print(f"[DEBUG] Searching for terms: {candidate_terms}")

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

    # Debug: Log chat types
    dm_count = 0
    group_count = 0
    for chat_id, data in chat_data.items():
        display_name = data["display_name"]
        chat_identifier = data["chat_identifier"]
        handles = data["handles"]
        
        # Determine if it's a DM or group
        is_group = len(handles) > 1
        if is_group:
            group_count += 1
        else:
            dm_count += 1
        
        label = _build_chat_label(chat_id, display_name, chat_identifier, handles)

        best_score = 0.0
        for term in candidate_terms:
            normalized_term = normalize_chat_key(term)

            # 1. Check display name
            if display_name:
                score = fuzzy_name_match(term, display_name)
                if score > best_score:
                    best_score = score
                    if not auto_select and score > 35:
                        print(f"[DEBUG] Match via display_name '{display_name}' with term '{term}': {score}")

            # 2. Check chat identifier
            if chat_identifier:
                score = fuzzy_name_match(term, chat_identifier)
                if score > best_score:
                    best_score = score
                    if not auto_select and score > 35:
                        print(f"[DEBUG] Match via chat_identifier '{chat_identifier}' with term '{term}': {score}")
                
                if normalized_term and normalized_term in normalize_chat_key(chat_identifier):
                    if 90.0 > best_score:
                        best_score = 90.0
                        if not auto_select:
                            print(f"[DEBUG] Match via normalized chat_identifier '{chat_identifier}': 90.0")

            # 3. Check handles (phone/email)
            for h in handles:
                score = fuzzy_name_match(term, h)
                if score > best_score:
                    best_score = score
                    if not auto_select and score > 35:
                        print(f"[DEBUG] Match via handle '{h}' with term '{term}': {score}")
                
                if normalize_chat_key(h) == normalized_term:
                    if 100.0 > best_score:
                        best_score = 100.0
                        if not auto_select:
                            print(f"[DEBUG] Exact match via handle '{h}': 100.0")
                elif normalized_term and normalized_term in normalize_chat_key(h):
                    if 90.0 > best_score:
                        best_score = 90.0
                        if not auto_select:
                            print(f"[DEBUG] Partial match via handle '{h}': 90.0")

            # 4. Check the label
            score = fuzzy_name_match(term, label)
            if score > best_score:
                best_score = score

        if best_score > 35:
            chat_type = "GROUP" if len(handles) > 1 else "DM"
            if not auto_select:
                print(f"[DEBUG] [{chat_type}] Chat ID {chat_id}: '{label}' - Score: {best_score}")
            matches.append((best_score, chat_id, label, last_msg_date))
    
    if not auto_select:
        print(f"[DEBUG] Summary: {dm_count} DMs, {group_count} groups scanned")

    if not matches:
        if not auto_select:
            print("❌ No matching chats found in iMessage database.")
        return []

    # Sort primarily by fuzzy score, secondarily by recency
    matches.sort(key=lambda item: (item[0], item[3]), reverse=True)

    if not auto_select:
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

def _build_chat_label(chat_id: int, display_name: Optional[str], chat_identifier: Optional[str], handles: set) -> str:
    if display_name:
        return display_name
    if chat_identifier and not chat_identifier.startswith("chat") and not chat_identifier.startswith("SMS") and not chat_identifier.startswith("iMessage"):
        return chat_identifier
    if handles:
        ordered_handles = sorted(handles)
        if len(ordered_handles) == 1:
            return ordered_handles[0]
        if len(ordered_handles) == 2:
            return f"{ordered_handles[0]} + {ordered_handles[1]}"
        return f"{ordered_handles[0]} +{len(ordered_handles) - 1} others"
    return f"Chat {chat_id}"

def _get_chat_participants(conn: sqlite3.Connection, chat_id: int) -> List[str]:
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT DISTINCT COALESCE(h.id, h.uncanonicalized_id)
        FROM chat_handle_join chj
        LEFT JOIN handle h ON h.ROWID = chj.handle_id
        WHERE chj.chat_id = ?
          AND COALESCE(h.id, h.uncanonicalized_id) IS NOT NULL
        """,
        [chat_id],
    )
    participants = []
    for (identifier,) in cursor.fetchall():
        if identifier:
            participants.append(identifier)
    return sorted(set(participants))

def list_recent_group_chats(limit: int = 10) -> List[Dict[str, object]]:
    db_path = get_chat_db_path()
    if not os.path.exists(db_path):
        return []

    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                c.ROWID,
                c.display_name,
                c.chat_identifier,
                COUNT(DISTINCT chj.handle_id) AS participant_count,
                MAX(m.date) AS last_msg_date
            FROM chat c
            LEFT JOIN chat_handle_join chj ON chj.chat_id = c.ROWID
            LEFT JOIN chat_message_join cmj ON cmj.chat_id = c.ROWID
            LEFT JOIN message m ON m.ROWID = cmj.message_id
            GROUP BY c.ROWID
            HAVING participant_count > 1
            ORDER BY last_msg_date DESC
            LIMIT ?
            """,
            [limit],
        )
        rows = cursor.fetchall()
        chats: List[Dict[str, object]] = []
        for chat_id, display_name, chat_identifier, participant_count, _ in rows:
            participants = _get_chat_participants(conn, chat_id)
            label = _build_chat_label(chat_id, display_name, chat_identifier, set(participants))
            chats.append(
                {
                    "chat_id": chat_id,
                    "label": label,
                    "participant_count": int(participant_count or 0),
                }
            )
        return chats
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        return []
    finally:
        if conn is not None:
            conn.close()

def load_recent_chat_history(chat_filter: str, limit: Optional[int] = None, auto_select: bool = False) -> tuple[str, int, Optional[str], bool, Optional[str], Optional[int], Optional[str]]:
    db_path = get_chat_db_path()
    if not os.path.exists(db_path):
        return "", 0, None, False, None, None, None

    matching_chats = resolve_chat_matches(chat_filter, auto_select=auto_select)
    if not matching_chats:
        return "", 0, None, False, None, None, None

    selected_chat = None
    if auto_select:
        # In autopilot mode, always select the best match without prompting
        selected_chat = matching_chats[0]
        print(f"[DEBUG] Auto-selected best match with score: {selected_chat[0]}")
    elif matching_chats[0][0] >= 95:
        if len(matching_chats) > 1 and matching_chats[1][0] >= 90:
            selected_chat = prompt_for_chat_suggestion(matching_chats)
        else:
            selected_chat = matching_chats[0]
    else:
        selected_chat = prompt_for_chat_suggestion(matching_chats)

    if not selected_chat:
        return "", 0, None, False, None, None, None

    best_score, chat_id, resolved_label = selected_chat
    if auto_select:
        print(f"✅ Auto-selected '{resolved_label}' (confidence: {best_score:.1f}%)")
    else:
        print(f"✅ Matched with '{resolved_label}'")

    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        participants = _get_chat_participants(conn, chat_id)
        is_group_chat = len(participants) > 1

        # Get the actual chat_identifier (GUID) for AppleScript targeting
        cursor.execute(
            """
            SELECT chat_identifier, display_name
            FROM chat
            WHERE ROWID = ?
            """,
            [chat_id]
        )
        chat_info = cursor.fetchone()
        chat_guid = chat_info[0] if chat_info else None

        query = f"""
            SELECT
                m.date,
                m.is_from_me,
                m.text,
                COALESCE(h.id, h.uncanonicalized_id),
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
            return "", 0, resolved_label, is_group_chat, None, chat_id

        lines = []
        for dt_raw, is_from_me, text, handle_id, display_name in reversed(rows):
            speaker = "Me" if is_from_me == 1 else (handle_id or display_name or "Them")
            dt_txt = apple_timestamp_to_iso(dt_raw)
            cleaned = (text or "").replace("\ufffc", "").replace("\n", " ").strip()
            if cleaned:
                lines.append(f"[{dt_txt}] {speaker}: {cleaned}")

        chat_context = None
        if is_group_chat:
            preview_participants = participants[:6]
            if len(participants) > 6:
                preview_participants.append(f"+{len(participants) - 6} more")
            participant_line = ", ".join(preview_participants) if preview_participants else "unknown"
            chat_context = (
                f"Group chat context: this thread has {len(participants)} participant handles. "
                f"Known participants: {participant_line}."
            )
        return "\n".join(lines), len(lines), resolved_label, is_group_chat, chat_context, chat_id, chat_guid
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        return "", 0, resolved_label, False, None, chat_id, None
    finally:
        if conn is not None:
            conn.close()

def search_relevant_history(chat_id: int, query_text: str, limit: int = 5) -> str:
    """Finds old messages in this chat that match keywords in the query_text."""
    db_path = get_chat_db_path()
    if not os.path.exists(db_path) or not query_text:
        return ""

    keywords = [w.strip(",.?!\"") for w in query_text.lower().split() if len(w) > 3]
    if not keywords:
        return ""

    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        conditions = " OR ".join(["m.text LIKE ?" for _ in keywords])
        params = [f"%{k}%" for k in keywords] + [chat_id, limit]
        
        query = f"""
            SELECT m.date, m.is_from_me, m.text, COALESCE(h.id, h.uncanonicalized_id)
            FROM message m
            LEFT JOIN handle h ON h.ROWID = m.handle_id
            LEFT JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
            WHERE ({conditions})
              AND m.text IS NOT NULL
              AND m.associated_message_guid IS NULL
              AND cmj.chat_id = ?
            ORDER BY m.date DESC
            LIMIT ?
        """
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        if not rows:
            return ""
            
        lines = []
        for dt_raw, is_from_me, text, handle_id in reversed(rows):
            speaker = "Me" if is_from_me == 1 else (handle_id or "Them")
            dt_txt = apple_timestamp_to_iso(dt_raw)
            cleaned = (text or "").replace("\ufffc", "").replace("\n", " ").strip()
            lines.append(f"[{dt_txt}] {speaker}: {cleaned}")
            
        return "\n".join(lines)
    except Exception:
        return ""
    finally:
        conn.close()
