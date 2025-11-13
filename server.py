import asyncio
import websockets
import mysql.connector
import json
import uuid
import ssl
from mysql.connector import Error

# تحميل الإعدادات من ملف JSON
with open('setting.json') as config_file:
    config = json.load(config_file)

db_config = config['database']
server_config = config['server']

# ==========================
# 🔁 نظام ذكي للاتصال بقاعدة البيانات
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
    """تأكد من أن الاتصال مفتوح، وإعادة الاتصال إذا انقطع"""
    global db, cursor
    try:
        db.ping(reconnect=True, attempts=3, delay=2)
    except:
        print("⚠️ Lost connection, reconnecting to MySQL...")
        db = get_db_connection()
        cursor = db.cursor()

# إنشاء الاتصال المبدئي
db = get_db_connection()
cursor = db.cursor()

cursor.execute('''CREATE TABLE IF NOT EXISTS mstkhdm_igloo (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    username VARCHAR(255) NOT NULL,
                    password VARCHAR(255) NOT NULL,
                    token VARCHAR(255)
                )''')
db.commit()

# ==========================
# 🧠 دالة معالجة الاتصالات
# ==========================
async def handle_connection(websocket, path):
    try:
        client_ip = websocket.remote_address[0]
        print(f"Client connected from IP: {client_ip}")

        async for message in websocket:
            ensure_connection()
            data = json.loads(message)
            action = data.get('action')

            if action == 'login':
                username = data['username']
                password = data['password']

                cursor.execute('SELECT * FROM mstkhdm_igloo WHERE username=%s AND password=%s', (username, password))
                user = cursor.fetchone()

                if user:
                    token = str(uuid.uuid4())
                    cursor.execute('UPDATE mstkhdm_igloo SET token=%s WHERE id=%s', (token, user[0]))
                    db.commit()
                    response = {'status': 'success', 'message': 'Logged in successfully', 'token': token}
                else:
                    response = {'status': 'error', 'message': 'Invalid credentials'}
                
                await websocket.send(json.dumps(response))

            elif action == 'check_login':
                token = data['token']
                cursor.execute('SELECT * FROM mstkhdm_igloo WHERE token=%s', (token,))
                user = cursor.fetchone()
                
                if user:
                    response = {'status': 'success', 'username': user[1]}
                else:
                    response = {'status': 'errorlog', 'message': 'Invalid session'}
                
                await websocket.send(json.dumps(response))

            elif action == 'get_catego':
                cursor.execute("SELECT id, name FROM categories")
                items = cursor.fetchall()
                items_list = [{'id': item[0], 'name': item[1]} for item in items]
                await websocket.send(json.dumps({"status": "catego list", "categories": items_list}))

            elif action == 'get_items_by_category':
                categoryid = data['category_id']
                cursor.execute("SELECT name, id, quantity FROM products WHERE category_id = %s", (categoryid,))
                products = cursor.fetchall()
                products_list = [{'name': p[0], 'id': p[1], 'quantity': p[2]} for p in products]
                await websocket.send(json.dumps({"status": "product list", "items": products_list}))

            elif action == 'add_product':
                productname = data['name']
                quantityproduct = data['quantity']
                categoryid = data['category_id']

                cursor.execute("SELECT quantity FROM products WHERE name = %s AND category_id = %s", (productname, categoryid))
                result = cursor.fetchone()

                if result:
                    new_quantity = result[0] + quantityproduct
                    cursor.execute("UPDATE products SET quantity = %s WHERE name = %s AND category_id = %s",
                                   (new_quantity, productname, categoryid))
                else:
                    cursor.execute("INSERT INTO products (name, quantity, category_id) VALUES (%s, %s, %s)",
                                   (productname, quantityproduct, categoryid))
                
                db.commit()
                await websocket.send(json.dumps({"status": "product list"}))

            elif action == 'add_category':
                category_name = data['name']
                cursor.execute("SELECT id FROM categories WHERE name = %s", (category_name,))
                existing = cursor.fetchone()

                if existing:
                    response = {"status": "error", "message": "Category already exists"}
                else:
                    cursor.execute("INSERT INTO categories (name) VALUES (%s)", (category_name,))
                    db.commit()
                    response = {"status": "success", "message": "Category added successfully"}
                await websocket.send(json.dumps(response))

            elif action == 'check_update':
                latest_version = "1.0.2"
                urlupdate = "https://play.google.com/store/apps/details?id=com.mycompany.igloo"
                response = {'action': 'app_update', 'urlupdate': urlupdate, 'version': latest_version}
                await websocket.send(json.dumps(response))

    except Exception as e:
        print(f"❌ Unexpected error: {e}")

# ==========================
# 🚀 تشغيل الخادم بالطريقة الصحيحة (asyncio.run)
# ==========================
async def main():
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ssl_context.load_cert_chain(certfile="server.crt", keyfile="server.key")

    async with websockets.serve(
        handle_connection,
        server_config['host'],
        server_config['port'],
        ssl=ssl_context
    ):
        print(f"🚀 Server started on {server_config['host']}:{server_config['port']}")
        await asyncio.Future()  # تشغيل دائم

if __name__ == "__main__":
    asyncio.run(main())