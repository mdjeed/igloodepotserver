import asyncio
import websockets
import mysql.connector
import json
import uuid
import ssl
from mysql.connector import Error

# =========================
# تحميل الإعدادات
# =========================
with open('setting.json') as config_file:
    config = json.load(config_file)

db_config = config['database']
server_config = config['server']


# =========================
# دالة اتصال آمن بـ MySQL
# =========================
def get_db():
    return mysql.connector.connect(
        host=db_config['host'],
        user=db_config['user'],
        password=db_config['password'],
        database=db_config['database'],
        connection_timeout=30,
        autocommit=True
    )


# =========================
# WebSocket Handler
# =========================
async def handle_connection(websocket):
    client_ip = websocket.remote_address[0]
    print(f"Client connected from IP: {client_ip}")

    try:
        async for message in websocket:
            data = json.loads(message)

            try:
                db = get_db()
                cursor = db.cursor()

                # ================= LOGIN =================
                if data['action'] == 'login':
                    cursor.execute(
                        "SELECT id, username FROM mstkhdm_igloo WHERE username=%s AND password=%s",
                        (data['username'], data['password'])
                    )
                    user = cursor.fetchone()

                    if user:
                        token = str(uuid.uuid4())
                        cursor.execute(
                            "UPDATE mstkhdm_igloo SET token=%s WHERE id=%s",
                            (token, user[0])
                        )
                        response = {
                            'status': 'success',
                            'token': token,
                            'username': user[1]
                        }
                    else:
                        response = {'status': 'error', 'message': 'Invalid credentials'}

                    await websocket.send(json.dumps(response))

                # ================= CHECK LOGIN =================
                elif data['action'] == 'check_login':
                    cursor.execute(
                        "SELECT username FROM mstkhdm_igloo WHERE token=%s",
                        (data['token'],)
                    )
                    user = cursor.fetchone()

                    if user:
                        response = {'status': 'success', 'username': user[0]}
                    else:
                        response = {'status': 'errorlog'}

                    await websocket.send(json.dumps(response))

                # ================= GET CATEGORIES =================
                elif data['action'] == 'get_catego':
                    cursor.execute("SELECT id, name FROM categories")
                    categories = cursor.fetchall()

                    await websocket.send(json.dumps({
                        "status": "catego list",
                        "categories": [{'id': i[0], 'name': i[1]} for i in categories]
                    }))

                # ================= GET PRODUCTS =================
                elif data['action'] == 'get_items_by_category':
                    cursor.execute(
                        "SELECT id, name, quantity FROM products WHERE category_id=%s",
                        (data['category_id'],)
                    )
                    products = cursor.fetchall()

                    await websocket.send(json.dumps({
                        "status": "product list",
                        "items": [{'id': p[0], 'name': p[1], 'quantity': p[2]} for p in products]
                    }))

                # ================= ADD PRODUCT =================
                elif data['action'] == 'add_product':
                    cursor.execute(
                        "INSERT INTO products (name, quantity, category_id) VALUES (%s,%s,%s)",
                        (data['name'], data['quantity'], data['category_id'])
                    )
                    await websocket.send(json.dumps({"status": "success"}))

                # ================= UPDATE ITEM =================
                elif data['action'] == 'update_item':
                    cursor.execute(
                        "UPDATE products SET name=%s, quantity=%s WHERE id=%s",
                        (data['updated_name'], data['updated_quantity'], data['item_id'])
                    )
                    await websocket.send(json.dumps({"status": "update_success"}))

                # ================= APP UPDATE =================
                elif data['action'] == 'check_update':
                    await websocket.send(json.dumps({
                        'action': 'app_update',
                        'version': '1.0.2',
                        'urlupdate': 'https://play.google.com/store/apps/details?id=com.mycompany.igloo'
                    }))

            except Error as e:
                print("DB Error:", e)
                await websocket.send(json.dumps({
                    'status': 'error',
                    'message': 'Database error'
                }))

            finally:
                if cursor:
                    cursor.close()
                if db:
                    db.close()

    except websockets.exceptions.ConnectionClosed:
        print("Client disconnected")


# =========================
# SSL
# =========================
ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
ssl_context.load_cert_chain("server.crt", "server.key")


# =========================
# Run Server
# =========================
async def main():
    print(f"Server running on {server_config['host']}:{server_config['port']}")
    async with websockets.serve(
        handle_connection,
        server_config['host'],
        server_config['port'],
        ssl=ssl_context
    ):
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())
