import sqlite3

connection = sqlite3.connect("money_tracker.db")
cursor = connection.cursor()

try:
    cursor.execute(
        "ALTER TABLE users ADD COLUMN is_admin INTEGER DEFAULT 0"
    )
    print("Admin column added successfully!")

except sqlite3.OperationalError:
    print("Admin column already exists.")

connection.commit()
connection.close()