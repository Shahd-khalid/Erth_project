import sqlite3
import json

conn = sqlite3.connect('db.sqlite3')
cur = conn.cursor()
cur.execute("SELECT id, description, image FROM cases_asset WHERE image LIKE '%photo_5917983429859413356_y.jpg%' OR image LIKE '%ChatGPT_Image_Mar_24_2026_05_52_32_PM.png%'")
rows = cur.fetchall()

for r in rows:
    print(f"ID:{r[0]}|DESC:{r[1]}|IMG:{r[2]}")
conn.close()
