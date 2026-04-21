import sqlite3
import os
import glob

# Find all AddressBook SQLite databases (including iCloud and other Sources)
search_path = os.path.expanduser("~/Library/Application Support/AddressBook/**/AddressBook-v22.abcddb")
db_paths = glob.glob(search_path, recursive=True)

for db_path in db_paths:
    print(f"\n--- Checking DB: {db_path} ---")
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
        LIMIT 3
        """
        results = cursor.execute(query).fetchall()
        for row in results:
            print(row)
    except Exception as e:
        print(f"Error reading {db_path}: {e}")
    finally:
        conn.close()
