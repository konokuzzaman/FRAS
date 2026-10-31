from mysql.connector import connect, Error
from config import DB_CONFIG

try:
    conn = connect(**DB_CONFIG)
    print("DB connected successfully!")
    conn.close()
except Error as e:
    print("DB connection error:", e)