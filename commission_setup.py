import sqlite3

connection = sqlite3.connect("money_tracker.db")
cursor = connection.cursor()

# Create commission withdrawal table
cursor.execute("""
CREATE TABLE IF NOT EXISTS commission_withdrawals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phone_number TEXT NOT NULL,
    amount REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'Pending',
    date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

# Make sure platform_settings exists
cursor.execute("""
CREATE TABLE IF NOT EXISTS platform_settings (
    id INTEGER PRIMARY KEY,
    commission_balance REAL NOT NULL DEFAULT 0
)
""")

# Make sure the platform has one settings row
cursor.execute("""
INSERT OR IGNORE INTO platform_settings
(id, commission_balance)
VALUES (1, 0)
""")

connection.commit()
connection.close()

print("Commission system database setup completed successfully.")