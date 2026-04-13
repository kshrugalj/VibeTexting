import subprocess
from .utils import fuzzy_name_match, normalize_chat_key, escape_applescript_string

def resolve_contacts_aliases(chat_filter: str) -> list[str]:
    if not chat_filter:
        return []

    print(f"🔍 Searching contacts for '{chat_filter}'...")
    
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
                set output to output & pName & "|" & pPhones & "|" & pEmails & "\n"
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

    # Collect all matches with their scores
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
        phone_blob = parts[1]
        email_blob = parts[2]
        
        # Check phones/emails for direct match too
        phones = [p.strip() for p in phone_blob.split(",") if p.strip()]
        emails = [e.strip() for e in email_blob.split(",") if e.strip()]
        all_contact_identifiers = [person_name] + phones + emails

        # Scoring
        best_match_score = fuzzy_name_match(chat_filter, person_name)
        
        # Check for better matches in phones/emails
        for ident in all_contact_identifiers:
            score = fuzzy_name_match(chat_filter, ident)
            if score > best_match_score:
                best_match_score = score
        
        if best_match_score > 70:
            contact_matches.append((best_match_score, all_contact_identifiers))

    if not contact_matches:
        return []

    # Sort by score descending
    contact_matches.sort(key=lambda x: x[0], reverse=True)
    
    top_score = contact_matches[0][0]
    
    # Filter to keep only the best matches
    # If we have 100% matches, ONLY keep those.
    # Otherwise, keep everything within a small margin of the top score (e.g., 5 points)
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
