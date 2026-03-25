import asyncio
import websockets
import mysql.connector
import json
import uuid
import ssl


with open('setting.json') as config_file:
    config = json.load(config_file)

db_config = config['database']
server_config = config['server']

db = mysql.connector.connect(
    host=db_config['host'],
    user=db_config['user'],
    password=db_config['password'],
    database=db_config['database']
)

cursor = db.cursor()

cursor.execute('''CREATE TABLE IF NOT EXISTS mstkhdm_igloo (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    username VARCHAR(255) NOT NULL,
                    password VARCHAR(255) NOT NULL,
                    token VARCHAR(255)
                )''')

db.commit()

async def handle_connection(websocket):
    try:
        client_ip = websocket.remote_address[0]
        print(f"Client connected from IP: {client_ip}")
        async for message in websocket:
            data = json.loads(message)

            if data['action'] == 'login':
                username = data['username']
                password = data['password']
    
                
                cursor.execute('SELECT * FROM mstkhdm_igloo WHERE username=%s AND password=%s', (username, password))
                user = cursor.fetchone()

                if user:
                    token = str(uuid.uuid4()) 
                    cursor.execute('UPDATE mstkhdm_igloo SET token=%s WHERE id=%s', (token, user[0]))
                    db.commit()
                    response = {'status': 'success', 'message': 'Logged in successfully', 'token': token,'name':user[4]}
                    print(f'User {username} logged in.')
                else:
                    response = {'status': 'error', 'message': 'Invalid credentials'}
                
                await websocket.send(json.dumps(response))




            
            elif data['action'] == 'check_login':
                token = data['token']
                cursor.execute('SELECT * FROM mstkhdm_igloo WHERE token=%s', (token,))
                user = cursor.fetchone()
                
                if user:
                    response = {'status': 'success', 'username': user[1]}
                    print(f'User {user[1]} checked login status.')
                else:
                    response = {'status': 'errorlog', 'message': 'Invalid session'}
                
                await websocket.send(json.dumps(response))



            elif data['action'] == 'get_catego':
                cursor.execute("SELECT id, name FROM categories")  
                items = cursor.fetchall()
              
                items_list = [{'id': item[0], 'name': item[1]} for item in items]  
                await websocket.send(json.dumps({"status": "catego list", "categories": items_list}))

            
            elif data['action'] == 'get_items_by_category':
                categoryid = data['category_id'] 
                cursor.execute("SELECT name, id, quantity FROM products WHERE category_id = %s", (categoryid,))
                products = cursor.fetchall()

                products_list = [{'name': product[0], 'id': product[1], 'quantity': product[2]} for product in products]

                await websocket.send(json.dumps({"status": "product list", "items": products_list}))




            elif data['action'] == 'add_product':
                productname = data['name'] 
                quantityproduct = data['quantity']
                categoryid = data['category_id']

          
                cursor.execute("SELECT quantity FROM products WHERE name = %s AND category_id = %s", (productname, categoryid))
                result = cursor.fetchone()

                if result:
                   
                    current_quantity = result[0]
                    new_quantity = current_quantity + quantityproduct
                    cursor.execute("UPDATE products SET quantity = %s WHERE name = %s AND category_id = %s", (new_quantity, productname, categoryid))
                else:
                   
                    cursor.execute("INSERT INTO products (name, quantity, category_id) VALUES (%s, %s, %s)", (productname, quantityproduct, categoryid))
                
                db.commit()
                await websocket.send(json.dumps({"status": "product list"}))





            elif data['action'] == 'selcteditem':
            
                items = data['itemsSelected']
                date = data['date']
                added_by = data.get('added_by')
                company = data.get('company')
                branch_id = data['branch_id'] 
            
                for item in items:
                    item_id = item['id']          
                    name = item['name']
                    quantity = item['counter']
            
              
                    cursor.execute("""
                        INSERT INTO inventory (item_name, quantity, date, added_by, company)
                        VALUES (%s, %s, %s, %s, %s)
                    """, (name, quantity, date, added_by, company))
            
 
                    cursor.execute("""
                        UPDATE Branch_Items
                        SET quantity = quantity - %s
                        WHERE branch_id = %s 
                        AND item_id = %s
                        AND quantity >= %s
                    """, (quantity, branch_id, item_id, quantity))
            
                db.commit()
            
 
                categoryid = data.get('category_id')
            
                cursor.execute("""
                    SELECT
                    products.name,
                    products.id,
                    Branch_Items.quantity
            
                    FROM Branch_Items
            
                    JOIN products
                    ON Branch_Items.item_id = products.id
            
                    WHERE Branch_Items.branch_id = %s
                    AND products.category_id = %s
                """, (branch_id, categoryid))
            
                products = cursor.fetchall()
            
                products_list = [
                    {
                        'name': product[0],
                        'id': product[1],
                        'quantity': product[2]
                    }
                    for product in products
                ]
            
                await websocket.send(json.dumps({
                    "status": "get_items_by_category",
                    "items": products_list
                }))

                                



            elif data['action'] == 'getselecteditem':
                cursor.execute("SELECT date, item_name, quantity, added_by , company FROM inventory") 
                sel3adate = cursor.fetchall()
                
                items_info = [{'date': row[0].strftime('%Y-%m-%d'), 'name': row[1], 'quantity': row[2], 'added_by': row[3],'company':row[4]} for row in sel3adate]

                websocket_message = {
                    'action': 'send_items_info',
                    'itemsout': items_info
                }
                await websocket.send(json.dumps(websocket_message))


            elif data['action'] == 'check_update':
          
                latest_version = "1.0.2" 
                urlupdate="https://play.google.com/store/apps/details?id=com.mycompany.igloo"
                response = {
                    'action': 'app_update',
                    'urlupdate':urlupdate, 
                    'version': latest_version   
                }
                await websocket.send(json.dumps(response))


            elif data['action'] == 'add_category':
                            category_name = data['name']
                            
                            
                            cursor.execute("SELECT id FROM categories WHERE name = %s", (category_name,))
                            existing_category = cursor.fetchone()

                            if existing_category:
                                response = {"status": "error", "message": "Category already exists"}
                            else:
                                cursor.execute("INSERT INTO categories (name) VALUES (%s)", (category_name,))
                                db.commit()
                                response = {"status": "success", "message": "Category added successfully"}
                            
                            await websocket.send(json.dumps(response))



            
            elif data['action'] == 'ping':
               print('pong')
               await websocket.send(json.dumps({'action': 'pong'}))


            
  

           
            elif data['action'] == 'add_branch':
                branchname=data['branch_name']
                cursor.execute("INSERT INTO Branches (branchname) VALUES (%s)", (branchname,))
                db.commit()
                response = {"status": "addbranchsuccess"}
                await websocket.send(json.dumps(response))
                 
                
            elif data['action'] == 'get_branch':
                 cursor.execute("SELECT id, branchname FROM Branches")  
                 items = cursor.fetchall()
              
                 items_list = [{'id': item[0], 'branchname': item[1]} for item in items]  
                 await websocket.send(json.dumps({"status": "branch_list", "branches": items_list}))

            elif data['action'] == 'get_items_all_branches':

                    category_id = data['category_id']
                
                    cursor.execute("""
                        SELECT
                        products.id,
                        products.name,
                        SUM(Branch_Items.quantity) AS total_quantity
                
                        FROM Branch_Items
                
                        JOIN products
                        ON Branch_Items.item_id = products.id
                
                        WHERE products.category_id = %s
                
                        GROUP BY
                        products.id,
                        products.name
                
                        ORDER BY products.name
                    """, (category_id,))
                
                    rows = cursor.fetchall()
                
                    items = [
                        {
                            "id": row[0],
                            "name": row[1],
                            "quantity": int(row[2])
                        }
                        for row in rows
                    ]
                
                    await websocket.send(json.dumps({
                        "status": "items_list_all",
                        "items": items
                    }))
                            

            elif data['action'] == 'get_items_bybranchandcatego':
                    
                        branch_id = data['branch_id']
                        category_id = data['category_id']
                    
                        cursor.execute("""
                            SELECT
                            products.id,
                            products.name,
                            Branch_Items.quantity
                            FROM Branch_Items
                    
                            JOIN products
                            ON Branch_Items.item_id = products.id
                    
                            WHERE Branch_Items.branch_id = %s
                            AND products.category_id = %s
                        """, (branch_id, category_id))
                    
                        rows = cursor.fetchall()
                    
                        items = [
                            {
                                "id": row[0],
                                "name": row[1],
                                "quantity": row[2]
                            }
                            for row in rows
                        ]
                    
                        await websocket.send(json.dumps({
                            "status": "items_list",
                            "items": items
                        }))
                                
                                
                     
                                

            elif data['action'] == 'get_categories_by_branch':

                    branch_id = data['branch_id']
    
                    cursor.execute("""
                        SELECT DISTINCT
                        categories.id,
                        categories.name
                        FROM Branch_Items
                
                        JOIN products
                        ON Branch_Items.item_id = products.id
                
                        JOIN categories
                        ON products.category_id = categories.id
                
                        WHERE Branch_Items.branch_id = %s
                    """, (branch_id,))
                
                    items = cursor.fetchall()
                
                    items_list = [
                        {'id': item[0], 'name': item[1]}
                        for item in items
                    ]
                    
                    await websocket.send(json.dumps({
                        "status": "category_list",
                        "categories": items_list
                    }))
                                                        


                       

            elif data['action'] == 'update_item':
                    item_id = data.get('item_id')
                    updated_name = data.get('updated_name') 
                    updated_quantity = data.get('updated_quantity')  
                    added_quantity = data.get('added_quantity', 0)  

                
                    cursor.execute("SELECT name, quantity FROM products WHERE id = %s", (item_id,))
                    item = cursor.fetchone()

                    if not item:
                        response = {
                            'status': 'error',
                            'message': 'Item not found',
                        }
                    else:
                        current_name, current_quantity = item  

                   
                        new_name = updated_name if updated_name else current_name
                        new_quantity = (updated_quantity if updated_quantity is not None else current_quantity) + added_quantity

                        cursor.execute("""
                            UPDATE products
                            SET name = %s, quantity = %s
                            WHERE id = %s
                        """, (new_name, new_quantity, item_id))
                        db.commit()

                        response = {
                            'status': 'update_success',
                            'item_id': item_id,
                            'updated_name': new_name,
                            'updated_quantity': new_quantity,
                        }

                    await websocket.send(json.dumps(response))







    except websockets.exceptions.ConnectionClosedOK:
        print("Connection closed normally")
    except websockets.exceptions.ConnectionClosedError as e:
        print(f"Connection closed with error: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")
ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
ssl_context.load_cert_chain(certfile="server.crt",
                            keyfile="server.key")

async def main():
    print(f"Server starting on {server_config['host']}:{server_config['port']}")
    async with websockets.serve(handle_connection, server_config['host'], server_config['port']):
        print("Server is running...")
        await asyncio.Future()  # تشغيل دائم (انتظار لا نهائي)

if __name__ == "__main__":
    asyncio.run(main())
