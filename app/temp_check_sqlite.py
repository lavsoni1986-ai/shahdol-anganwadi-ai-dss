import sqlite3, sys, os

def main(db_path):
    if not os.path.exists(db_path):
        print(f"Database file not found: {db_path}")
        sys.exit(1)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cur.fetchall()
    if tables:
        print('Tables in database:')
        for t in tables:
            print(t[0])
    else:
        print('No tables found.')
    conn.close()

if __name__ == '__main__':
    if len(sys.argv) != 2:
        print('Usage: python temp_check_sqlite.py <path_to_db>')
        sys.exit(1)
    main(sys.argv[1])
