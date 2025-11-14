# server.py (DEBUG)
import asyncio, websockets, mysql.connector, json, uuid, os, traceback, sys
from mysql.connector import Error

# طباعة كل شيء إلى stdout
def log(*args, **kwargs):
    print(*args, **kwargs)
    sys.stdout.flush()

# قراءة الإعدادات
try:
    with open('setting.json') as f:
        config = json.load(f)
except Exception as e:
    log("ERROR: cannot read setting.json:", e)
    config = {"database": {}}

db_config = config.get('database', {})
HOST_ENV = os.getenv("HOST", "0.0.0.0")
PORT_ENV = int(os.getenv("PORT", os.getenv("PORT", "0") or 0))  # Railway يعطينا PORT env

log("ENV VARS:", {k: os.getenv(k) for k in ["PORT", "RAILWAY_ENV", "RAILWAY_STATIC_URL"] if os.getenv(k)})
log("server will bind to HOST:", HOST_ENV, "PORT(env):", PORT_ENV)

# DB connection helpers
def get_db_connection():
    try:
        conn = mysql.connector.connect(
            host=db_config.get('host', os.getenv("DB_HOST")),
            port=int(db_config.get('port', os.getenv("DB_PORT") or 3306)),
            user=db_config.get('user', os.getenv("DB_USER")),
            password=db_config.get('password', os.getenv("DB_PASS")),
            database=db_config.get('database', os.getenv("DB_NAME"))
        )
        log("DB connected ok")
        return conn
    except Exception as e:
        log("DB connection failed:", e)
        return None

def ensure_connection():
    global db, cursor
    try:
        if db is None:
            raise Exception("db is None")
        db.ping(reconnect=True, attempts=3, delay=2)
    except Exception as e:
        log("DB ping failed, reconnecting...", e)
        db = get_db_connection()
        if db:
            cursor = db.cursor()
        else:
            cursor = None

db = get_db_connection()
cursor = db.cursor() if db else None

# create tables minimal safe (wrapped)
try:
    if cursor:
        cursor.execute('''CREATE TABLE IF NOT EXISTS mstkhdm_igloo (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(255) NOT NULL,
            password VARCHAR(255) NOT NULL,
            token VARCHAR(255)
        )''')
        db.commit()
        log("Ensure users table exists")
except Exception:
    log("Warning: create table failed:", traceback.format_exc())

# handler
async def handle_connection(websocket):
    log("New websocket connection from:", websocket.remote_address)
    try:
        async for message in websocket:
            log("RCV:", message)
            ensure_connection()
            try:
                data = json.loads(message)
            except Exception:
                await websocket.send(json.dumps({"status":"error","message":"invalid json"}))
                continue

            action = data.get("action")
            if action == "ping":
                await websocket.send(json.dumps({"pong": True}))
            elif action == "check_db":
                if cursor:
                    try:
                        cursor.execute("SELECT 1")
                        await websocket.send(json.dumps({"db": "ok"}))
                    except Exception as e:
                        await websocket.send(json.dumps({"db": "error", "detail": str(e)}))
                else:
                    await websocket.send(json.dumps({"db":"no-cursor"}))
            else:
                await websocket.send(json.dumps({"status":"unknown action", "action": action}))

    except websockets.exceptions.ConnectionClosedOK:
        log("client closed normally")
    except Exception as e:
        log("handler exception:", traceback.format_exc())

# main
async def main():
    port = PORT_ENV or int(config.get("server", {}).get("port", 0) or 0) or 8080
    log("Starting server on 0.0.0.0 port:", port)
    async with websockets.serve(handle_connection, "0.0.0.0", port):
        log("websocket serve context entered")
        await asyncio.Future()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:
        log("Fatal error on startup:", traceback.format_exc())