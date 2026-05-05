import os
import sqlite3
from datetime import datetime, timedelta
from typing import List, Tuple, Optional, Dict
from .config import get_chat_db_path, normalize_chat_key
from .contacts import resolve_contacts_aliases
from .vision import describe_image
from .utils import fuzzy_name_match

# --- RAG 2.0: Semantic Memory Initialization ---
# This is intentionally lazy. Importing the embedding stack at module load time
# can spike CPU/RAM and make the whole app feel frozen.
CHROMA_DATA_PATH = os.path.join(os.path.expanduser("~"), ".vibetexting", "chroma_db")
RAG_ENABLED = True
_rag_init_attempted = False
message_collection = None
_recent_chats_cache: dict[int, tuple[float, List[Dict[str, object]]]] = {}

def _ensure_rag_ready() -> bool:
    global _rag_init_attempted, message_collection, RAG_ENABLED

    if message_collection is not None:
        return True
    if _rag_init_attempted:
        return False

    _rag_init_attempted = True
    try:
        import chromadb
        from chromadb.utils import embedding_functions

        os.makedirs(CHROMA_DATA_PATH, exist_ok=True)
        chroma_client = chromadb.PersistentClient(path=CHROMA_DATA_PATH)
        embedding_func = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )
        message_collection = chroma_client.get_or_create_collection(
            name="messages",
            embedding_function=embedding_func,
            metadata={"hnsw:space": "cosine"}
        )
        return True
    except Exception as e:
        RAG_ENABLED = False
        print(f"⚠️ Semantic Memory (RAG) disabled: {e}")
        return False

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

def resolve_chat_matches(chat_filter: str, auto_select: bool = False) -> List[Tuple[float, int, str, bool]]:
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
                h.id as handle_id,
                h.uncanonicalized_id,
                (SELECT MAX(CASE WHEN m.date > 10000000000 THEN m.date / 1000000000 ELSE m.date END) 
                 FROM message m
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

    # Also scan contacts for any identifiers that might match the recipient
    candidate_terms = {chat_filter}
    aliases = resolve_contacts_aliases(chat_filter)
    if aliases:
        candidate_terms.update(aliases)

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
        # Use handle_id if available, otherwise fallback to uncanonicalized_id
        # We only add ONE identifier per handle row to avoid artificially increasing handle count
        hid = handle_id or uncanonicalized_id
        if hid:
            chat_data[chat_id]["handles"].add(hid)

    for chat_id, data in chat_data.items():
        display_name = data["display_name"]
        chat_identifier = data["chat_identifier"]
        handles = data["handles"]

        # Determine if it's a DM or group based on unique handle identifiers
        is_group = len(handles) > 1
        label = _build_chat_label(chat_id, display_name, chat_identifier, handles)

        best_score = 0.0
        for term in candidate_terms:
            normalized_term = normalize_chat_key(term)

            # 1. Check display name
            if display_name:
                score = fuzzy_name_match(term, display_name)
                if score > best_score:
                    best_score = score

            # 2. Check chat identifier
            if chat_identifier:
                score = fuzzy_name_match(term, chat_identifier)
                if score > best_score:
                    best_score = score

                if normalized_term and normalized_term in normalize_chat_key(chat_identifier):
                    if 90.0 > best_score:
                        best_score = 90.0

            # 3. Check handles (phone/email)
            for h in handles:
                score = fuzzy_name_match(term, h)
                if score > best_score:
                    best_score = score

                if normalize_chat_key(h) == normalized_term:
                    if 100.0 > best_score:
                        best_score = 100.0
                elif normalized_term and normalized_term in normalize_chat_key(h):
                    if 90.0 > best_score:
                        best_score = 90.0

            # 4. Check the label
            score = fuzzy_name_match(term, label)
            if score > best_score:
                best_score = score

        if best_score > 35:
            # Store is_group (as an int for sorting: 0 for DM, 1 for group)
            matches.append((best_score, chat_id, label, data["last_msg_date"], is_group))

    if not matches:
        return []

    # Sort by fuzzy score, then by recency
    matches.sort(key=lambda item: (item[0], item[3]), reverse=True)

    # Return matches with (score, id, label, is_group)
    return [(m[0], m[1], m[2], m[4]) for m in matches]
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

def prompt_for_chat_suggestion(matches: List[Tuple[float, int, str, bool]]) -> Optional[Tuple[float, int, str, bool]]:
    yellow, reset = "\033[1;33m", "\033[0m"
    print(f"\n{yellow}Multiple potential chats found. Which one did you mean?{reset}")
    
    # Prioritize DMs in display but keep the sort order from resolve_chat_matches
    # DMs are shown with [DM] prefix, groups with [GROUP]
    for idx, (score, chat_id, label, is_group) in enumerate(matches[:10], start=1):
        type_label = "[GROUP]" if is_group else "[DM]   "
        print(f"  {idx}. {type_label} {label} ({score:.1f}% match)")
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

def list_recent_chats(limit: int = 10) -> List[Dict[str, object]]:
    db_path = get_chat_db_path()
    if not os.path.exists(db_path):
        return []

    now = datetime.now().timestamp()
    cached = _recent_chats_cache.get(limit)
    if cached and now - cached[0] < 3:
        return cached[1]

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
                    "participant_count": int(participant_count or len(participants) or 0),
                }
            )
        _recent_chats_cache[limit] = (now, chats)
        return chats
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        return []
    finally:
        if conn is not None:
            conn.close()

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
            SELECT MAX(CASE WHEN m.date > 10000000000 THEN m.date / 1000000000 ELSE m.date END)
            FROM message m
            JOIN chat_message_join cmj ON m.ROWID = cmj.message_id
            WHERE cmj.chat_id = ?
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
              AND (m.associated_message_type IS NULL OR m.associated_message_type = 0 OR m.associated_message_type = 1000)
              AND m.is_from_me = 0
        """
        params = [chat_id]
        if after_date is not None:
            # Note: after_date is already in the normalized (second) format from the caller
            query += " AND (CASE WHEN m.date > 10000000000 THEN m.date / 1000000000 ELSE m.date END) > ?"
            params.append(after_date)
        query += " ORDER BY (CASE WHEN m.date > 10000000000 THEN m.date / 1000000000 ELSE m.date END) DESC, m.ROWID DESC LIMIT 1"

        cursor.execute(query, params)
        result = cursor.fetchone()
        return result if result else None
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        return None
    finally:
        if conn is not None:
            conn.close()

def load_recent_chat_history(chat_filter: str, limit: Optional[int] = None, auto_select: bool = False, chat_id: Optional[int] = None) -> tuple[str, int, Optional[str], bool, Optional[str], Optional[int], Optional[str], bool]:
    db_path = get_chat_db_path()
    if not os.path.exists(db_path):
        return "", 0, None, False, None, None, None, False

    resolved_label = None
    was_group_match = False

    if chat_id is None:
        matching_chats = resolve_chat_matches(chat_filter, auto_select=auto_select)
        if not matching_chats:
            return "", 0, None, False, None, None, None, False

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
            return "", 0, None, False, None, None, None, False

        best_score, chat_id, resolved_label, was_group_match = selected_chat
        if auto_select:
            print(f"✅ Auto-selected '{resolved_label}' (confidence: {best_score:.1f}%)")
        else:
            print(f"✅ Matched with '{resolved_label}'")
    else:
        # If chat_id is provided, we still need the label for display/AppleScript
        resolved_label = chat_filter 

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
                m.attributedBody,
                COALESCE(h.id, h.uncanonicalized_id),
                c.display_name,
                m.cache_has_attachments,
                m.balloon_bundle_id,
                m.associated_message_type,
                (SELECT a.filename FROM attachment a JOIN message_attachment_join maj ON a.ROWID = maj.attachment_id WHERE maj.message_id = m.ROWID AND (a.mime_type LIKE 'image/%' OR a.uti LIKE 'public.image' OR a.filename LIKE '%.jpg' OR a.filename LIKE '%.png' OR a.filename LIKE '%.heic') LIMIT 1) as image_filename
            FROM message m
            LEFT JOIN handle h ON h.ROWID = m.handle_id
            LEFT JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
            LEFT JOIN chat c ON c.ROWID = cmj.chat_id
            WHERE (m.associated_message_type IS NULL OR m.associated_message_type = 0 OR m.associated_message_type = 1000)
              AND c.ROWID = ?
            ORDER BY (CASE WHEN m.date > 10000000000 THEN m.date / 1000000000 ELSE m.date END) DESC, m.ROWID DESC
            {'' if limit is None else 'LIMIT ?'}
        """
        query_params = [chat_id]
        if limit is not None:
            query_params.append(limit)
        cursor.execute(query, query_params)
        rows = cursor.fetchall()

        if not rows:
            return "", 0, resolved_label, is_group_chat, None, chat_id, chat_guid, False

        # Fetch total count separately for efficiency
        cursor.execute("SELECT COUNT(*) FROM chat_message_join WHERE chat_id = ?", [chat_id])
        total_count = cursor.fetchone()[0]
        
        lines = []
        for dt_raw, is_from_me, text, attr_body, handle_id, display_name, has_attachments, balloon_id, assoc_type, image_filename in reversed(rows):
            speaker = "Me" if is_from_me == 1 else (handle_id or display_name or "Them")
            dt_txt = apple_timestamp_to_iso(dt_raw)
            
            cleaned = (text or "").replace("\ufffc", "").replace("\n", " ").strip()
            
            # If it's an image, get the vision description
            if image_filename and os.path.exists(os.path.expanduser(image_filename)):
                vision_desc = describe_image(image_filename)
                if cleaned:
                    cleaned = f"{cleaned} {vision_desc}"
                else:
                    cleaned = vision_desc
            
            # Fallback: Try to extract text from attributedBody if text is empty
            if not cleaned and attr_body:
                try:
                    # Sniff for NSString inside the binary plist/stream
                    # This is a very simple way to extract the plain text string
                    # iMessage attributedBody often contains the text after the 'NSString' marker
                    body_str = str(attr_body)
                    if "NSString" in body_str:
                        # Find the actual text content between binary markers
                        # This is a heuristic that works for most standard messages
                        parts = attr_body.split(b"NSString", 1)
                        if len(parts) > 1:
                            sub = parts[1]
                            # Look for the start of the actual string (usually after some metadata)
                            # Standard format: ...NSString + length byte + string content
                            for i in range(len(sub) - 1):
                                if sub[i] == 0x01 and sub[i+1] == 0x2b: # Marker for string content
                                    start = i + 3 # Skip marker and length byte
                                    # Find end of string (non-printable or marker)
                                    end = start
                                    while end < len(sub) and (sub[end] >= 0x20 or sub[end] == 0x0a or sub[end] == 0x0d):
                                        end += 1
                                    if end > start:
                                        cleaned = sub[start:end].decode('utf-8', errors='ignore').strip()
                                        break
                except Exception:
                    pass

            # If text is STILL missing, provide a descriptive label
            if not cleaned:
                if has_attachments:
                    cleaned = "[Image/Attachment]"
                elif balloon_id:
                    if "sticker" in balloon_id.lower():
                        cleaned = "[Sticker]"
                    else:
                        cleaned = "[Rich Message]"
                elif assoc_type == 1000:
                    cleaned = "[Sticker/Reaction]"
                else:
                    cleaned = "[Message]"
            
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
        
        # Determine if the very last message was from me
        last_is_from_me = rows[0][1] == 1 if rows else False
            
        return "\n".join(lines), total_count, resolved_label, is_group_chat, chat_context, chat_id, chat_guid, last_is_from_me
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        return "", 0, resolved_label, False, None, chat_id, None, False
    finally:
        if conn is not None:
            conn.close()

def index_chat_messages(chat_id: int):
    """
    Syncs messages from iMessage SQLite to ChromaDB for a specific chat.
    We use a simple high-water mark approach based on timestamps.
    """
    if not RAG_ENABLED or not _ensure_rag_ready():
        return

    db_path = get_chat_db_path()
    if not os.path.exists(db_path):
        return

    # 1. Get the last indexed message timestamp for this chat
    last_indexed = 0
    try:
        results = message_collection.get(
            where={"chat_id": chat_id},
            limit=1,
            include=["metadatas"]
        )
        if results["metadatas"]:
            # Find the max timestamp we have for this chat
            # Note: In a full implementation, we'd store the high-water mark separately
            # For simplicity, we query the latest in this batch
            latest_rows = message_collection.get(
                where={"chat_id": chat_id},
                # We can't sort by metadata in basic Chroma, so we'd fetch more
                # or just trust the SQLite load logic below.
            )
            if latest_rows["metadatas"]:
                last_indexed = max(m["timestamp"] for m in latest_rows["metadatas"])
    except Exception:
        pass

    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        # Fetch new messages after the last indexed timestamp
        query = """
            SELECT m.ROWID, m.date, m.is_from_me, m.text, COALESCE(h.id, h.uncanonicalized_id)
            FROM message m
            LEFT JOIN handle h ON h.ROWID = m.handle_id
            LEFT JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
            WHERE cmj.chat_id = ?
              AND m.text IS NOT NULL
              AND m.text != ''
              AND (m.associated_message_type IS NULL OR m.associated_message_type = 0)
              AND (CASE WHEN m.date > 10000000000 THEN m.date / 1000000000 ELSE m.date END) > ?
            ORDER BY m.date ASC
        """
        cursor.execute(query, [chat_id, last_indexed])
        rows = cursor.fetchall()
        
        if not rows:
            return

        print(f"🧠 Indexing {len(rows)} new messages for semantic memory...")
        
        documents = []
        metadatas = []
        ids = []
        
        for row_id, dt_raw, is_from_me, text, handle_id in rows:
            speaker = "Me" if is_from_me == 1 else (handle_id or "Them")
            timestamp = dt_raw / 1000000000 if dt_raw > 10000000000 else dt_raw
            
            # Clean text
            cleaned = text.replace("\ufffc", "").strip()
            if not cleaned:
                continue
                
            documents.append(cleaned)
            metadatas.append({
                "chat_id": chat_id,
                "speaker": speaker,
                "timestamp": timestamp,
                "is_from_me": bool(is_from_me)
            })
            ids.append(f"msg_{chat_id}_{row_id}")
            
        # Batch add to ChromaDB
        if documents:
            message_collection.add(
                documents=documents,
                metadatas=metadatas,
                ids=ids
            )
            print(f"✅ Indexed {len(documents)} messages.")
            
    except Exception as e:
        print(f"❌ Error during indexing: {e}")
    finally:
        conn.close()

def search_relevant_history(chat_id: int, query_text: str, limit: int = 5) -> str:
    """
    Finds old messages in this chat using semantic similarity (RAG).
    Falls back to keyword search if RAG is disabled.
    """
    if not query_text:
        return ""

    if RAG_ENABLED and _ensure_rag_ready():
        try:
            # Trigger lazy indexing if needed (in a real app, this might be backgrounded)
            # For this MVP, we index before searching to ensure fresh data
            index_chat_messages(chat_id)

            results = message_collection.query(
                query_texts=[query_text],
                n_results=limit,
                where={"chat_id": chat_id}
            )
            
            if not results["documents"] or not results["documents"][0]:
                return ""
                
            lines = []
            # results["documents"][0] is the list of matches for the first query
            for doc, meta in zip(results["documents"][0], results["metadatas"][0]):
                dt_txt = apple_timestamp_to_iso(meta["timestamp"])
                lines.append(f"[{dt_txt}] {meta['speaker']}: {doc}")
            
            # Sort by timestamp to preserve conversation flow
            lines.sort() 
            return "\n".join(lines)
            
        except Exception as e:
            print(f"⚠️ Semantic search failed: {e}. Falling back to keywords.")
            # fall through to keyword search

    # --- Legacy Keyword Fallback ---
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
              AND (m.associated_message_type IS NULL OR m.associated_message_type = 0)
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
