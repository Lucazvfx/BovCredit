import sqlite3

def explore_db():
    conn = sqlite3.connect('gestao.db')
    cursor = conn.cursor()
    
    # Get tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    print("Tables:", tables)
    
    for table in tables:
        table_name = table[0]
        print(f"\nSchema for {table_name}:")
        cursor.execute(f"PRAGMA table_info({table_name});")
        info = cursor.fetchall()
        for col in info:
            print(col)
            
        # Exemplo local: procure apenas uma conta sintética de desenvolvimento.
        if 'usuario' in table_name.lower():
            print(f"\nSearching for user in {table_name}...")
            cursor.execute(f"SELECT * FROM {table_name} WHERE email = 'dev@example.invalid';")
            user = cursor.fetchone()
            if user:
                print("Found user:", user)
            else:
                print("User not found.")
                
    conn.close()

if __name__ == "__main__":
    explore_db()
