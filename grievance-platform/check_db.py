import os

USE_MYSQL = os.environ.get('DB_TYPE', '').lower() == 'mysql'

if USE_MYSQL:
    import mysql.connector
    cfg = {
        'host': os.environ.get('MYSQL_HOST', 'localhost'),
        'user': os.environ.get('MYSQL_USER', 'root'),
        'password': os.environ.get('MYSQL_PASSWORD', ''),
        'database': os.environ.get('MYSQL_DATABASE', 'grievance_db'),
    }
    conn = mysql.connector.connect(**cfg)
else:
    import sqlite3
    conn = sqlite3.connect('grievance.db')

c = conn.cursor()

c.execute('SELECT COUNT(*) FROM complaints')
print('Total complaints:', c.fetchone()[0])

c.execute('SELECT id, title, status, created_at FROM complaints ORDER BY id DESC LIMIT 5')
for row in c.fetchall():
    print(row)

conn.close()