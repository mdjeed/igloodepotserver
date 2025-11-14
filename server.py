import asyncio
import websockets
import mysql.connector
import json
import uuid
import os
from mysql.connector import Error


# ==========================
# تحميل الإعدادات
# ==========================
with open('setting.json') as config_file:
    config = json.load(config_file)

db_config = config['database']

# 📌 Railway يعطي PORT أوتوماتيك
PORT = int(os.getenv("PORT", config["server"]["port"]))
HOST = "0.0.0.0"

print("ENV VARS:", os.environ)


# ==========================
# DB
# ==========================
def get_db_connection():
    try:
        conn = mysql.connector.connect(
            host=db_config['host'],
            user=db_config['user'],
            password=db_config['password'],
            database=db_config['database']
        )
        return conn
    except Error as e:
        print(f"MySQL connection error: {e}")
        return None


def ensure_connection():
    global db, cursor
    try:
        db.ping(reconnect=True, attempts=3, delay=2)
    except:
        print("⚠️ Lost DB connection, reconnecting...")
        db = get_db_connection()
        cursor = db.cursor()


db = get_db_connection()
cursor = db.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS mstkhdm_igloo (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(255),
    password VARCHAR(255),
    token VARCHAR(255)
)
""")
db.commit()


# ==========================
# WebSocket Handler
# ==========================
async def handle_connection(websocket, path):
    try:
        print("Client connected:", websocket.remote_address)

        async for message in websocket:
            ensure_connection()
            data = json.loads(message)
            action = data.get("action")

            # Login
            if action == "login":
                cursor.execute(
                    "SELECT * FROM mstkhdm_igloo WHERE username=%s AND password=%s",
                    (data["username"], data["password"])
                )
                user = cursor.fetchone()

                if user:
                    token = str(uuid.uuid4())
                    cursor.execute("UPDATE mstkhdm_igloo SET token=%s WHERE id=%s", (token, user[0]))
                    db.commit()

                    await websocket.send(json.dumps({
                        "status": "success",
                        "message": "Logged in",
                        "token": token
                    }))
                else:
                    await websocket.send(json.dumps({
                        "status": "error",
                        "message": "Invalid login"
                    }))

            # check session
            elif action == "check_login":
                cursor.execute("SELECT * FROM mstkhdm_igloo WHERE token=%s", (data["token"],))
                user = cursor.fetchone()

                if user:
                    await websocket.send(json.dumps({"status": "success", "username": user[1]}))
                else:
                    await websocket.send(json.dumps({"status": "invalid"}))

            # Categories
            elif action == "get_catego":
                cursor.execute("SELECT id, name FROM categories")
                items = cursor.fetchall()
                await websocket.send(json.dumps({
                    "status": "catego list",
                    "categories": [{"id": c[0], "name": c[1]} for c in items]
                }))

            # Products by category
            elif action == "get_items_by_category":
                cursor.execute("SELECT name, id, quantity FROM products WHERE category_id=%s",
                               (data["category_id"],))
                items = cursor.fetchall()
                await websocket.send(json.dumps({
                    "status": "product list",
                    "items": [{"name": i[0], "id": i[1], "quantity": i[2]} for i in items]
                }))

            # Add category
            elif action == "add_category":
                cursor.execute("SELECT id FROM categories WHERE name=%s", (data["name"],))
                exist = cursor.fetchone()

                if exist:
                    await websocket.send(json.dumps({"status": "exists"}))
                else:
                    cursor.execute("INSERT INTO categories (name) VALUES (%s)", (data["name"],))
                    db.commit()
                    await websocket.send(json.dumps({"status": "success"}))

            # Update check
            elif action == "check_update":
                await websocket.send(json.dumps({
                    "action": "app_update",
                    "version": "1.0.2",
                    "urlupdate": "https://play.google.com/store/apps/details?id=com.mycompany.igloo"
                }))

    except Exception as e:
        print("❌ Error:", e)


# ==========================
# Run Server (NO SSL)
# ==========================
async def main():
    print(f"🚀 Starting WebSocket on {HOST}:{PORT}")

    async with websockets.serve(
        handle_connection,
        HOST,
        PORT
    ):
        print("Server is ready.")
        await asyncio.Future()  # Make server run forever


if __name__ == "__main__":
    asyncio.run(main())