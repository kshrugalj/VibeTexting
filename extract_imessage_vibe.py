#!/usr/bin/env python3
"""
Vibe Profile Extractor
Reads the local macOS iMessage database to extract your texting style
and saves it to a text file for the local AI to mimic.
"""

import sqlite3
import os
import random
import sys
import argparse
from datetime import datetime, timedelta


APPLE_EPOCH = datetime(2001, 1, 1)


def apple_timestamp_to_iso(raw_date):
    """Convert Apple message timestamps to a readable local datetime string."""
    if raw_date is None:
        return "unknown-time"
    try:
        val = int(raw_date)
        # iMessage stores date as seconds or nanoseconds since 2001-01-01.
        seconds = val / 1_000_000_000 if abs(val) > 10_000_000_000 else val
        return (APPLE_EPOCH + timedelta(seconds=seconds)).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return "unknown-time"

def get_chat_db_path():
    return os.path.expanduser('~/Library/Messages/chat.db')


def build_match_clause(chat_filter):
    if not chat_filter:
        return "", []
    clause = """
      AND (
            lower(ifnull(h.id, '')) LIKE lower(?)
         OR lower(ifnull(c.display_name, '')) LIKE lower(?)
      )
    """
    like_val = f"%{chat_filter}%"
    return clause, [like_val, like_val]


def extract_vibe(limit=150, chat_filter=None, history_limit=300, history_out="my_chat_history.txt", history_full=False):
    db_path = get_chat_db_path()
    if not os.path.exists(db_path):
        print(f"Error: Could not find iMessage database at {db_path}")
        print("Note: Ensure you are running this on a Mac where you use iMessage.")
        sys.exit(1)

    try:
        # Note: In newer macOS versions, terminal apps need Full Disk Access to read chat.db
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        print("Analyzing iMessage database (this is 100% local and private)...")
        match_clause, match_params = build_match_clause(chat_filter)

        # Query messages sent by the user (is_from_me = 1)
        # Filter out tapbacks, URLs, attachments, and extremely long/short texts
        query = f"""
            SELECT m.text
            FROM message m
            LEFT JOIN handle h ON h.ROWID = m.handle_id
            LEFT JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
            LEFT JOIN chat c ON c.ROWID = cmj.chat_id
            WHERE m.is_from_me = 1
              AND m.text IS NOT NULL
              AND m.text != ''
              AND length(m.text) > 2
              AND length(m.text) < 300
              AND m.text NOT LIKE '%http%'
              AND m.text NOT LIKE '%www.%'
              AND m.associated_message_guid IS NULL
              AND ifnull(m.cache_has_attachments, 0) = 0
              {match_clause}
            ORDER BY m.date DESC
            LIMIT 5000
        """
        cursor.execute(query, match_params)
        rows = cursor.fetchall()

        # Exclude Apple's auto-generated tapback messages (Loved "...", Liked "...")
        # Note: associated_message_guid IS NULL already handles modern tapbacks,
        # but we keep this for legacy or edge cases.
        messages = [
            row[0]
            for row in rows
            if not row[0].startswith(("Loved “", "Liked “", "Disliked “", "Laughed at “", "Emphasized “", "Questioned “"))
        ]

        if len(messages) < 10:
            print("Not enough typical messages found to build a good profile.")
            print("Found:", len(messages))
            if chat_filter:
                print(f"Tip: The chat filter '{chat_filter}' may be too narrow. Try a broader filter or no filter.")
            sys.exit(1)

        sample_size = min(limit, len(messages))
        sampled_messages = random.sample(messages, sample_size)

        output_file = "my_vibe_profile.txt"
        with open(output_file, "w", encoding="utf-8") as f:
            for msg in sampled_messages:
                # Remove object replacement characters used for inline attachments
                cleaned = msg.replace("\ufffc", "").strip()
                if cleaned:
                    f.write(f"{cleaned}\n")

        history_query = f"""
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
              {'' if history_full else 'AND m.is_from_me = 1'}
              {match_clause}
            ORDER BY m.date DESC
            {'' if history_full or history_limit is None else 'LIMIT ?'}
        """
        history_params = [*match_params]
        if not history_full and history_limit is not None:
            history_params.append(history_limit)
        cursor.execute(history_query, history_params)
        history_rows = cursor.fetchall()

        with open(history_out, "w", encoding="utf-8") as f:
            for dt_raw, is_from_me, text, _, _ in reversed(history_rows):
                dt_txt = apple_timestamp_to_iso(dt_raw)
                cleaned = (text or "").replace("\ufffc", "").replace("\n", " ").strip()
                if cleaned:
                    if history_full:
                        speaker = "Me" if is_from_me == 1 else "Them"
                        f.write(f"[{dt_txt}] {speaker}: {cleaned}\n")
                    else:
                        f.write(f"[{dt_txt}] Me: {cleaned}\n")

        print(f"\nSuccess! Extracted {sample_size} of your sent messages to '{output_file}'.")
        if history_full:
            print(f"Success! Exported the full chat history ({len(history_rows)} messages) to '{history_out}'.")
        else:
            print(f"Success! Exported {len(history_rows)} of your sent messages to '{history_out}'.")
        print("\nThese messages will be used as few-shot examples to teach the local AI your texting style.")
        print("\nTo use your new vibe profile, run:")
        print("  python3 vibetext.py --local --vibe my_vibe_profile.txt")
        return 0

    except (sqlite3.OperationalError, sqlite3.DatabaseError) as e:
        print(f"\nDatabase Access Error: {e}")
        print("\nmacOS security block: your process does not have permission to read your iMessage database.")
        print("\nHow to fix:")
        print("  1. Open System Settings > Privacy & Security > Full Disk Access")
        print("  2. Add your Terminal app, VS Code, and python3 interpreter.")
        print("  3. Restart VS Code/terminal and run this script again.")
        sys.exit(1)
    finally:
        if "conn" in locals():
            conn.close()


def main():
    parser = argparse.ArgumentParser(
        description="Extract your iMessage texting style and chat history for VibeTexting"
    )
    parser.add_argument("--limit", type=int, default=150, help="Max sent messages to sample for vibe profile")
    parser.add_argument("--chat", help="Optional filter by phone/email/chat display name")
    parser.add_argument("--history-limit", type=int, default=300, help="Max messages to export for chat history")
    parser.add_argument("--history-full", action="store_true", help="Export the full chat history instead of a limited slice")
    parser.add_argument("--history-out", default="my_chat_history.txt", help="Output file for chat history")
    args = parser.parse_args()

    return extract_vibe(
        limit=args.limit,
        chat_filter=args.chat,
        history_limit=args.history_limit,
        history_out=args.history_out,
        history_full=args.history_full,
    )


if __name__ == "__main__":
    sys.exit(main())
