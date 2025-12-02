import sqlite3

DB_NAME = "database.db"  # Must match the file name!

def get_db():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cursor = conn.cursor()

    


    # ------------------------------------------------------------
    # USERS
    # ------------------------------------------------------------
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        email TEXT UNIQUE,
        password TEXT
    );
    """)
    
    # ------------------------------------------------------------
    # ALLOWANCES
    # ------------------------------------------------------------
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS allowances (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        amount REAL,
        date TEXT,
        FOREIGN KEY(user_id) REFERENCES users(id)
    );
    """)

    # ------------------------------------------------------------
    # RECURRING EXPENSES
    # ------------------------------------------------------------
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS recurring_expenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        title TEXT,
        amount REAL,
        category TEXT,
        frequency TEXT,
        next_date TEXT,
        status TEXT DEFAULT 'active',
        FOREIGN KEY(user_id) REFERENCES users(id)
    );
    """)

    # ------------------------------------------------------------
    # EXPENSES
    # ------------------------------------------------------------
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS expenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        category TEXT,
        amount REAL,
        description TEXT,
        date TEXT,
        FOREIGN KEY(user_id) REFERENCES users(id)
    );
    """)

    # ------------------------------------------------------------
    # OLD RECURRING (IGNORED)
    # ------------------------------------------------------------
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS recurring (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        name TEXT,
        amount REAL,
        period TEXT,
        next_date TEXT
    );
    """)

    # ------------------------------------------------------------
    # CATEGORY LIMITS
    # ------------------------------------------------------------
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS category_limits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        category TEXT,
        limit_amount REAL,
        FOREIGN KEY(user_id) REFERENCES users(id)
    );
    """)

    # ------------------------------------------------------------
    # FINAL GOALS TABLE (CLEAN + MATCHES YOUR CODE!)
    # ------------------------------------------------------------
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS goals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        title TEXT NOT NULL,
        target_amount REAL NOT NULL,
        saved_amount REAL DEFAULT 0,
        due_date TEXT,
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY(user_id) REFERENCES users(id)
    );
    """)
    

    conn.commit()
    conn.close()


def alter_table():
    conn = get_db()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            ALTER TABLE recurring_expenses
            ADD COLUMN status TEXT DEFAULT 'active'
        """)
        print("Column 'status' added successfully!")
    except:
        print("Column already exists (OK)")

    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_db()
    alter_table()
    print("Database (database.db) initialized successfully!")
