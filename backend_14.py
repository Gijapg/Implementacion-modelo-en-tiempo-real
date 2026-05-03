from logica_bot.ORDENES import *
from logica_bot.safe_operations import *
from logica_bot.MAIN_BOT import *

import MetaTrader5 as mt5
import asyncio
from quart import Quart, jsonify, request, session, Response
from functools import wraps
from dotenv import load_dotenv, find_dotenv
import bcrypt
from bcrypt import checkpw
import os
import stripe
import datetime
import aiomysql
import jwt

import logging
import os

log_dir = "logs"
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'{log_dir}/debug.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


symbol = 'EURUSD'
symbol2 = 'GBPUSD'
symbol3 = 'EURGBP'
symbol4 = 'USDJPY'
symbol5 = 'GBPJPY'
symbol6 = 'USDCAD'
symbol7 = 'USDCHF'
n_candles = 200

dotenv_path = find_dotenv("db_keys.env")
if dotenv_path:
    load_dotenv(dotenv_path)

DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "database": os.getenv("DB_NAME")
}

app = Quart(__name__)
APP_CONFIG = {
    "secret_key" : os.getenv("SECRET_KEY"),
    "secret_key_app" : os.getenv("app_secret_key")
}
SECRET_KEY = APP_CONFIG["secret_key"]
app.secret_key = APP_CONFIG["secret_key_app"]  

@app.route('/')
async def index():
    session['user'] = 'admin'  
    return 'Hello, World'

STRIPE_CONFIG = {
    "end_point_secret" : os.getenv("END_POINT_SECRET"),
    "stripe_api_key" : os.getenv("stripe_api_key")
}
stripe.api_key = STRIPE_CONFIG["stripe_api_key"] 
endpoint_secret = STRIPE_CONFIG["end_point_secret"] 

async def get_db_connection():
    conn = await aiomysql.connect(
        host=DB_CONFIG['host'],
        user=DB_CONFIG['user'],
        password=DB_CONFIG['password'],
        db=DB_CONFIG['database'],
        autocommit=True
    )
    return conn

async def save_customer_id_to_db(username, customer_id):
    conn = await get_db_connection() 
    try:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
            result = await cursor.fetchone()

            if result:
                await cursor.execute(
                    "UPDATE users SET customer_id = %s WHERE username = %s",
                    (customer_id, username)
                )
            else:
                await cursor.execute(
                    "INSERT INTO users (username, customer_id) VALUES (%s, %s)",
                    (username, customer_id)
                )

            await conn.commit()
            print(f"Customer ID {customer_id} guardado para el usuario {username}")

    except Exception as e:
        print(f"Error al guardar el customer_id: {e}")
    finally:
        conn.close() 

@app.route("/get_logged_in_user", methods=["POST"])
async def get_logged_in_user():
    data = await request.json
    username = data.get("username")

    if not username:
        return jsonify({"status": "fail", "message": "Username no proporcionado"}), 400

    print(f"USERNAMEEE {username}")

    try:
        customers = stripe.Customer.list(limit=100)
        matching_customers = [
            c for c in customers.data if c.metadata.get("username") == username
        ]

        if matching_customers:
            print(f"Clientes encontrados para {username}: {[c['id'] for c in matching_customers]}")
            customer = sorted(matching_customers, key=lambda c: c.created, reverse=True)[0]
            print(f"Cliente seleccionado: {customer['id']}")
        else:
            customer = stripe.Customer.create(
                metadata={"username": username}
            )
            print(f"Cliente creado: {customer['id']}")

        await save_customer_id_to_db(username, customer["id"])

        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            customer=customer["id"], 
            line_items=[ 
                {
                    'price_data': {
                        'currency': 'usd',
                        'product_data': {
                            'name': 'Plan de suscripción',
                        },
                        'recurring': {
                            'interval': 'month', 
                        },
                        'unit_amount': 2000, 
                    },
                    'quantity': 1,
                },
            ],
            mode="subscription",  
            metadata={"username": username}, 
            success_url="https://example.com/success",  
            cancel_url="https://example.com/cancel", 
        )
        print(f"Sesión de Checkout creada: {session.id}")

        static_payment_link_url = session.url
        print(f"URL de Payment Link estático generado: {static_payment_link_url}")

        response = jsonify(
            {
                "status": "success",
                "username": username,
                "customer_id": customer["id"],
                "payment_link_url": static_payment_link_url,
            }
        )
        response.set_cookie("username", username, max_age=3600)
        print(f"COOKIE SET: {username}")
        return response

    except stripe.error.StripeError as e:
        print(f"Error al procesar el cliente o el Payment Link: {e}")
        return jsonify({"status": "fail", "message": "Error al procesar el pago"}), 500


@app.route("/stripe/webhook", methods=["POST"])
async def stripe_webhook():
    print("en webhook")
    payload = await request.data
    sig_header = request.headers.get("Stripe-Signature")
    event = None

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
        print(f"Webhook event: {event}")
    except ValueError:
        return "Invalid payload", 400
    except stripe.error.SignatureVerificationError:
        return "Invalid signature", 400

    try:
        if event["type"] == "checkout.session.completed":
            session = event.get("data", {}).get("object", {})
            if not session:
                return "Invalid session data", 400

            username = session.get("metadata", {}).get("username", "Desconocido")
            email = session.get("customer_email", "No email provided")  
            print(f"Pago completado por {username} - Email: {email}")

        elif event["type"] == "invoice.payment_succeeded":
            customer_id = event["data"]["object"]["customer"]
            print(f"Customer ID from webhook: {customer_id}")
            stripe_customer = stripe.Customer.retrieve(customer_id)
            print(f"Customer Metadata: {stripe_customer.metadata}")

            username = stripe_customer.metadata.get("username", "Desconocido")
            email = stripe_customer.email  
            print(f"USERNAME FROM WEBHOOK: {username} - Email: {email}")

            subscriptions = stripe.Subscription.list(customer=customer_id, limit=1)
            period_end = subscriptions.data[0].current_period_end if subscriptions.data else None
            await update_user_subscription_status(username, "active", period_end)
            print(f"Pago exitoso para cliente: {username} - Email: {email}")

        elif event["type"] == "customer.subscription.deleted":
            customer_id = event["data"]["object"]["customer"]
            stripe_customer = stripe.Customer.retrieve(customer_id)

            username = stripe_customer.metadata.get("username", "Desconocido")
            email = stripe_customer.email 
            await update_user_subscription_status(username, "inactive", None)
            print(f"Suscripción cancelada para cliente: {username} - Email: {email}")

    except Exception as e:
        print(f"Error en webhook: {e}")
        return "Webhook handling error", 500

    return "Success", 200


async def update_user_subscription_status(username, status, period_end):
    db_connection = await get_db_connection()
    async with db_connection.cursor() as cursor:
        try:
            await cursor.execute(
                "UPDATE users SET subscription_status=%s, subscription_end=%s WHERE username=%s",
                (status, datetime.datetime.fromtimestamp(period_end) if period_end else None, username)
            )
            await db_connection.commit()
        except aiomysql.MySQLError as err:
            print(f"Error actualizando la base de datos: {err}")
        finally:
            await db_connection.ensure_closed()


@app.route('/verify_subscription', methods=['POST'])
async def verify_subscription():
    data = await request.json
    username = data.get("username")

    if not username:
        return jsonify({"message": "Username no proporcionado"}), 400 

    db_connection = await get_db_connection()
    async with db_connection.cursor(aiomysql.DictCursor) as cursor:
        try:
            await cursor.execute("SELECT subscription_status, subscription_end FROM users WHERE username=%s", (username,))
            user = await cursor.fetchone()

            if user:
                if user['subscription_status'] == 'active' and user['subscription_end'] > datetime.utcnow():
                    return jsonify({"access_granted": True}), 200
                else:
                    return jsonify({"access_granted": False, "message": "Suscripción inactiva o expirada"}), 403
            else:
                return jsonify({"message": "Usuario no encontrado"}), 404
        except aiomysql.MySQLError as err:
            return jsonify({"message": f"Error de base de datos: {err}"}), 500
        finally:
            db_connection.close()


@app.route("/check_session", methods=["GET"])
async def check_session():
    token = request.headers.get("Authorization") 

    if token:
        try:
            decoded_token = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
            username = decoded_token["username"]

            return jsonify({"username": username}), 200
        except jwt.ExpiredSignatureError:
            return jsonify({"message": "El token ha expirado"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"message": "Token inválido"}), 401

    return jsonify({"username": None}), 200


@app.route('/logout', methods=['POST'])
async def logout():
    return {"message": "Sesión cerrada correctamente"}, 200


def token_required(f):
    """Decorador para verificar si el JWT es válido."""
    @wraps(f)
    async def decorator(*args, **kwargs):
        token = None
        if "Authorization" in request.headers:
            token = request.headers["Authorization"]

        if not token:
            return jsonify({"message": "Token es requerido"}), 403

        try:
            data = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
            current_user = data["username"]
        except:
            return jsonify({"message": "Token inválido"}), 403

        return await f(*args, **kwargs)

    return decorator


@app.route("/register", methods=["POST"])
async def register_user():
    data = await request.json
    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return jsonify({"status": "fail", "message": "Faltan datos"}), 400

    db_connection = await get_db_connection()
    async with db_connection.cursor() as cursor:
        hashed_password = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
        try:
            query = "INSERT INTO users (username, password) VALUES (%s, %s)"
            await cursor.execute(query, (username, hashed_password.decode("utf-8")))
            await db_connection.commit()
            expiration_time = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1)
            token = jwt.encode(
                {"username": username, "exp": expiration_time}, 
                SECRET_KEY, 
                algorithm="HS256"
            )

            return jsonify({"status": "success", "message": "Inicio de sesión exitoso", "token": token, "username": username}), 201
        except aiomysql.MySQLError:
            return jsonify({"status": "fail", "message": "El usuario ya existe"}), 409
        finally:
            db_connection.close()


@app.route("/login", methods=["POST"])
async def login():
    data = await request.json
    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return jsonify({"status": "fail", "message": "Faltan datos"}), 400

    conn = await get_db_connection()

    async with conn.cursor() as cursor:
        query = "SELECT password FROM users WHERE username = %s"
        await cursor.execute(query, (username,))
        user = await cursor.fetchone()

    conn.close()

    if user:
        user_dict = {cursor.description[i][0]: user[i] for i in range(len(cursor.description))}
        if bcrypt.checkpw(password.encode("utf-8"), user_dict["password"].encode("utf-8")):
            expiration_time = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1)
            token = jwt.encode(
                {"username": username, "exp": expiration_time}, 
                SECRET_KEY, 
                algorithm="HS256"
            )

            return jsonify({"status": "success", "message": "Inicio de sesión exitoso", "token": token}), 200

    return jsonify({"status": "fail", "message": "Credenciales inválidas"}), 401


@app.route("/update_account", methods=["PUT"])
#@token_required DESCOMENTAR DESPUESSSSSSSS
async def save_account_details():
    data = await request.json
    username = data.get("username")
    account_id = data.get("account_id")
    account_password = data.get("account_password")
    server = data.get("server")

    if not username:
        return jsonify({"status": "fail", "message": "Falta el username"}), 400
    if not account_id:
        return jsonify({"status": "fail", "message": "Falta el account_id"}), 400
    if not account_password:
        return jsonify({"status": "fail", "message": "Falta el account_password"}), 400
    if not server:
        return jsonify({"status": "fail", "message": "Falta el server"}), 400

    hashed_account_password = bcrypt.hashpw(account_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    try:
        async with await get_db_connection() as conn:
            async with conn.cursor() as cursor:
                query = """
                    UPDATE users 
                    SET account_id = %s, account_password = %s, server = %s 
                    WHERE username = %s
                """
                await cursor.execute(query, (account_id, hashed_account_password, server, username))
                await conn.commit()
                updated_rows = cursor.rowcount

        if updated_rows > 0:
            return jsonify({"status": "success", "message": "Detalles actualizados correctamente"}), 200
        else:
            return jsonify({"status": "fail", "message": "No se encontraron registros para actualizar"}), 404

    except Exception as e:
        return jsonify({"status": "fail", "message": str(e)}), 500


async def get_account_details(username):
    """Obtiene los detalles de la cuenta del usuario desde la base de datos."""
    try:
        conn = await get_db_connection()
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            query = """
                SELECT account_id, account_password, server
                FROM users
                WHERE username = %s
            """
            await cursor.execute(query, (username,))
            result = await cursor.fetchone()

            if result is None:
                return None

            return result
    except aiomysql.Error as e:
        print(f"Error al obtener detalles de la cuenta: {e}")
        return None


def initialize_mt5(username, password):
    """Inicializa MetaTrader 5 con los datos del usuario."""
    account_details = get_account_details(username)
    if not account_details:
        return False, "No se encontraron detalles de la cuenta."

    account = account_details["account_id"]
    server = account_details["server"]
    hashed_password = account_details["account_password"]

    if not bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8')):
        return False, "La contraseña es incorrecta."

    if not mt5.initialize(login=account, password=password, server=server):
        return False, f"Error al inicializar MetaTrader 5: {mt5.last_error()}"

    return True, "MetaTrader 5 inicializado correctamente."


@app.route('/initialize-mt5', methods=['POST'])
async def initialize_mt5_endpoint():
    """Endpoint para validar las credenciales e inicializar MetaTrader 5."""
    data = await request.get_json()
    username = data.get("username")
    user_password = data.get("password")

    if not username or not user_password:
        return jsonify({"message": "Username and password are required"}), 400

    account_details = await get_account_details(username)
    if not account_details:
        return jsonify({"message": "Invalid username"}), 401

    hashed_password = account_details["account_password"]
    if not checkpw(user_password.encode('utf-8'), hashed_password.encode('utf-8')):
        return jsonify({"message": "Invalid password"}), 401

    account = account_details["account_id"]
    server = account_details["server"]

    if not mt5.initialize(login=account, password=user_password, server=server):
        error_msg = mt5.last_error()
        return jsonify({"message": f"Error initializing MetaTrader 5: {error_msg}"}), 500

    return jsonify({"message": "MetaTrader 5 initialized successfully!"}), 200 

def get_candle_data(symbol, timeframe, n_candles):
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, n_candles)
    if rates is None:
        clear_message()
        print(f"No se pueden obtener las velas para {symbol}", mt5.last_error())
        log_operation(f"No se pueden obtener los precios, cierre y vuelva a iniciar sesion.")
        return None
    else: 
        return rates

bot_active = False

async def bot_logic():
    global bot_active
    while bot_active:
        candles_data = candles_data2 = candles_data3 = candles_data4 = candles_data5 = None
        candles_data = get_candle_data(symbol, mt5.TIMEFRAME_M5, n_candles)
        #remove_old_pending_orders(minutes=540)
        #actualizar_resultados()
        #monitor_positions()
        clear_message()
        """if candles_data is not None:
            clear_message()
            logica_bot(symbol, candles_data)
            log_operation(f"El bot esta trabajando para {symbol}...")"""

        """candles_data2 = get_candle_data(symbol2, mt5.TIMEFRAME_M5, n_candles)
        if candles_data2 is not None:
            logica_bot(symbol2, candles_data2)
            log_operation(f"El bot esta trabajando para {symbol2}...")"""

        """candles_data3 = get_candle_data(symbol3, mt5.TIMEFRAME_M5, n_candles)
        if candles_data3 is not None:
            logica_bot(symbol3, candles_data3)
            log_operation(f"El bot esta trabajando para {symbol3}...")"""

        candles_data4 = get_candle_data(symbol4, mt5.TIMEFRAME_M5, n_candles)
        if candles_data4 is not None:
            #clear_message()
            logica_bot(symbol4, candles_data4)
            log_operation(f"El bot esta trabajando para {symbol4}...")

        """candles_data5 = get_candle_data(symbol5, mt5.TIMEFRAME_M5, n_candles)
        if candles_data5 is not None:
            logica_bot(symbol5, candles_data5)
            log_operation(f"El bot esta trabajando para {symbol5}...")"""

        """candles_data6 = get_candle_data(symbol6, mt5.TIMEFRAME_M5, n_candles)
        if candles_data6 is not None:
            logica_bot(symbol6, candles_data6)
            log_operation(f"El bot esta trabajando para {symbol6}...")"""

        """candles_data7 = get_candle_data(symbol7, mt5.TIMEFRAME_M5, n_candles)
        if candles_data7 is not None:
            logica_bot(symbol7, candles_data7)
            log_operation(f"El bot esta trabajando para {symbol7}...")"""

        await asyncio.sleep(60)

@app.route('/start_bot', methods=['POST'])
async def start_bot():
    global bot_active
    if not bot_active:
        bot_active = True
        asyncio.create_task(bot_logic())
        return {"status": "success", "message": "Bot iniciado"}, 200
    else:
        return {"status": "error", "message": "El bot ya está en ejecución"}, 400

@app.route('/stop_bot', methods=['POST'])
async def stop_bot():
    global bot_active
    if bot_active:
        bot_active = False
        return {"status": "success", "message": "Bot detenido"}, 200
    else:
        return {"status": "error", "message": "El bot no está en ejecución"}, 400

@app.route('/check_bot_status', methods=['GET'])
def check_bot_status():
    return {"active": bot_active}, 200

operation_message = [] 

def log_operation(message):
    """Guardar solo el mensaje más reciente"""
    global operation_message
    operation_message.append(message)

@app.route('/get_operations', methods=['GET'])
async def get_operations():
    """Devolver todos los mensajes concatenados"""
    print("Operation Messages Before Sending: ", operation_message) 
    return Response("\n".join(operation_message), content_type='text/plain')

def clear_message():
    operation_message.clear()


if __name__ == '__main__':
    import uvicorn
    logger.info("Servidor iniciado")
    uvicorn.run(app, host="38.247.140.62", port=80)
