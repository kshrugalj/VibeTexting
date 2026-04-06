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

def get_chat_db_path():
    return os.path.expanduser('~/Library/Messages/chat.db')

def extract_vibe(limit=100):
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

        # Query messages sent by the user (is_from_me = 1)
        # Filter out tapbacks, URLs, attachments, and extremely long/short texts
        query = """
            SELECT text
            FROM message
            WHERE is_from_me = 1
              AND text IS NOT NULL
              AND text != ''
              AND length(text) > 2
              AND length(text) < 300
              AND text NOT LIKE 'http%'
              AND text NOT LIKE 'www.%'
              AND cache_has_attachments = 0
            ORDER BY date DESC
            LIMIT 5000
        """
        cursor.execute(query)
        rows = cursor.fetchall()
        
        # Clean and sample the messages
        # Exclude Apple's auto-generated tapback messages (Loved "...", Liked "...")
        messages = [
            row[0] for row in rows 
            if not row[0].startswith(("Loved “", "Liked “", "Disliked “", "Laughed at “", "Emphasized “", "Questioned “"))
        ]
        
        if len(messages) < 10:
            print("Not enough typical messages found to build a good profile.")
            print("Found:", len(messages))
            sys.exit(1)
            
        sample_size = min(limit, len(messages))
        sampled_messages = random.sample(messages, sample_size)
        
        output_file = "my_vibe_profile.txt"
        with open(output_file, "w", encoding="utf-8") as f:
            for msg in sampled_messages:
                # Remove object replacement characters used for inline attachments
                cleaned = msg.replace('\ufffc', '').strip()
                if cleaned:
                    f.write(f"{cleaned}\n")
                    
        print(f"\n✅ Success! Extracted {sample_size} of your sent messages to '{output_file}'.")
        print("\nThese messages will be used as 'few-shot' examples to teach the local AI your exact texting style.")
        print("\nTo use your new vibe profile, run:")
        print("  python3 vibetext.py --local --vibe my_vibe_profile.txt")

    except sqlite3.OperationalError as e:
        print(f"\nDatabase Access Error: {e}")
        print("\n⚠️  macOS SECURITY BLOCK: Your terminal does not have permission to read your iMessage database.")
        print("\nHow to fix:")
        print("  1. Open System Settings > Privacy & Security > Full Disk Access")
        print("  2. Click the '+' button and add your Terminal app (or IDE/VSCode).")
        print("  3. Restart your terminal and run this script again.")
        sys.exit(1)
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    extract_vibe()
