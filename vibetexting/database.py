import os
import sqlite3
from datetime import datetime, timedelta
from typing import List, Tuple, Optional, Dict
from .config import get_chat_db_path, normalize_chat_key
from .contacts import resolve_contacts_aliases

def fuzzy_name_match(query: str, target: str) -> float:
    """Very simple fuzzy matching score between 0 and 100."""
    if not query or not target:
        return 0.0
    q = query.lower().strip()
    t = target.lower().strip()
    if q == t:
        return 100.0
    if q in t:
        return 80.0 + (len(q) / len(t) * 15.0)
    return 0.0

def apple_timestamp_to_iso(raw_date):
    """Convert Apple's CoreData/iMessage timestamp to ISO-like string."""
    try:
        # iMessage epoch is Jan 1, 2001
        epoch = datetime(2001, 1, 1)
        if raw_date > 10**12: # nanoseconds
            dt = epoch + timedelta(seconds=raw_date / 1_000_000_000)
        else:
            dt = epoch + timedelta(seconds=raw_date)
        return dt.strftime("%Y-%m-%d %H:%M")
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
        cursor.execute(
            """
            SELECT 
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

def _build_chat_label(chat_id: int, display_name: str, chat_identifier: str, handles: set) -> str:
    if display_name:
        return display_name
    if not handles:
        return chat_identifier or f"Chat-{chat_id}"
    
    # For DMs, use the single handle
    if len(handles) == 1:
        return list(handles)[0]
    
    # For group chats without a name, show first two handles + count
    h_list = sorted(list(handles))
    if len(h_list) > 2:
        return f"{h_list[0]}, {h_list[1]} (+{len(h_list)-2} more)"
    return ", ".join(h_list)

def prompt_for_chat_suggestion(matches: List[Tuple[float, int, str]]) -> Optional[Tuple[float, int, str]]:
    print(f"\n{'\033[1;33m'}Multiple potential chats found. Which one did you mean?{'\033[0m'}")
    for idx, (score, chat_id, label) in enumerate(matches[:5], start=1):
        print(f"  {idx}. {label} ({score:.1f}% match)")
    print(f"  n. None of these / skip history")
    
    choice = input("\nPick a number: ").strip().lower()
    if choice == 'n' or not choice:
        return None
    try:
        idx = int(choice)
        if 1 <= idx <= len(matches):
            return matches[idx - 1]
    except ValueError:
        pass
    return None

def _get_chat_participants(conn: sqlite3.Connection, chat_id: int) -> List[str]:
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT COALESCE(h.id, h.uncanonicalized_id)
        FROM handle h
        JOIN chat_handle_join chj ON chj.handle_id = h.ROWID
        WHERE chj.chat_id = ?
        """,
        [chat_id]
    )
    return [r[0] for r in cursor.fetchall() if r[0]]

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
                (SELECT COUNT(*) FROM chat_handle_join WHERE chat_id = c.ROWID) as participant_count,
                (SELECT MAX(date) FROM message m 
                 JOIN chat_message_join cmj ON m.ROWID = cmj.message_id 
                 WHERE cmj.chat_id = c.ROWID) as last_msg_date
            FROM chat c
            WHERE participant_count > 1
            ORDER BY last_msg_date DESC
            LIMIT ?
            """,
            [limit]
        )
        rows = cursor.fetchall()
        
        chats = []
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

def get_latest_message_date(chat_id: int) -> Optional[int]:
    """Get the timestamp of the most recent message in a chat."""
    db_path = get_chat_db_path()
    if not os.path.exists(db_path):
        return None

    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT MAX(m.date)
            FROM message m
            JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
            WHERE cmj.chat_id = ?
              AND m.text IS NOT NULL
              AND m.text != ''
            """,
            [chat_id],
        )
        result = cursor.fetchone()
        return result[0] if result and result[0] is not None else None
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        return None
    finally:
        if conn is not None:
            conn.close()


def get_latest_message_for_chat(chat_id: int, after_date: Optional[int] = None) -> Optional[Tuple[int, int, str, Optional[str]]]:
    """Get the latest incoming (not from me) message from a chat, optionally after a given date.
    Returns (date, is_from_me, text, handle_id) or None."""
    db_path = get_chat_db_path()
    if not os.path.exists(db_path):
        return None

    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        query = """
            SELECT
                m.date,
                m.is_from_me,
                m.text,
                COALESCE(h.id, h.uncanonicalized_id)
            FROM message m
            LEFT JOIN handle h ON h.ROWID = m.handle_id
            JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
            WHERE cmj.chat_id = ?
              AND m.text IS NOT NULL
              AND m.text != ''
              AND m.text NOT LIKE '%http%%'
              AND m.text NOT LIKE '%www.%%'
              AND m.associated_message_guid IS NULL
              AND m.is_from_me = 0
        """
        params = [chat_id]
        if after_date is not None:
            query += " AND m.date > ?"
            params.append(after_date)
        query += " ORDER BY m.date DESC LIMIT 1"

        cursor.execute(query, params)
        result = cursor.fetchone()
        return result if result else None
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        return None
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
            return "", 0, resolved_label, is_group_chat, None, chat_id, chat_guid

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
