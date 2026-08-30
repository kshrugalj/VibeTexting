"""
wrapped.py — Global Wrapped (about you)
Computes annual / range / all-time stats from chat.db, 100% local.
No ChromaDB, no network.
"""

from __future__ import annotations

import os
import re
import json
import sqlite3
from datetime import datetime, timedelta
from collections import defaultdict, Counter
from typing import Optional, Dict, List, Tuple

from .config import get_chat_db_path

CACHE_DIR = os.path.join(os.path.expanduser("~"), ".vibetexting", "wrapped_cache")
os.makedirs(CACHE_DIR, exist_ok=True)

APPLE_EPOCH = datetime(2001, 1, 1)

# ---------------------------------------------------------------------------
# Helpers: Apple timestamp <-> datetime
# ---------------------------------------------------------------------------

def _apple_ts_for_year(year: int) -> float:
    """Seconds from Apple epoch (2001-01-01) to Jan 1 of year."""
    target = datetime(year, 1, 1)
    return (target - APPLE_EPOCH).total_seconds()

def _raw_to_dt(raw: int) -> datetime:
    secs = raw / 1_000_000_000 if raw > 10**12 else float(raw)
    return APPLE_EPOCH + timedelta(seconds=secs)

def _build_date_filter(year_from: Optional[int], year_to: Optional[int]) -> Tuple[str, List]:
    """
    Returns (where_clause_fragment, params) to filter m.date.
    Caller must prepend with AND or WHERE.
    where_fragment uses converted apple seconds for comparison.
    If both None -> "" (no filter, all time).
    """
    if year_from is None and year_to is None:
        return "", []
    clauses = []
    params: List[float] = []
    if year_from is not None:
        start = _apple_ts_for_year(year_from)
        clauses.append("(CASE WHEN m.date > 10000000000 THEN m.date / 1000000000 ELSE m.date END) >= ?")
        params.append(start)
    if year_to is not None:
        # exclusive upper bound: Jan 1 of year_to+1
        end = _apple_ts_for_year(year_to + 1)
        clauses.append("(CASE WHEN m.date > 10000000000 THEN m.date / 1000000000 ELSE m.date END) < ?")
        params.append(end)
    if not clauses:
        return "", []
    return " AND " + " AND ".join(clauses), params

def _cache_path(year_from: Optional[int], year_to: Optional[int]) -> str:
    if year_from is None and year_to is None:
        key = "all"
    elif year_from == year_to:
        key = str(year_from)
    else:
        a = str(year_from) if year_from is not None else "start"
        b = str(year_to) if year_to is not None else "now"
        key = f"{a}-{b}"
    return os.path.join(CACHE_DIR, f"global_{key}.json")

def _get_latest_raw_date() -> Optional[float]:
    db_path = get_chat_db_path()
    if not os.path.exists(db_path):
        return None
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT MAX(m.date) FROM message m")
        row = cur.fetchone()
        return row[0] if row and row[0] is not None else None
    except Exception:
        return None
    finally:
        if conn:
            conn.close()

def _is_cache_valid(cache_path: str) -> bool:
    if not os.path.exists(cache_path):
        return False
    try:
        latest = _get_latest_raw_date()
        if latest is None:
            return True
        # Compare cache mtime vs latest message timestamp? Use file mtime vs now?
        # Simple: if cache exists and latest raw is older than cache mtime (converted), valid.
        # We store latest_raw in cache JSON for exact check.
        with open(cache_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        cached_latest = data.get("_cached_latest_raw")
        # If latest in DB equals cached, still valid; if DB newer, invalid
        if cached_latest is not None and latest == cached_latest:
            return True
        if cached_latest is not None and latest != cached_latest:
            return False
        # Fallback: check mtime within 60s
        return False
    except Exception:
        return False

def _load_cache(year_from: Optional[int], year_to: Optional[int]) -> Optional[Dict]:
    p = _cache_path(year_from, year_to)
    if not _is_cache_valid(p):
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        # strip internal key
        data.pop("_cached_latest_raw", None)
        return data
    except Exception:
        return None

def _save_cache(year_from: Optional[int], year_to: Optional[int], payload: Dict) -> None:
    p = _cache_path(year_from, year_to)
    try:
        latest = _get_latest_raw_date()
        to_save = dict(payload)
        to_save["_cached_latest_raw"] = latest
        with open(p, "w", encoding="utf-8") as f:
            json.dump(to_save, f, indent=2)
    except Exception:
        pass

# ---------------------------------------------------------------------------
# Label resolution for circle top chats
# ---------------------------------------------------------------------------

def _build_label_for_chat(chat_id: int, display_name: Optional[str], chat_identifier: Optional[str], handles: List[str]) -> str:
    if display_name:
        return display_name
    if not handles:
        return chat_identifier or f"Chat-{chat_id}"
    if len(handles) == 1:
        return handles[0]
    h_list = sorted(handles)
    if len(h_list) > 2:
        return f"{h_list[0]}, {h_list[1]} (+{len(h_list)-2} more)"
    return ", ".join(h_list)

def _fetch_chat_labels(chat_ids: List[int]) -> Dict[int, str]:
    if not chat_ids:
        return {}
    db_path = get_chat_db_path()
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        labels: Dict[int, str] = {}
        for cid in chat_ids:
            cur.execute("SELECT display_name, chat_identifier FROM chat WHERE ROWID = ?", [cid])
            row = cur.fetchone()
            display_name, chat_identifier = (row[0], row[1]) if row else (None, None)
            cur.execute(
                "SELECT COALESCE(h.id, h.uncanonicalized_id) FROM handle h JOIN chat_handle_join chj ON chj.handle_id = h.ROWID WHERE chj.chat_id = ?",
                [cid],
            )
            handles = [r[0] for r in cur.fetchall() if r[0]]
            labels[cid] = _build_label_for_chat(cid, display_name, chat_identifier, handles)
        return labels
    except Exception:
        return {cid: f"Chat-{cid}" for cid in chat_ids}
    finally:
        if conn:
            conn.close()

# ---------------------------------------------------------------------------
# Core: compute global wrapped
# ---------------------------------------------------------------------------

_EMOJI_RE = re.compile(
    "["
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F300-\U0001F5FF"  # symbols & pictographs
    "\U0001F680-\U0001F6FF"  # transport
    "\U0001F1E0-\U0001F1FF"  # flags
    "\U00002700-\U000027BF"
    "\U000024C2-\U0001F251"
    "\U0001F900-\U0001F9FF"
    "\u2600-\u26FF"
    "\u2700-\u27BF"
    "]+",
    flags=re.UNICODE,
)

def _tokenize_low(text: str) -> List[str]:
    return re.findall(r"\b[a-z']+\b", text.lower())

def get_global_wrapped(
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    use_cache: bool = False,
) -> Dict:
    """
    Compute global Wrapped for year range [year_from, year_to] inclusive.
    If both None -> all time.
    If year_from == year_to -> single year.
    Returns dict with 7 cards + meta.
    """
    # Try cache
    if use_cache:
        cached = _load_cache(year_from, year_to)
        if cached is not None:
            return cached

    db_path = get_chat_db_path()
    if not os.path.exists(db_path):
        return {
            "error": f"chat.db not found at {db_path}",
            "year_from": year_from,
            "year_to": year_to,
            "range_label": _range_label(year_from, year_to),
        }

    date_filter, params = _build_date_filter(year_from, year_to)

    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        # Single fetch: all messages in range with chat_id
        query = f"""
            SELECT m.date, m.is_from_me, m.text, cmj.chat_id
            FROM message m
            JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
            WHERE (m.associated_message_type IS NULL OR m.associated_message_type = 0 OR m.associated_message_type = 1000)
              {date_filter}
        """
        cur.execute(query, params)
        rows = cur.fetchall()
    except (sqlite3.OperationalError, sqlite3.DatabaseError) as e:
        msg = str(e)
        if "unable to open database file" in msg.lower():
            msg = (
                f"Unable to open chat.db at {db_path}. "
                "Grant Full Disk Access to Terminal (System Settings → Privacy & Security → Full Disk Access) "
                "and retry. Or run with a copied DB for testing."
            )
        return {"error": msg, "year_from": year_from, "year_to": year_to, "range_label": _range_label(year_from, year_to)}
    finally:
        if conn:
            conn.close()

    # If no rows and we filtered by year, still return structure with zeros
    # Compute metrics in Python
    sent_rows = [r for r in rows if r[1] == 1]
    volume = len(sent_rows)

    # For circle: distinct chats where YOU sent (global about you)
    chat_ids_sent = set(r[3] for r in sent_rows if r[3] is not None)
    circle_total = len(chat_ids_sent)

    # Top 3 chats by total messages (both sides) within range
    cnt_by_chat = Counter(r[3] for r in rows if r[3] is not None)
    top_chat_ids = [cid for cid, _ in cnt_by_chat.most_common(3)]
    top_labels_map = _fetch_chat_labels(top_chat_ids)
    top_chats = [
        {"chat_id": cid, "label": top_labels_map.get(cid, f"Chat-{cid}"), "count": cnt_by_chat[cid]}
        for cid in top_chat_ids
    ]

    # Prime time: histogram of sent hours
    hour_counts = Counter()
    weekday_counts = Counter()
    for raw, is_me, text, chat_id in sent_rows:
        try:
            dt = _raw_to_dt(raw)
            hour_counts[dt.hour] += 1
            weekday_counts[dt.weekday()] += 1
        except Exception:
            continue
    prime_hour = hour_counts.most_common(1)[0] if hour_counts else (None, 0)
    prime_weekday = weekday_counts.most_common(1)[0] if weekday_counts else (None, 0)
    weekday_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    prime_hour_val, prime_hour_cnt = prime_hour
    prime_wday_val, prime_wday_cnt = prime_weekday
    # format hour like 11pm
    def _fmt_hour(h):
        if h is None:
            return None
        suffix = "am" if h < 12 else "pm"
        hr12 = h % 12
        if hr12 == 0:
            hr12 = 12
        return f"{hr12}{suffix}"
    prime_time = {
        "peak_hour": prime_hour_val,
        "peak_hour_label": _fmt_hour(prime_hour_val) if prime_hour_val is not None else None,
        "peak_hour_count": prime_hour_cnt,
        "peak_weekday": weekday_names[prime_wday_val] if prime_wday_val is not None else None,
        "peak_weekday_count": prime_wday_cnt,
        "hour_histogram": dict(hour_counts),
        "weekday_histogram": {weekday_names[k]: v for k, v in weekday_counts.items()},
    }

    # Signature: avg words, emoji, lowercase
    sent_texts = [(r[2] or "") for r in sent_rows]
    # avg words
    word_counts = []
    total_words = 0
    for t in sent_texts:
        # replace U+FFFC etc
        cleaned = t.replace("\ufffc", "").strip()
        if not cleaned:
            continue
        wc = len(cleaned.split())
        word_counts.append(wc)
        total_words += wc
    avg_words = round(sum(word_counts) / len(word_counts), 1) if word_counts else 0.0
    # emoji
    emoji_counter = Counter()
    for t in sent_texts:
        for em in _EMOJI_RE.findall(t):
            # _EMOJI_RE finds sequences; count each char? For v1, count each match as one, then split into individual emojis
            # Better to count each codepoint that is emoji: split match into chars
            for ch in em:
                emoji_counter[ch] += 1
            # if match contained multiple emojis as sequence, also count the sequence? Keep per-char.
    top_emojis = emoji_counter.most_common(5)
    total_emojis = sum(emoji_counter.values())
    emoji_per_msg = round(total_emojis / len(sent_rows), 2) if sent_rows else 0.0
    # lowercase
    nonempty_texts = [t for t in sent_texts if t.strip()]
    lower_cnt = sum(1 for t in nonempty_texts if t.strip() == t.strip().lower() and t.strip() != t.strip().upper() and t.strip())
    # Actually check if entire text is lower: text == text.lower() and has letters
    lower_cnt2 = 0
    for t in nonempty_texts:
        stripped = t.strip()
        # has at least one alpha lower
        has_alpha = any(c.isalpha() for c in stripped)
        if has_alpha and stripped == stripped.lower():
            lower_cnt2 += 1
    lowercase_pct = round((lower_cnt2 / len(nonempty_texts) * 100), 1) if nonempty_texts else 0.0

    # Determine 24h late-night? Track late night 0-4
    late_night = sum(1 for raw, is_me, text, cid in sent_rows if _raw_to_dt(raw).hour in (0, 1, 2, 3, 4)) if sent_rows else 0

    signature = {
        "avg_words": avg_words,
        "median_words": _median(word_counts) if word_counts else 0,
        "total_words": total_words,
        "top_emojis": [{"emoji": e, "count": c} for e, c in top_emojis],
        "total_emojis": total_emojis,
        "emoji_per_msg": emoji_per_msg,
        "lowercase_pct": lowercase_pct,
        "late_night_count": late_night,
        "message_count": len(sent_rows),
    }

    # Streaks & Loyal One: two-way days per chat
    # Build per_chat -> day -> [you, them]
    per_chat_day: Dict[int, Dict[str, List[int]]] = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    for raw, is_me, text, chat_id in rows:
        if chat_id is None:
            continue
        try:
            dt = _raw_to_dt(raw)
            day = dt.strftime("%Y-%m-%d")
            bucket = per_chat_day[chat_id][day]
            if is_me == 1:
                bucket[0] += 1
            else:
                bucket[1] += 1
        except Exception:
            continue

    # Compute two-way days per chat
    two_way_per_chat: Dict[int, List[str]] = {}
    two_way_count_per_chat: Dict[int, int] = {}
    for cid, day_map in per_chat_day.items():
        two_days = [day for day, (you, them) in day_map.items() if you > 0 and them > 0]
        two_days_sorted = sorted(two_days)
        two_way_per_chat[cid] = two_days_sorted
        two_way_count_per_chat[cid] = len(two_days_sorted)

    # Streaks: longest consecutive two-way streak across all chats
    longest_streak = 0
    longest_streak_chat: Optional[int] = None
    longest_streak_bounds: Optional[Tuple[str, str]] = None
    current_streak = 0
    current_streak_chat: Optional[int] = None
    # Also compute current streak ending today per chat
    today_str = datetime.now().strftime("%Y-%m-%d")
    best_current = 0
    best_current_cid = None
    best_current_bounds = None

    for cid, days_sorted in two_way_per_chat.items():
        if not days_sorted:
            continue
        # longest
        cur_len = 1
        best_len = 1
        cur_start = days_sorted[0]
        best_start = days_sorted[0]
        best_end = days_sorted[0]
        for i in range(1, len(days_sorted)):
            prev = datetime.strptime(days_sorted[i - 1], "%Y-%m-%d")
            curr = datetime.strptime(days_sorted[i], "%Y-%m-%d")
            if (curr - prev).days == 1:
                cur_len += 1
            else:
                if cur_len > best_len:
                    best_len = cur_len
                    best_start = days_sorted[i - cur_len]
                    best_end = days_sorted[i - 1]
                cur_len = 1
                cur_start = days_sorted[i]
        # tail check
        if cur_len > best_len:
            best_len = cur_len
            # need to find start of tail
            best_start = days_sorted[len(days_sorted) - cur_len]
            best_end = days_sorted[-1]

        if best_len > longest_streak:
            longest_streak = best_len
            longest_streak_chat = cid
            longest_streak_bounds = (best_start, best_end)

        # current streak ending today: walk backwards from today
        # if today is two-way day, count backwards
        date_set = set(days_sorted)
        if today_str in date_set:
            c = 0
            d = datetime.strptime(today_str, "%Y-%m-%d")
            while d.strftime("%Y-%m-%d") in date_set:
                c += 1
                d -= timedelta(days=1)
            if c > best_current:
                best_current = c
                best_current_cid = cid
                # bounds
                start_d = datetime.strptime(today_str, "%Y-%m-%d") - timedelta(days=c - 1)
                best_current_bounds = (start_d.strftime("%Y-%m-%d"), today_str)

    # If no current streak ending today, best_current stays 0
    streaks = {
        "longest": longest_streak,
        "longest_chat_id": longest_streak_chat,
        "longest_chat_label": _fetch_chat_labels([longest_streak_chat]).get(longest_streak_chat) if longest_streak_chat is not None else None,
        "longest_start": longest_streak_bounds[0] if longest_streak_bounds else None,
        "longest_end": longest_streak_bounds[1] if longest_streak_bounds else None,
        "current": best_current,
        "current_chat_id": best_current_cid,
        "current_chat_label": _fetch_chat_labels([best_current_cid]).get(best_current_cid) if best_current_cid is not None else None,
        "current_start": best_current_bounds[0] if best_current_bounds else None,
        "current_end": best_current_bounds[1] if best_current_bounds else None,
    }

    # Loyal One: chat with most two-way days
    loyal_chat = max(two_way_count_per_chat, key=lambda k: two_way_count_per_chat[k]) if two_way_count_per_chat else None
    loyal_days = two_way_count_per_chat.get(loyal_chat, 0) if loyal_chat is not None else 0
    # runner up
    sorted_loyal = sorted(two_way_count_per_chat.items(), key=lambda x: x[1], reverse=True)
    runner = sorted_loyal[1] if len(sorted_loyal) > 1 else None
    loyal_labels = _fetch_chat_labels([c for c, _ in sorted_loyal[:3]])
    loyal_one = {
        "chat_id": loyal_chat,
        "label": loyal_labels.get(loyal_chat) if loyal_chat is not None else None,
        "two_way_days": loyal_days,
        "runner_up": {"label": loyal_labels.get(runner[0]), "days": runner[1]} if runner else None,
        "top3": [{"label": loyal_labels.get(cid, f"Chat-{cid}"), "days": cnt, "chat_id": cid} for cid, cnt in sorted_loyal[:3]],
    }

    # Day One Flex: earliest sent in filtered range
    earliest_raw = None
    earliest_text = None
    earliest_dt_str = None
    if sent_rows:
        # sent_rows currently filtered; find min raw
        # Need also text for that row; iterate to find min
        min_row = min(sent_rows, key=lambda r: r[0])
        earliest_raw = min_row[0]
        earliest_text = (min_row[2] or "").replace("\ufffc", "").strip() or "[no text]"
        if len(earliest_text) > 80:
            earliest_text = earliest_text[:80] + "..."
        try:
            edt = _raw_to_dt(earliest_raw)
            earliest_dt_str = edt.strftime("%Y-%m-%d %H:%M")
            days_since = (datetime.now() - edt).days
        except Exception:
            earliest_dt_str = None
            days_since = None
    else:
        earliest_dt_str = None
        days_since = None

    # For all-time, also compute first ever overall regardless of filter? But filtered earliest is already correct for range.
    # Provide both.
    day_one = {
        "first_message_date": earliest_dt_str,
        "first_message_text": earliest_text,
        "days_since": days_since,
        "raw": earliest_raw,
    }

    payload = {
        "range_label": _range_label(year_from, year_to),
        "year_from": year_from,
        "year_to": year_to,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "volume": {"sent": volume, "total_in_range": len(rows)},
        "circle": {"distinct_chats_you_texted": circle_total, "top_chats": top_chats, "total_messages_in_range": len(rows)},
        "prime_time": prime_time,
        "signature": signature,
        "streaks": streaks,
        "loyal_one": loyal_one,
        "day_one": day_one,
    }

    # Save cache
    if use_cache:
        _save_cache(year_from, year_to, payload)
    return payload

def _median(lst: List[int]) -> float:
    if not lst:
        return 0
    s = sorted(lst)
    n = len(s)
    if n % 2 == 1:
        return float(s[n // 2])
    return (s[n // 2 - 1] + s[n // 2]) / 2

def _range_label(year_from: Optional[int], year_to: Optional[int]) -> str:
    if year_from is None and year_to is None:
        return "All Time"
    if year_from is not None and year_to is not None and year_from == year_to:
        return str(year_from)
    if year_from is not None and year_to is not None:
        return f"{year_from}–{year_to}"
    if year_from is not None:
        return f"{year_from}–now"
    if year_to is not None:
        return f"through {year_to}"
    return "Custom"
