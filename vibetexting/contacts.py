import os
import glob
import sqlite3
import subprocess
from .utils import fuzzy_name_match, normalize_chat_key

def _get_contacts_via_sqlite(chat_filter: str) -> list:
    """Fast, native extraction of macOS Contacts via SQLite."""
    search_path = os.path.expanduser("~/Library/Application Support/AddressBook/**/AddressBook-v22.abcddb")
    db_paths = glob.glob(search_path, recursive=True)
    
    if not db_paths:
        return []

    contact_matches = []
    
    for db_path in db_paths:
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            query = """
            SELECT 
                r.ZFIRSTNAME,
                r.ZLASTNAME,
                r.ZORGANIZATION,
                (SELECT GROUP_CONCAT(ZFULLNUMBER, ',') FROM ZABCDPHONENUMBER WHERE ZOWNER = r.Z_PK),
                (SELECT GROUP_CONCAT(ZADDRESS, ',') FROM ZABCDEMAILADDRESS WHERE ZOWNER = r.Z_PK)
            FROM ZABCDRECORD r
            WHERE r.ZFIRSTNAME IS NOT NULL OR r.ZLASTNAME IS NOT NULL OR r.ZORGANIZATION IS NOT NULL
            """
            results = cursor.execute(query).fetchall()
            
            for row in results:
                first = row[0] or ""
                last = row[1] or ""
                org = row[2] or ""
                phones_str = row[3] or ""
                emails_str = row[4] or ""
                
                parts = [p for p in [first, last, org] if p]
                person_name = " ".join(parts).strip()
                
                phones = [p.strip() for p in phones_str.split(",") if p.strip()]
                emails = [e.strip() for e in emails_str.split(",") if e.strip()]
                
                all_contact_identifiers = [person_name] + phones + emails
                if not all_contact_identifiers:
                    continue

                best_match_score = fuzzy_name_match(chat_filter, person_name)
                for ident in all_contact_identifiers:
                    score = fuzzy_name_match(chat_filter, ident)
                    if score > best_match_score:
                        best_match_score = score
                
                if best_match_score > 70:
                    contact_matches.append((best_match_score, all_contact_identifiers))
                    
        except Exception:
            pass
        finally:
            try:
                conn.close()
            except Exception:
                pass
                
    return contact_matches


def _get_contacts_via_applescript(chat_filter: str) -> list:
    """Slow, fallback extraction of macOS Contacts via AppleScript."""
    script = '''
    tell application "Contacts"
        if not running then 
            launch
            delay 1
        end if
        set output to ""
        set people_list to people
        repeat with p in people_list
            set pName to name of p
            if pName is missing value then set pName to ""
            
            set pPhones to ""
            try
                repeat with ph in phones of p
                    set pPhones to pPhones & (value of ph) & ","
                end repeat
            end try
            
            set pEmails to ""
            try
                repeat with em in emails of p
                    set pEmails to pEmails & (value of em) & ","
                end repeat
            end try
            
            if pName is not "" or pPhones is not "" or pEmails is not "" then
                set output to output & pName & "|" & pPhones & "|" & pEmails & "\\n"
            end if
        end repeat
        return output
    end tell
    '''

    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception as e:
        print(f"⚠️ Error running AppleScript: {e}")
        return []

    if result.returncode != 0:
        if "not authorized" in result.stderr.lower() or "permissions" in result.stderr.lower():
            print("❌ Permission denied to access Contacts. Please check System Settings > Privacy & Security > Automation.")
        else:
            print(f"⚠️ AppleScript failed with code {result.returncode}: {result.stderr}")
        return []

    contact_matches = []
    lines = result.stdout.strip().split("\n")
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        parts = line.split("|")
        if len(parts) < 3:
            continue
        
        person_name = parts[0]
        phones = [p.strip() for p in parts[1].split(",") if p.strip()]
        emails = [e.strip() for e in parts[2].split(",") if e.strip()]
        
        all_contact_identifiers = [person_name] + phones + emails

        best_match_score = fuzzy_name_match(chat_filter, person_name)
        for ident in all_contact_identifiers:
            score = fuzzy_name_match(chat_filter, ident)
            if score > best_match_score:
                best_match_score = score
        
        if best_match_score > 70:
            contact_matches.append((best_match_score, all_contact_identifiers))

    return contact_matches


def resolve_contacts_aliases(chat_filter: str) -> list[str]:
    if not chat_filter:
        return []

    print(f"🔍 Searching contacts for '{chat_filter}'...")
    
    # 1. Fast Native SQLite extraction
    contact_matches = _get_contacts_via_sqlite(chat_filter)
    
    # 2. Slow Fallback if SQLite fails/empty
    if not contact_matches:
        contact_matches = _get_contacts_via_applescript(chat_filter)

    if not contact_matches:
        return []

    # Sort by score descending
    contact_matches.sort(key=lambda x: x[0], reverse=True)
    
    top_score = contact_matches[0][0]
    
    filtered_identifiers = []
    match_count = 0
    
    for score, identifiers in contact_matches:
        if top_score == 100:
            if score < 100:
                break
        elif score < (top_score - 5):
            break
            
        match_count += 1
        for ident in identifiers:
            if ident:
                filtered_identifiers.append(ident)

    unique_aliases = []
    seen = set()
    for alias in filtered_identifiers:
        key = normalize_chat_key(alias)
        if not key or key in seen:
            continue
        seen.add(key)
        unique_aliases.append(alias)
    
    if unique_aliases:
        print(f"✅ Found {len(unique_aliases)} potential identifiers for {match_count} matching contact(s).")
        
    return unique_aliases
