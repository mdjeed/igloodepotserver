import asyncio
import websockets
import mysql.connector
import json
import uuid
import os
from mysql.connector import Error

# ==========================
# تحميل الإعدادات من ملف JSON
# ==========================
with open('setting.json') as config_file:
    config = json.load(config_file)

db_config = config['database']

# ==========================
# 🔁 الاتصال بقاعدة البيانات
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
    """إعادة الاتصال عند الانقطاع"""
    global db, cursor
    try:
        db.ping(reconnect=True, attempts=3, delay=2)
    except:
        print("⚠️ Lost connection. Reconnecting...")
        db = get_db_connection()
        cursor = db.cursor()


# إنشاء الاتصال الأولي
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
# 🧠 معالجة الاتصال
# ==========================
async def handle_connection(websocket):
    try:
        print("Client connected")

        async for message in websocket:
            ensure_connection()
            data = json.loads(message)
            action = data.get('action')

            # ------------------- LOGIN -------------------
            if action == 'login':
                username = data['username']
                password = data['password']

                cursor.execute(
                    'SELECT * FROM mstkhdm_igloo WHERE username=%s AND password=%s',
                    (username, password)
                )
                user = cursor.fetchone()

                if user:
                    token = str(uuid.uuid4())
                    cursor.execute(
                        'UPDATE mstkhdm_igloo SET token=%s WHERE id=%s',
                        (token, user[0])
                    )
                    db.commit()
                    response = {'status': 'success', 'message': 'Logged in successfully', 'token': token}
                else:
                    response = {'status': 'error', 'message': 'Invalid credentials'}

                await websocket.send(json.dumps(response))

            # ------------------- CHECK LOGIN -------------------
            elif action == 'check_login':
                token = data['token']

                cursor.execute(
                    'SELECT * FROM mstkhdm_igloo WHERE token=%s',
                    (token,)
                )
                user = cursor.fetchone()

                if user:
                    response = {'status': 'success', 'username': user[1]}
                else:
                    response = {'status': 'errorlog', 'message': 'Invalid session'}

                await websocket.send(json.dumps(response))

            # ------------------- GET CATEGORY -------------------
            elif action == 'get_catego':
                cursor.execute("SELECT id, name FROM categories")
                items = cursor.fetchall()
                items_list = [{'id': i[0], 'name': i[1]} for i in items]

                await websocket.send(json.dumps({
                    "status": "catego list",
                    "categories": items_list
                }))

            # ------------------- GET ITEMS BY CATEGORY -------------------
            elif action == 'get_items_by_category':
                categoryid = data['category_id']
                cursor.execute("SELECT name, id, quantity FROM products WHERE category_id = %s", (categoryid,))
                products = cursor.fetchall()

                products_list = [
                    {'name': p[0], 'id': p[1], 'quantity': p[2]} for p in products
                ]

                await websocket.send(json.dumps({
                    "status": "product list",
                    "items": products_list
                }))

            # ------------------- ADD PRODUCT -------------------
            elif action == 'add_product':
                productname = data['name']
                quantityproduct = data['quantity']
                categoryid = data['category_id']

                cursor.execute(
                    "SELECT quantity FROM products WHERE name = %s AND category_id = %s",
                    (productname, categoryid)
                )
                result = cursor.fetchone()

                if result:
                    new_quantity = result[0] + quantityproduct
                    cursor.execute(
                        "UPDATE products SET quantity = %s WHERE name = %s AND category_id = %s",
                        (new_quantity, productname, categoryid)
                    )
                else:
                    cursor.execute(
                        "INSERT INTO products (name, quantity, category_id) VALUES (%s, %s, %s)",
                        (productname, quantityproduct, categoryid)
                    )

                db.commit()
                await websocket.send(json.dumps({"status": "product list"}))

            # ------------------- ADD CATEGORY -------------------
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

            # ------------------- CHECK UPDATE -------------------
            elif action == 'check_update':
                await websocket.send(json.dumps({
                    'action': 'app_update',
                    'urlupdate': 'https://play.google.com/store/apps/details?id=com.mycompany.igloo',
                    'version': "1.0.2"
                }))

    except Exception as e:
        print(f"❌ Error: {e}")


# ==========================
# 🚀 تشغيل الخادم (بدون SSL - مناسب لـ Railway)
# ==========================
async def main():
    port = int(os.getenv("PORT", 8080))   # Railway يعطيك PORT تلقائيًا

    print(f"🚀 Server running on 0.0.0.0:{port}")

    async with websockets.serve(
        handle_connection,
        "0.0.0.0",
        port
    ):
        await asyncio.Future()  # يمنع الإغلاق


if __name__ == "__main__":
    asyncio.run(main())