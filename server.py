import asyncio
from aiohttp import web
import mysql.connector
import json
import uuid
import os

# ---------------- CONFIG ----------------
with open('setting.json') as config_file:
    config = json.load(config_file)

db_config = config['database']

# ---------------- DB CONNECTOR (pool بسيط) ----------------
def get_db():
    return mysql.connector.connect(
        host=db_config['host'],
        user=db_config['user'],
        port=db_config.get('port', 3306),
        password=db_config['password'],
        database=db_config['database'],
        autocommit=False
    )

# إنشاء الجدول إن لم يوجد
db_init = get_db()
cur_init = db_init.cursor()
cur_init.execute('''CREATE TABLE IF NOT EXISTS mstkhdm_igloo (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(255) NOT NULL,
    password VARCHAR(255) NOT NULL,
    token VARCHAR(255)
)''')
db_init.commit()
cur_init.close()
db_init.close()

# ---------------- WEBSOCKET ----------------
async def websocket_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    client_ip = request.remote
    print(f"Client connected: {client_ip}")

    db = get_db()
    cursor = db.cursor()

    try:
        async for msg in ws:
            if msg.type != web.WSMsgType.TEXT:
                continue

            try:
                data = json.loads(msg.data)
            except:
                await ws.send_json({'status': 'error', 'message': 'Invalid JSON'})
                continue

            action = data.get('action')

            # ================= LOGIN =================
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
                    response = {
                        'status': 'success',
                        'message': 'Logged in successfully',
                        'token': token,
                        'name': user[1]  # لو عندك عمود اسم مختلف عدله
                    }
                else:
                    response = {'status': 'error', 'message': 'Invalid credentials'}

                await ws.send_json(response)

            # ================= CHECK LOGIN =================
            elif action == 'check_login':
                token = data['token']
                cursor.execute('SELECT * FROM mstkhdm_igloo WHERE token=%s', (token,))
                user = cursor.fetchone()

                if user:
                    response = {'status': 'success', 'username': user[1]}
                else:
                    response = {'status': 'errorlog', 'message': 'Invalid session'}

                await ws.send_json(response)

            # ================= GET CATEGORIES =================
            elif action == 'get_catego':
                cursor.execute("SELECT id, name FROM categories")
                items = cursor.fetchall()

                await ws.send_json({
                    "status": "catego list",
                    "categories": [{'id': i[0], 'name': i[1]} for i in items]
                })

            # ================= GET ITEMS BY CATEGORY =================
            elif action == 'get_items_by_category':
                categoryid = data['category_id']
                cursor.execute(
                    "SELECT name, id, quantity FROM products WHERE category_id=%s",
                    (categoryid,)
                )
                products = cursor.fetchall()

                await ws.send_json({
                    "status": "product list",
                    "items": [
                        {'name': p[0], 'id': p[1], 'quantity': p[2]}
                        for p in products
                    ]
                })

            # ================= ADD PRODUCT =================
            elif action == 'add_product':
                productname = data['name']
                quantityproduct = data['quantity']
                categoryid = data['category_id']
                branch_id = data['branch_id']

                cursor.execute(
                    "SELECT id FROM products WHERE name=%s AND category_id=%s",
                    (productname, categoryid)
                )
                result = cursor.fetchone()

                if result:
                    product_id = result[0]
                else:
                    cursor.execute(
                        "INSERT INTO products (name, category_id) VALUES (%s,%s)",
                        (productname, categoryid)
                    )
                    product_id = cursor.lastrowid

                cursor.execute(
                    "SELECT quantity FROM Branch_Items WHERE branch_id=%s AND item_id=%s",
                    (branch_id, product_id)
                )
                branch_item = cursor.fetchone()

                if branch_item:
                    new_quantity = branch_item[0] + quantityproduct
                    cursor.execute(
                        "UPDATE Branch_Items SET quantity=%s WHERE branch_id=%s AND item_id=%s",
                        (new_quantity, branch_id, product_id)
                    )
                else:
                    cursor.execute(
                        "INSERT INTO Branch_Items (branch_id,item_id,quantity) VALUES (%s,%s,%s)",
                        (branch_id, product_id, quantityproduct)
                    )

                db.commit()

                await ws.send_json({
                    "status": "product_added",
                    "product_id": product_id
                })

            # ================= SELECTED ITEMS =================
            elif action == 'selcteditem':
                items = data['itemsSelected']
                branch_id = data['branch_id']
                date = data['date']
                added_by = data.get('added_by')
                company = data.get('company')

                not_available = []

                for item in items:
                    cursor.execute(
                        "SELECT quantity FROM Branch_Items WHERE branch_id=%s AND item_id=%s",
                        (branch_id, item['id'])
                    )
                    result = cursor.fetchone()

                    if result is None or result[0] < item['counter']:
                        not_available.append(item['name'])

                if not_available:
                    await ws.send_json({
                        "status": "not_available",
                        "items": not_available
                    })
                    continue

                for item in items:
                    cursor.execute(
                        "UPDATE Branch_Items SET quantity=quantity-%s WHERE branch_id=%s AND item_id=%s",
                        (item['counter'], branch_id, item['id'])
                    )

                    cursor.execute(
                        "INSERT INTO inventory (item_name, quantity, date, added_by, company) VALUES (%s,%s,%s,%s,%s)",
                        (item['name'], item['counter'], date, added_by, company)
                    )

                db.commit()

            # ================= GET INVENTORY =================
            elif action == 'getselecteditem':
                cursor.execute(
                    "SELECT date, item_name, quantity, added_by, company FROM inventory"
                )
                rows = cursor.fetchall()

                items_info = [{
                    'date': r[0].strftime('%Y-%m-%d'),
                    'name': r[1],
                    'quantity': r[2],
                    'added_by': r[3],
                    'company': r[4]
                } for r in rows]

                await ws.send_json({
                    'action': 'send_items_info',
                    'itemsout': items_info
                })

            # ================= CHECK UPDATE =================
            elif action == 'check_update':
                await ws.send_json({
                    'action': 'app_update',
                    'urlupdate': "https://play.google.com/store/apps/details?id=com.mycompany.igloo",
                    'version': "1.0.2"
                })

            # ================= ADD CATEGORY =================
            elif action == 'add_category':
                category_name = data['name']

                cursor.execute(
                    "SELECT id FROM categories WHERE name=%s",
                    (category_name,)
                )
                existing = cursor.fetchone()

                if existing:
                    await ws.send_json({
                        "status": "error",
                        "message": "Category already exists"
                    })
                else:
                    cursor.execute(
                        "INSERT INTO categories (name) VALUES (%s)",
                        (category_name,)
                    )
                    db.commit()
                    await ws.send_json({
                        "status": "success",
                        "message": "Category added successfully"
                    })

            # ================= PING =================
            elif action == 'ping':
                await ws.send_json({'action': 'pong'})

            # ================= UPDATE ITEM =================
            elif action == 'update_item':
                item_id = data.get('item_id')
                branch_id = data.get('branch_id')
                updated_name = data.get('updated_name')
                updated_quantity = data.get('updated_quantity')
                added_quantity = data.get('added_quantity', 0)

                cursor.execute("SELECT name FROM products WHERE id=%s", (item_id,))
                item = cursor.fetchone()

                if not item:
                    await ws.send_json({'status': 'error', 'message': 'Item not found'})
                    continue

                original_name = item[0]

                cursor.execute(
                    "SELECT quantity, custom_name FROM Branch_Items WHERE branch_id=%s AND item_id=%s",
                    (branch_id, item_id)
                )
                branch_item = cursor.fetchone()

                if not branch_item:
                    await ws.send_json({'status': 'error', 'message': 'Item not in branch'})
                    continue

                current_quantity, current_custom_name = branch_item

                new_quantity = (
                    updated_quantity if updated_quantity is not None else current_quantity
                ) + added_quantity

                new_name = updated_name if updated_name else current_custom_name

                cursor.execute(
                    "UPDATE Branch_Items SET quantity=%s, custom_name=%s WHERE branch_id=%s AND item_id=%s",
                    (new_quantity, new_name, branch_id, item_id)
                )
                db.commit()

                await ws.send_json({
                    'status': 'update_success',
                    'item_id': item_id,
                    'branch_id': branch_id,
                    'updated_name': new_name if new_name else original_name,
                    'updated_quantity': new_quantity
                })

            # ================= ADD BRANCH =================
            elif action == 'add_branch':
                branchname = data['branch_name']
                cursor.execute("INSERT INTO Branches (branchname) VALUES (%s)", (branchname,))
                db.commit()
                await ws.send_json({"status": "addbranchsuccess"})

            # ================= GET BRANCH =================
            elif action == 'get_branch':
                cursor.execute("SELECT id, branchname FROM Branches")
                rows = cursor.fetchall()

                await ws.send_json({
                    "status": "branch_list",
                    "branches": [{'id': r[0], 'branchname': r[1]} for r in rows]
                })

            # ================= ALL BRANCH ITEMS =================
            elif action == 'get_items_all_branches':
                category_id = data['category_id']

                cursor.execute("""
                    SELECT products.id, products.name, SUM(Branch_Items.quantity)
                    FROM Branch_Items
                    JOIN products ON Branch_Items.item_id = products.id
                    WHERE products.category_id = %s
                    GROUP BY products.id, products.name
                """, (category_id,))

                rows = cursor.fetchall()

                await ws.send_json({
                    "status": "items_list_all",
                    "items": [
                        {"id": r[0], "name": r[1], "quantity": int(r[2])}
                        for r in rows
                    ]
                })

            # ================= ITEMS BY BRANCH =================
            elif action == 'get_items_bybranchandcatego':
                branch_id = data['branch_id']
                category_id = data['category_id']

                cursor.execute("""
                    SELECT products.id,
                    COALESCE(Branch_Items.custom_name, products.name),
                    Branch_Items.quantity
                    FROM Branch_Items
                    JOIN products ON Branch_Items.item_id = products.id
                    WHERE Branch_Items.branch_id = %s AND products.category_id = %s
                """, (branch_id, category_id))

                rows = cursor.fetchall()

                await ws.send_json({
                    "status": "items_list",
                    "items": [
                        {"id": r[0], "name": r[1], "quantity": r[2]}
                        for r in rows
                    ]
                })

            # ================= CATEGORIES BY BRANCH =================
            elif action == 'get_categories_by_branch':
                branch_id = data['branch_id']

                cursor.execute("""
                    SELECT DISTINCT categories.id, categories.name
                    FROM Branch_Items
                    JOIN products ON Branch_Items.item_id = products.id
                    JOIN categories ON products.category_id = categories.id
                    WHERE Branch_Items.branch_id = %s
                """, (branch_id,))

                rows = cursor.fetchall()

                await ws.send_json({
                    "status": "category_list",
                    "categories": [{'id': r[0], 'name': r[1]} for r in rows]
                })

    finally:
        cursor.close()
        db.close()

    return ws

# ---------------- SERVER ----------------
app = web.Application()
app.router.add_get('/', websocket_handler)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    web.run_app(app, host="0.0.0.0", port=port)
