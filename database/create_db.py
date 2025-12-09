import sqlite3
from pathlib import Path

# Get paths relative to this file
BASE_DIR = Path(__file__).resolve().parent
db_path = BASE_DIR / "nps.db"
schema_path = BASE_DIR / "schema.sql"

print("DB path:    ", db_path)
print("Schema path:", schema_path)

# (Re)create the database file and apply schema
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

with open(schema_path, "r", encoding="utf-8") as f:
    schema_sql = f.read()
    cursor.executescript(schema_sql)

conn.commit()
conn.close()

print("nps.db created and schema applied successfully!")
