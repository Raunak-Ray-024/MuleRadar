import sqlite3, secrets, hashlib, sys
 
if len(sys.argv) != 3:
    sys.exit("Use: python create_user.py <username> <analyst|admin>")
 
username, role = sys.argv[1], sys.argv[2]
assert role in ("analyst", "admin"), "role sirf analyst ya admin"
 
key = secrets.token_urlsafe(32)
con = sqlite3.connect("muleradar.db")
con.execute("CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, role TEXT, key_hash TEXT)")
con.execute("INSERT OR REPLACE INTO users VALUES (?, ?, ?)",
            (username, role, hashlib.sha256(key.encode()).hexdigest()))
con.commit(); con.close()
print(f"{username} ({role}) created.")
print("API key (one time view, save it):", key)
 






